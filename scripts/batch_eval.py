#!/usr/bin/env python3
"""批量自动化评估脚本 — 分批执行 + Trace 采集 + Judge 评分 + HTML 报告。

用法:
    ./batch_eval.py                          # 全部 6 批, 每批 10 条
    ./batch_eval.py --batch 1                # 仅跑第 1 批
    ./batch_eval.py --batch 1-3              # 跑 1-3 批
    ./batch_eval.py --report-only            # 仅从已有结果生成报告

输出:
    docs/batch_results/batch_1.json ... batch_6.json
    docs/batch_results/summary.json
    docs/eval_report.html
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ── 配置 ──────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
TEST_SET_PATH = BASE_DIR / "docs" / "qa_testset_ali_handbook.json"
RESULTS_DIR = BASE_DIR / "docs" / "batch_results"
REPORT_PATH = BASE_DIR / "docs" / "eval_report.html"
BASE_URL = "http://localhost:8000"
KB_ID = "cccccccc-0000-4000-c000-000000000001"
BATCH_SIZE = 10
TOTAL_BATCHES = 6
CONCURRENCY = 3
API_TIMEOUT = 90.0
BATCH_COOLDOWN = 3.0  # 批次间隔秒数


def _load_env() -> dict:
    env = {}
    for p in [BASE_DIR / ".env", Path(".env")]:
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k] = v
            break
        except FileNotFoundError:
            continue
    return env


# ── SSE 客户端 ────────────────────────────────────────

async def call_chat_api(
    client: httpx.AsyncClient, query: str, top_k: int = 10
) -> dict[str, Any]:
    """调用 POST /v1/chat，返回 {answer, chunks, langfuse_trace_id, first_token_ms, total_ms, error}。"""
    payload = {
        "query": query,
        "filter_params": {"kb_ids": [KB_ID]},
        "top_k": top_k,
        "history_messages": [],
        "conversation_id": "aaaaaaaa-1111-4000-a000-000000000001",
    }

    answer_parts: list[str] = []
    chunks: list[dict] = []
    langfuse_trace_id: str | None = None
    t_start = time.monotonic()
    first_token_ms = 0
    first_token_set = False

    try:
        async with client.stream(
            "POST", f"{BASE_URL}/v1/chat",
            json=payload, timeout=httpx.Timeout(API_TIMEOUT),
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                token = data.get("token", "")
                if token and not data.get("done"):
                    if not first_token_set:
                        first_token_ms = int((time.monotonic() - t_start) * 1000)
                        first_token_set = True
                    answer_parts.append(token)
                if data.get("done"):
                    sources = data.get("sources") or []
                    chunks = [
                        {"chunk_text": s.get("chunk_text", ""), "filename": s.get("filename", "")}
                        for s in sources
                    ]
                    langfuse_trace_id = data.get("langfuse_trace_id")
                    break
    except Exception as e:
        return {
            "answer": "", "chunks": [], "langfuse_trace_id": None,
            "first_token_ms": 0, "total_ms": int((time.monotonic() - t_start) * 1000),
            "error": str(e),
        }

    return {
        "answer": "".join(answer_parts),
        "chunks": chunks,
        "langfuse_trace_id": langfuse_trace_id,
        "first_token_ms": first_token_ms,
        "total_ms": int((time.monotonic() - t_start) * 1000),
        "error": None,
    }


# ── Langfuse Trace 拉取 ────────────────────────────────

def _init_langfuse():
    env = _load_env()
    try:
        from langfuse import Langfuse
        return Langfuse(
            secret_key=env["LANGFUSE_SECRET_KEY"],
            public_key=env["LANGFUSE_PUBLIC_KEY"],
            host=env["LANGFUSE_BASE_URL"],
        )
    except Exception:
        return None


def fetch_trace(langfuse_client, trace_id: str) -> dict | None:
    """拉取 Langfuse trace 树。"""
    if langfuse_client is None:
        return None
    try:
        trace = langfuse_client.get_trace(trace_id)
        observations = langfuse_client.get_observations(trace_id=trace_id)

        # 构建节点树
        obs_map: dict[str, dict] = {}
        roots: list[dict] = []

        for obs in observations:
            node = {
                "id": getattr(obs, "id", ""),
                "name": getattr(obs, "name", ""),
                "type": str(getattr(obs, "type", "span")).lower(),
                "parent_id": getattr(obs, "parent_observation_id", None),
                "start_time": str(getattr(obs, "start_time", "")) if getattr(obs, "start_time", None) else None,
                "end_time": str(getattr(obs, "end_time", "")) if getattr(obs, "end_time", None) else None,
                "model": getattr(obs, "model", None) or None,
                "input": _safe_json(getattr(obs, "input", None)),
                "output": _safe_json(getattr(obs, "output", None)),
                "metadata": _safe_json(getattr(obs, "metadata", None)),
                "children": [],
            }
            # 计算耗时
            if node["start_time"] and node["end_time"]:
                try:
                    from datetime import datetime
                    st = datetime.fromisoformat(node["start_time"].replace("Z", "+00:00"))
                    et = datetime.fromisoformat(node["end_time"].replace("Z", "+00:00"))
                    node["duration_ms"] = int((et - st).total_seconds() * 1000)
                except Exception:
                    node["duration_ms"] = 0
            else:
                node["duration_ms"] = 0
            obs_map[node["id"]] = node

        # 组装父子关系
        for node in obs_map.values():
            pid = node.get("parent_id")
            if pid and pid in obs_map:
                obs_map[pid]["children"].append(node)
            elif pid is None or pid == trace_id:
                roots.append(node)

        # 提取评分
        scores: dict[str, float] = {}
        if hasattr(trace, "scores"):
            for s in trace.scores:
                scores[getattr(s, "name", "")] = getattr(s, "value", 0.0)

        # 关键 span 摘要
        span_summary: dict[str, dict] = {}
        for node in obs_map.values():
            name = node["name"]
            if name in ("hybrid_search", "reranker", "query_planner", "llm_generation", "judge"):
                span_summary[name] = {
                    "duration_ms": node["duration_ms"],
                    "output": node["output"],
                }

        return {
            "trace_id": trace_id,
            "spans_count": len(obs_map),
            "roots": roots,
            "scores": scores,
            "span_summary": span_summary,
        }
    except Exception as e:
        return {"trace_id": trace_id, "error": str(e)}


def _safe_json(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (list, dict)):
        return val
    try:
        return str(val)[:500]
    except Exception:
        return None


# ── Judge 评分 ─────────────────────────────────────────

async def judge_score_batch(judge, samples: list[dict]) -> list[dict]:
    """对一批样本批量 Judge 评分。"""
    if judge is None:
        return samples

    async def _score_one(s: dict) -> dict:
        answer = s.get("answer", "").strip()
        if not answer:
            s["judge"] = None
            return s
        ctxs = [c.get("chunk_text", "") for c in s.get("chunks", []) if c.get("chunk_text", "").strip()]
        chunks_for_judge = [
            {"content": c[:300], "chunk_id": f"c{i}", "source_file": "", "score": 1.0}
            for i, c in enumerate(ctxs[:5])
        ]
        ground_truth = s.get("expected_answer", "")
        if ground_truth == "NOT_IN_KB":
            ground_truth = None
        try:
            result = await judge.evaluate(
                query=s["question"],
                answer=answer,
                chunks=chunks_for_judge,
                ground_truth=ground_truth,
            )
            s["judge"] = {
                "faithfulness": result.get("faithfulness"),
                "answer_relevance": result.get("answer_relevance"),
                "context_relevance": result.get("context_relevance"),
                "answer_correctness": result.get("answer_correctness"),
                "model": result.get("model", ""),
                "latency_ms": result.get("latency_ms", 0),
            }
        except Exception as e:
            s["judge"] = {"error": str(e)}
        return s

    tasks = [_score_one(s) for s in samples]
    return await asyncio.gather(*tasks)


# ── HTML 报告生成 ──────────────────────────────────────

def generate_html_report(per_batch: list[dict], output_path: Path) -> None:
    """生成完整的 HTML 诊断报告。"""
    all_results = []
    for batch in per_batch:
        all_results.extend(batch.get("results", []))

    total = len(all_results)
    positive = [r for r in all_results if r.get("category") != "negative"]
    negative = [r for r in all_results if r.get("category") == "negative"]
    errors = [r for r in all_results if r.get("error")]

    # 计算正向题各维度平均分
    judge_dims = ["faithfulness", "answer_relevance", "context_relevance", "answer_correctness"]
    pos_scores: dict[str, list[float]] = {d: [] for d in judge_dims}
    for r in positive:
        j = r.get("judge") or {}
        for d in judge_dims:
            v = j.get(d)
            if v is not None:
                pos_scores[d].append(v)
    pos_avg = {d: round(sum(v)/len(v), 3) if v else 0 for d, v in pos_scores.items()}

    # 负向题分析
    neg_with_answer = [r for r in negative if r.get("answer", "").strip()]
    neg_refused = [r for r in negative if not r.get("answer", "").strip() or
                   any(kw in r.get("answer", "").lower() for kw in
                       ["未找到", "没有", "不包含", "无法提供", "不在", "抱歉"])]

    # 平均延迟
    avg_ft = sum(r.get("first_token_ms", 0) for r in all_results if r.get("first_token_ms")) / max(total, 1)
    avg_total = sum(r.get("total_ms", 0) for r in all_results if r.get("total_ms")) / max(total, 1)

    # Trace 统计
    with_trace = [r for r in all_results if r.get("trace")]

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KES 检索评估报告 — batch eval</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #333; }}
.header {{ background: linear-gradient(135deg, #1677ff, #0958d9); color: #fff; padding: 32px 48px; }}
.header h1 {{ font-size: 24px; margin-bottom: 8px; }}
.header p {{ opacity: 0.85; font-size: 14px; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 24px 48px; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.card {{ background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
.card .value {{ font-size: 32px; font-weight: 700; }}
.card .label {{ color: #8c8c8c; font-size: 13px; margin-top: 4px; }}
.card.green .value {{ color: #52c41a; }}
.card.red .value {{ color: #ff4d4f; }}
.card.blue .value {{ color: #1677ff; }}
.card.orange .value {{ color: #fa8c16; }}
.section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
.section h2 {{ font-size: 18px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #f0f0f0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
th {{ background: #fafafa; font-weight: 600; color: #555; }}
tr:hover {{ background: #fafafa; }}
.tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.tag-pos {{ background: #e6f7ff; color: #1677ff; }}
.tag-neg {{ background: #fff7e6; color: #fa8c16; }}
.tag-err {{ background: #fff2f0; color: #ff4d4f; }}
.tag-ok {{ background: #f6ffed; color: #52c41a; }}
.tag-warn {{ background: #fffbe6; color: #fadb14; }}
.score-bar {{ width: 100%; height: 8px; border-radius: 4px; background: #f0f0f0; overflow: hidden; }}
.score-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
.detail-row {{ cursor: pointer; }}
.detail-panel {{ display: none; background: #fafafa; padding: 16px; margin: 8px 0; border-radius: 8px; font-size: 12px; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }}
.batch-tabs {{ display: flex; gap: 8px; margin-bottom: 16px; }}
.batch-tab {{ padding: 8px 20px; border-radius: 8px; border: 1px solid #d9d9d9; background: #fff; cursor: pointer; font-size: 13px; }}
.batch-tab.active {{ background: #1677ff; color: #fff; border-color: #1677ff; }}
.batch-content {{ display: none; }}
.batch-content.active {{ display: block; }}
.warn-box {{ background: #fffbe6; border: 1px solid #ffe58f; border-radius: 8px; padding: 16px; margin: 12px 0; font-size: 13px; }}
.warn-box strong {{ color: #d48806; }}
.progress-ring {{ display: inline-block; width: 60px; height: 60px; }}
</style>
</head>
<body>
<div class="header">
  <h1>🔍 KES 检索质量评估报告</h1>
  <p>测试集: qa_testset_ali_handbook.json | 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>
<div class="container">

<!-- 仪表盘 -->
<div class="cards">
  <div class="card"><div class="value">{total}</div><div class="label">总样本数</div></div>
  <div class="card green"><div class="value">{len(positive)}</div><div class="label">正向题</div></div>
  <div class="card orange"><div class="value">{len(negative)}</div><div class="label">负向题（拒答测试）</div></div>
  <div class="card {'red' if errors else 'green'}"><div class="value">{len(errors)}</div><div class="label">API 错误</div></div>
  <div class="card blue"><div class="value">{avg_ft:.0f}ms</div><div class="label">平均首 token 延迟</div></div>
  <div class="card"><div class="value">{avg_total:.0f}ms</div><div class="label">平均总延迟</div></div>
  <div class="card blue"><div class="value">{len(with_trace)}</div><div class="label">Trace 成功拉取</div></div>
</div>

<!-- 评分概览 -->
<div class="section">
  <h2>📊 Judge 四维评分 — 正向题</h2>
  <table>
    <tr><th>维度</th><th>平均分</th><th>样本数</th><th>评级</th></tr>
    {_score_table_rows(pos_avg, pos_scores)}
  </table>
</div>

<!-- 负向题检测 -->
<div class="section">
  <h2>🛡️ 负向题拒答检测</h2>
  <table>
    <tr><th>指标</th><th>数量</th><th>比率</th></tr>
    <tr><td>负向题总数</td><td>{len(negative)}</td><td>—</td></tr>
    <tr><td>产生了回答（可能幻觉）</td><td>{len(neg_with_answer)}</td><td>{len(neg_with_answer)/max(len(negative),1)*100:.0f}%</td></tr>
    <tr><td>正确拒答/无答案</td><td>{len(neg_refused)}</td><td>{len(neg_refused)/max(len(negative),1)*100:.0f}%</td></tr>
  </table>
  {_neg_refused_html(negative, neg_refused)}
</div>

<!-- 分批结果 -->
<div class="section">
  <h2>📋 分批详情</h2>
  <div class="batch-tabs">
    {''.join(f'<div class="batch-tab{" active" if i==0 else ""}" onclick="switchBatch({i})">第 {i+1} 批</div>' for i in range(len(per_batch)))}
  </div>
  {_batch_content_html(per_batch)}
</div>

<!-- 检索链路诊断 -->
<div class="section">
  <h2>🔧 检索链路诊断</h2>
  {_diagnostics_html(all_results)}
</div>

<!-- 问题列表 -->
<div class="section">
  <h2>📝 全部问题详情</h2>
  {_all_questions_html(all_results)}
</div>

</div>
<script>
function toggleDetail(id) {{
  var el = document.getElementById('detail-' + id);
  el.style.display = el.style.display === 'block' ? 'none' : 'block';
}}
function switchBatch(idx) {{
  document.querySelectorAll('.batch-tab').forEach(function(t,i) {{ t.classList.toggle('active', i===idx); }});
  document.querySelectorAll('.batch-content').forEach(function(c,i) {{ c.classList.toggle('active', i===idx); }});
}}
</script>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")
    print(f"[report] HTML 报告: {output_path}")


def _score_table_rows(pos_avg: dict, pos_scores: dict) -> str:
    rows = []
    for d, avg in pos_avg.items():
        label = {"faithfulness": "忠实度", "answer_relevance": "答案相关性",
                 "context_relevance": "上下文相关性", "answer_correctness": "答案正确性"}.get(d, d)
        count = len(pos_scores.get(d, []))
        if avg >= 0.7:
            rating = '<span class="tag tag-ok">良好</span>'
        elif avg >= 0.5:
            rating = '<span class="tag tag-warn">一般</span>'
        else:
            rating = '<span class="tag tag-err">较差</span>'
        pct = int(avg * 100)
        color = "#52c41a" if avg >= 0.7 else "#faad14" if avg >= 0.5 else "#ff4d4f"
        bar = f'<div class="score-bar"><div class="score-bar-fill" style="width:{pct}%;background:{color}"></div></div>'
        rows.append(f'<tr><td>{label} ({d})</td><td><strong>{avg:.3f}</strong> {bar}</td><td>{count}</td><td>{rating}</td></tr>')
    return "\n".join(rows)


def _neg_refused_html(negative: list, refused: list) -> str:
    hallucinated = [r for r in negative if r.get("answer", "").strip() and r not in refused]
    if not hallucinated:
        return '<div class="warn-box">✅ 所有负向题均正确拒答，未产生幻觉内容。</div>'
    items = "".join(
        f'<tr><td>#{r["id"]}</td><td class="tag tag-err">⚠ 幻觉</td>'
        f'<td>{r["question"][:80]}</td>'
        f'<td>{r.get("answer", "")[:120]}...</td></tr>'
        for r in hallucinated[:10]
    )
    return f'<div class="warn-box"><strong>⚠ 发现 {len(hallucinated)} 个可能幻觉案例</strong>（负向题产生了不应有的回答）</div><table><tr><th>ID</th><th>状态</th><th>问题</th><th>回答摘要</th></tr>{items}</table>'


def _batch_content_html(per_batch: list[dict]) -> str:
    sections = []
    for i, batch in enumerate(per_batch):
        results = batch.get("results", [])
        items = "".join(
            f'<tr class="detail-row" onclick="toggleDetail(\'b{i}r{j}\')">'
            f'<td>{r["id"]}</td>'
            f'<td><span class="tag {"tag-neg" if r.get("category") == "negative" else "tag-pos"}">'
            f'{"负向" if r.get("category") == "negative" else "正向"}</span></td>'
            f'<td>{r.get("question", "")[:60]}</td>'
            f'<td>{r.get("answer", "")[:80]}</td>'
            f'<td>{r.get("total_ms", 0)}ms</td>'
            f'<td>{_judge_badge(r)}</td></tr>'
            f'<tr><td colspan="6"><div class="detail-panel" id="detail-b{i}r{j}">'
            f'Q: {r.get("question", "")}\n\n'
            f'A: {r.get("answer", "")}\n\n'
            f'Judge: {json.dumps(r.get("judge", {}), ensure_ascii=False, indent=2)}\n\n'
            f'Trace: {json.dumps({k: v for k, v in r.get("trace", {}).items() if k != "roots"}, ensure_ascii=False, indent=2)}'
            f'</div></td></tr>'
            for j, r in enumerate(results)
        )
        sections.append(f'<div class="batch-content{" active" if i==0 else ""}">'
                        f'<table><tr><th>ID</th><th>类型</th><th>问题</th><th>回答</th><th>延迟</th><th>评分</th></tr>'
                        f'{items}</table></div>')
    return "\n".join(sections)


def _judge_badge(r: dict) -> str:
    j = r.get("judge") or {}
    if not j or j.get("error"):
        return '<span class="tag tag-err">无评分</span>'
    f = j.get("faithfulness") or 0
    if f >= 0.7:
        return f'<span class="tag tag-ok">F:{f:.2f}</span>'
    elif f >= 0.5:
        return f'<span class="tag tag-warn">F:{f:.2f}</span>'
    else:
        return f'<span class="tag tag-err">F:{f:.2f}</span>'


def _diagnostics_html(all_results: list) -> str:
    # 延迟分布
    ft_times = [r.get("first_token_ms", 0) for r in all_results if r.get("first_token_ms")]
    total_times = [r.get("total_ms", 0) for r in all_results if r.get("total_ms")]
    if total_times:
        slow = sorted(total_times, reverse=True)[:5]
    else:
        slow = []

    # 检索命中分析
    no_chunks = [r for r in all_results if not r.get("chunks") and not r.get("error")]
    low_chunks = [r for r in all_results if 0 < len(r.get("chunks", [])) < 3]

    # Trace 阶段耗时分析
    span_stats = _collect_span_stats(all_results)

    html = "<div>"
    html += f"<p>首 token 延迟范围: {min(ft_times)}ms ~ {max(ft_times)}ms, 中位数: {_median(ft_times)}ms</p>"
    html += f"<p>零 chunk 查询: {len(no_chunks)} 条 | 低 chunk 查询(&lt;3): {len(low_chunks)} 条</p>"

    if slow:
        html += f"<p>最慢 {len(slow)} 条查询: {', '.join(f'{t}ms' for t in slow)}</p>"

    html += '<h3 style="margin-top:16px">Trace 阶段耗时汇总</h3>'
    html += '<table><tr><th>阶段</th><th>出现次数</th><th>平均耗时(ms)</th><th>最大耗时(ms)</th></tr>'
    for name, stats in sorted(span_stats.items()):
        html += (f'<tr><td>{name}</td><td>{stats["count"]}</td>'
                 f'<td>{stats["avg_ms"]:.0f}</td><td>{stats["max_ms"]:.0f}</td></tr>')
    html += '</table>'

    # 自动诊断
    issues = []
    pos_samples = [r for r in all_results if r.get("category") != "negative"]
    neg_samples = [r for r in all_results if r.get("category") == "negative"]
    if pos_samples:
        pos_f = [r.get("judge", {}).get("faithfulness", 0) or 0 for r in pos_samples if r.get("judge")]
        if pos_f and sum(pos_f)/len(pos_f) < 0.5:
            issues.append("正向题忠实度偏低，可能存在 RAG 幻觉问题")
        pos_cr = [r.get("judge", {}).get("context_relevance", 0) or 0 for r in pos_samples if r.get("judge")]
        if pos_cr and sum(pos_cr)/len(pos_cr) < 0.5:
            issues.append("上下文相关性偏低，检索召回质量可能不足")
    if neg_samples:
        hallucinated = [r for r in neg_samples if r.get("answer", "").strip() and
                        not any(kw in r.get("answer", "").lower()
                                for kw in ["未找到", "没有", "不包含", "无法提供", "不在", "抱歉"])]
        if len(hallucinated) > len(neg_samples) * 0.3:
            issues.append(f"负向题幻觉率 {len(hallucinated)}/{len(neg_samples)}，拒答机制需增强")
    if no_chunks:
        issues.append(f"{len(no_chunks)} 条查询零召回，检索策略可能需要优化")
    if not issues:
        issues.append("✅ 未发现明显异常，系统运行良好")

    html += '<h3 style="margin-top:16px">自动诊断</h3>'
    for iss in issues:
        html += f'<div class="warn-box">{iss}</div>'
    html += "</div>"
    return html


def _collect_span_stats(all_results: list) -> dict:
    stats: dict[str, dict] = {}
    for r in all_results:
        trace = r.get("trace")
        if not trace:
            continue
        ss = trace.get("span_summary", {})
        for name, info in ss.items():
            if name not in stats:
                stats[name] = {"count": 0, "total_ms": 0, "max_ms": 0}
            ms = info.get("duration_ms", 0) or 0
            stats[name]["count"] += 1
            stats[name]["total_ms"] += ms
            stats[name]["max_ms"] = max(stats[name]["max_ms"], ms)
    for v in stats.values():
        v["avg_ms"] = v["total_ms"] / max(v["count"], 1)
    return stats


def _all_questions_html(all_results: list) -> str:
    rows = []
    for r in all_results:
        cat = "负向" if r.get("category") == "negative" else "正向"
        j = r.get("judge") or {}
        scores_str = f'F:{j.get("faithfulness","-"):.2f} AR:{j.get("answer_relevance","-"):.2f} CR:{j.get("context_relevance","-"):.2f}' if j and not j.get("error") else "—"
        error_tag = f'<span class="tag tag-err">ERR</span>' if r.get("error") else ''
        rows.append(
            f'<tr>'
            f'<td>{r["id"]}</td><td>{cat}</td>'
            f'<td>{r.get("question", "")[:80]}</td>'
            f'<td>{r.get("answer", "")[:100]}</td>'
            f'<td>{scores_str} {error_tag}</td>'
            f'<td>{r.get("total_ms", 0)}ms</td>'
            f'</tr>'
        )
    return f'<table><tr><th>ID</th><th>类型</th><th>问题</th><th>回答</th><th>评分</th><th>延迟</th></tr>{"".join(rows)}</table>'


def _median(vals: list) -> float:
    if not vals:
        return 0
    s = sorted(vals)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


# ── 主流程 ────────────────────────────────────────────

async def run_batch(
    batch_idx: int, questions: list[dict], langfuse_client, judge
) -> dict:
    """执行单批：调用 API → 拉 trace → Judge 评分。"""
    print(f"\n{'='*60}")
    print(f"  第 {batch_idx+1}/{TOTAL_BATCHES} 批 — {len(questions)} 条")
    print(f"{'='*60}")

    sem = asyncio.Semaphore(CONCURRENCY)

    async def do_one(item: dict) -> dict:
        async with sem:
            async with httpx.AsyncClient() as client:
                result = await call_chat_api(client, item["question"])
            result["id"] = item.get("id", "?")
            result["question"] = item["question"]
            result["expected_answer"] = item.get("expected_answer", "")
            result["type"] = item.get("type", "")
            result["difficulty"] = item.get("difficulty", "")
            result["dimension"] = item.get("dimension", "")
            result["category"] = item.get("category", "")
            result["source_sections"] = item.get("source_sections", [])
            print(f"  [{result['id']}] {result['total_ms']}ms {'❌ '+result['error'] if result.get('error') else '✓'}")
            return result

    tasks = [do_one(q) for q in questions]
    results = await asyncio.gather(*tasks)

    # 拉取 Langfuse trace
    print(f"\n  拉取 Langfuse traces...")
    for r in results:
        tid = r.get("langfuse_trace_id")
        if tid and langfuse_client:
            trace = fetch_trace(langfuse_client, tid)
            r["trace"] = trace
            if trace and "error" not in trace:
                print(f"    [{r['id']}] trace: {trace.get('spans_count', 0)} spans")
            else:
                print(f"    [{r['id']}] trace: 失败 — {trace.get('error', 'unknown') if trace else 'no client'}")

    # Judge 评分
    print(f"\n  Judge 评分...")
    results = await judge_score_batch(judge, results)
    for r in results:
        j = r.get("judge") or {}
        if j and not j.get("error"):
            print(f"    [{r['id']}] F:{j.get('faithfulness', '-'):.2f} AR:{j.get('answer_relevance', '-'):.2f} CR:{j.get('context_relevance', '-'):.2f} AC:{j.get('answer_correctness', '-'):.2f}")

    return {"batch_idx": batch_idx, "results": results, "completed_at": time.strftime("%Y-%m-%d %H:%M:%S")}


async def main():
    parser = argparse.ArgumentParser(description="批量评估")
    parser.add_argument("--batch", help="批次范围 (1, 1-3), 默认全部")
    parser.add_argument("--report-only", action="store_true", help="仅从已有结果生成报告")
    args = parser.parse_args()

    # 加载测试集
    with open(TEST_SET_PATH) as f:
        testset = json.load(f)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.report_only:
        # 从已有 JSON 加载并生成报告
        per_batch = []
        for i in range(TOTAL_BATCHES):
            bp = RESULTS_DIR / f"batch_{i+1}.json"
            if bp.exists():
                with open(bp) as f:
                    per_batch.append(json.load(f))
        if not per_batch:
            print("未找到任何批次结果文件")
            return
        summary = _build_summary(per_batch)
        with open(RESULTS_DIR / "summary.json", "w") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        generate_html_report(per_batch, REPORT_PATH)
        return

    # 确定批次范围
    if args.batch:
        if "-" in args.batch:
            start, end = map(int, args.batch.split("-"))
            batches = list(range(start - 1, end))
        else:
            batches = [int(args.batch) - 1]
    else:
        batches = list(range(TOTAL_BATCHES))

    # 初始化 Langfuse + Judge
    print("初始化 Langfuse...")
    langfuse_client = _init_langfuse()
    print(f"  Langfuse: {'OK' if langfuse_client else '不可用'}")

    print("初始化 Judge...")
    import os as _os
    _os.chdir(str(BASE_DIR / "ai-service"))
    sys.path.insert(0, ".")
    from llm.model_pool import ModelPool
    from retrieval.judge import JudgeEvaluator
    pool = ModelPool()
    await pool.initialize()
    judge = JudgeEvaluator(pool.get_llm("slm"))
    print(f"  Judge: OK")

    per_batch = []
    for bi in batches:
        start = bi * BATCH_SIZE
        end = start + BATCH_SIZE
        batch_questions = testset[start:end]

        result = await run_batch(bi, batch_questions, langfuse_client, judge)

        # 保存中间结果
        bp = RESULTS_DIR / f"batch_{bi+1}.json"
        with open(bp, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  💾 已保存: {bp}")
        per_batch.append(result)

        if bi < batches[-1]:
            print(f"\n  ⏳ 冷却 {BATCH_COOLDOWN}s...")
            await asyncio.sleep(BATCH_COOLDOWN)

    # 汇总
    summary = _build_summary(per_batch)
    with open(RESULTS_DIR / "summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n📊 汇总已保存: {RESULTS_DIR / 'summary.json'}")

    # 生成 HTML 报告
    generate_html_report(per_batch, REPORT_PATH)

    # 打印结果摘要
    print_summary(summary)


def _build_summary(per_batch: list) -> dict:
    all_results = []
    for b in per_batch:
        all_results.extend(b.get("results", []))
    pos = [r for r in all_results if r.get("category") != "negative"]
    neg = [r for r in all_results if r.get("category") == "negative"]
    judge_dims = ["faithfulness", "answer_relevance", "context_relevance", "answer_correctness"]
    pos_scores = {d: [] for d in judge_dims}
    for r in pos:
        j = r.get("judge") or {}
        for d in judge_dims:
            v = j.get(d)
            if v is not None:
                pos_scores[d].append(v)
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_samples": len(all_results),
        "positive_count": len(pos),
        "negative_count": len(neg),
        "error_count": len([r for r in all_results if r.get("error")]),
        "pos_avg_scores": {d: round(sum(v)/len(v), 4) if v else 0 for d, v in pos_scores.items()},
        "neg_refused": len([r for r in neg if not r.get("answer", "").strip() or
                           any(kw in r.get("answer", "").lower()
                               for kw in ["未找到", "没有", "不包含", "无法提供", "不在", "抱歉"])]),
        "neg_hallucinated": len([r for r in neg if r.get("answer", "").strip() and
                                 not any(kw in r.get("answer", "").lower()
                                         for kw in ["未找到", "没有", "不包含", "无法提供", "不在", "抱歉"])]),
        "avg_first_token_ms": sum(r.get("first_token_ms", 0) for r in all_results if r.get("first_token_ms")) / max(len(all_results), 1),
        "avg_total_ms": sum(r.get("total_ms", 0) for r in all_results if r.get("total_ms")) / max(len(all_results), 1),
    }


def print_summary(summary: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  评估完成")
    print(f"{'='*60}")
    print(f"  总样本: {summary['total_samples']}")
    print(f"  正向题: {summary['positive_count']}  |  负向题: {summary['negative_count']}")
    print(f"  API错误: {summary['error_count']}")
    print(f"  平均延迟: {summary['avg_total_ms']:.0f}ms (首token {summary['avg_first_token_ms']:.0f}ms)")
    print(f"\n  正向题平均分:")
    for d, v in summary["pos_avg_scores"].items():
        print(f"    {d}: {v:.4f}")
    print(f"\n  负向题拒答率: {summary['neg_refused']}/{summary['negative_count']} ({summary['neg_refused']/max(summary['negative_count'],1)*100:.0f}%)")
    if summary['neg_hallucinated']:
        print(f"  ⚠ 幻觉风险: {summary['neg_hallucinated']} 条负向题产生了不应有的回答")
    else:
        print(f"  ✅ 所有负向题正确处理")


if __name__ == "__main__":
    asyncio.run(main())
