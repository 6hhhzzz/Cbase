#!/usr/bin/env python3
"""Judge 端到端评估脚本 — 使用 LLM-as-a-Judge 做 4 维自动评分。

用法:
    # 基线评估
    ./judge_eval.py eval --version v1-baseline --kb-id cccccccc-0000-4000-c000-000000000001

    # 对比两个版本
    ./judge_eval.py compare --report-a v1-baseline.json --report-b v2-optimized.json

依赖:
    pip install langfuse httpx
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

# ── 配置 ──────────────────────────────────────────────

DEFAULT_TEST_SET = str(Path(__file__).resolve().parent.parent / "docs" / "qa_testset_ali_handbook.json")
DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_OUTPUT = str(Path(__file__).resolve().parent.parent / "evaluation_reports")


def _load_env() -> dict:
    env = {}
    for p in [Path(__file__).resolve().parent.parent / ".env", Path(".env")]:
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
    client: httpx.AsyncClient,
    base_url: str,
    query: str,
    kb_id: str,
    top_k: int = 10,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """调用 POST /v1/chat，流式解析 SSE，返回 {answer, chunks, langfuse_trace_id}。"""
    payload = {
        "query": query,
        "filter_params": {"kb_ids": [kb_id]},
        "top_k": top_k,
        "history_messages": [],
        "conversation_id": "aaaaaaaa-1111-4000-a000-000000000001",
    }

    answer_parts: list[str] = []
    chunks: list[dict] = []
    langfuse_trace_id: str | None = None

    try:
        async with client.stream(
            "POST", f"{base_url}/v1/chat",
            json=payload, timeout=httpx.Timeout(timeout),
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
        return {"answer": "", "chunks": [], "langfuse_trace_id": None, "error": str(e)}

    return {
        "answer": "".join(answer_parts),
        "chunks": chunks,
        "langfuse_trace_id": langfuse_trace_id,
    }


# ── Judge 评估 ────────────────────────────────────────

async def compute_judge_metrics(samples: list[dict]) -> dict:
    """用 Judge（单次 LLM 调用）对每个样本做 4 维评分。"""
    import os as _os
    _os.chdir(str(Path(__file__).resolve().parent.parent / "ai-service"))
    sys.path.insert(0, ".")

    from llm.model_pool import ModelPool
    from retrieval.judge import JudgeEvaluator

    pool = ModelPool()
    await pool.initialize()
    judge = JudgeEvaluator(pool.get_llm("slm"))

    scores = {}
    per_sample = []

    async def _score_one(s: dict) -> dict:
        ctxs = [str(c).strip() for c in (s.get("contexts") or []) if c and str(c).strip()]
        chunks_for_judge = [{"content": c[:300], "chunk_id": f"c{i}", "source_file": "", "score": 1.0}
                           for i, c in enumerate(ctxs[:5])]
        result = await judge.evaluate(
            query=s["question"],
            answer=s.get("answer", "").strip(),
            chunks=chunks_for_judge,
            ground_truth=s.get("ground_truth", "").strip() or None,
        )
        result["langfuse_trace_id"] = s.get("langfuse_trace_id", "")
        result["id"] = s.get("id", "?")
        result["question"] = s["question"][:80]
        return result

    tasks = [_score_one(s) for s in samples if s.get("answer", "").strip()]
    results = await asyncio.gather(*tasks)
    print(f"[judge] 评分完成: {len(results)}/{len(samples)} 样本")

    dims = ["faithfulness", "answer_relevance", "context_relevance", "answer_correctness"]
    for dim in dims:
        vals = [r[dim] for r in results if r.get(dim) is not None]
        if vals:
            scores[f"judge_{dim}"] = {
                "aggregate": round(sum(vals) / len(vals), 4),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
            }

    for r in results:
        sample_scores = {}
        for dim in dims:
            if r.get(dim) is not None:
                sample_scores[f"judge_{dim}"] = r[dim]
        per_sample.append({
            "id": r["id"], "question": r["question"],
            "langfuse_trace_id": r.get("langfuse_trace_id", ""),
            "judge_scores": sample_scores,
        })

    return {"scores": scores, "per_sample": per_sample}


# ── Langfuse 推送 ─────────────────────────────────────

def push_judge_to_langfuse(per_sample: list[dict], version: str) -> int:
    """推送 Judge 分数到 Langfuse traces。"""
    env = _load_env()
    try:
        from langfuse import Langfuse
        client = Langfuse(
            secret_key=env["LANGFUSE_SECRET_KEY"],
            public_key=env["LANGFUSE_PUBLIC_KEY"],
            host=env["LANGFUSE_BASE_URL"],
        )
    except Exception:
        print("[langfuse] 无法连接，跳过推送")
        return 0

    pushed = 0
    for sample in per_sample:
        trace_id = sample.get("langfuse_trace_id", "")
        if not trace_id:
            continue
        judge_scores: dict = sample.get("judge_scores", {})
        for name, value in judge_scores.items():
            if value is not None:
                try:
                    client.score(
                        trace_id=trace_id,
                        name=name,
                        value=float(value),
                        comment=f"judge_eval_{version}",
                    )
                    pushed += 1
                except Exception:
                    pass

    client.flush()
    return pushed


# ── 报告 ──────────────────────────────────────────────

def generate_report(
    version: str, samples: list[dict], scores: dict, output_dir: str, ts: str
) -> tuple[str, str]:
    """生成 JSON 和 Markdown 报告。返回两个文件路径。"""
    os.makedirs(output_dir, exist_ok=True)

    report = {
        "version": version,
        "generated_at": ts,
        "total_samples": len(samples),
        "scores": scores,
        "per_sample": [
            {"id": s.get("id"), "question": s.get("question", "")[:80],
             "judge_scores": s.get("judge_scores", {}),
             "langfuse_trace_id": s.get("langfuse_trace_id", "")}
            for s in samples
        ],
    }

    json_path = os.path.join(output_dir, f"judge_{version}_{ts}.json")
    with open(json_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Markdown
    md_path = os.path.join(output_dir, f"judge_{version}_{ts}.md")
    with open(md_path, "w") as f:
        f.write(f"# Judge Evaluation — {version}\n\n")
        f.write(f"**Generated**: {ts}\n")
        f.write(f"**Samples**: {len(samples)}\n\n")
        f.write("## Aggregate Scores\n\n")
        f.write("| Metric | Score | Min | Max |\n")
        f.write("|--------|-------|-----|-----|\n")
        for metric, vals in scores.items():
            f.write(f"| {metric} | {vals['aggregate']:.4f} | {vals['min']:.4f} | {vals['max']:.4f} |\n")
        f.write("\n## Per-Sample\n\n")
        for s in report["per_sample"]:
            f.write(f"### {s['id']}. {s['question'][:80]}\n")
            rs = s.get("judge_scores", {})
            f.write("| Metric | Score |\n|--------|-------|\n")
            for k, v in rs.items():
                f.write(f"| {k} | {v:.4f} |\n")
            f.write("\n")

    return json_path, md_path


def generate_compare_report(report_a: dict, report_b: dict, output_dir: str) -> str:
    """生成对比报告。"""
    os.makedirs(output_dir, exist_ok=True)
    va, vb = report_a["version"], report_b["version"]
    md_path = os.path.join(output_dir, f"compare_{va}_vs_{vb}.md")
    ts = time.strftime("%Y%m%d_%H%M%S")

    sa, sb = report_a.get("scores", {}), report_b.get("scores", {})

    with open(md_path, "w") as f:
        f.write(f"# Judge Comparison: {va} → {vb}\n\n")
        f.write(f"**Generated**: {ts}\n\n")
        f.write("| Metric | {va} | {vb} | Diff | Direction |\n")
        f.write("|--------|------|------|------|----------|\n")
        all_metrics = sorted(set(list(sa.keys()) + list(sb.keys())))
        for m in all_metrics:
            a = sa.get(m, {}).get("aggregate", 0)
            b = sb.get(m, {}).get("aggregate", 0)
            diff = b - a
            if diff > 0.02:
                d = "📈 improved"
            elif diff < -0.02:
                d = "📉 regressed"
            else:
                d = "— stable"
            f.write(f"| {m} | {a:.4f} | {b:.4f} | {diff:+.4f} | {d} |\n")

        # Per-sample diff
        f.write("\n## Per-Sample Regression\n\n")
        f.write("| ID | Metric | {va} → {vb} |\n")
        f.write("|----|--------|------------|\n")
        for pa in report_a.get("per_sample", []):
            pid = pa.get("id", "?")
            rs_a = pa.get("judge_scores", {})
            pb = next((x for x in report_b.get("per_sample", []) if x.get("id") == pid), None)
            if not pb:
                continue
            rs_b = pb.get("judge_scores", {})
            for m in all_metrics:
                dv = rs_b.get(m, 0) - rs_a.get(m, 0)
                if abs(dv) > 0.05:
                    f.write(f"| {pid} | {m} | {rs_a.get(m,0):.4f} → {rs_b.get(m,0):.4f} ({dv:+.4f}) |\n")

    return md_path


# ── 主流程 ────────────────────────────────────────────

async def run_eval(args: argparse.Namespace) -> None:
    """执行评估。"""
    testset_path = args.testset or DEFAULT_TEST_SET
    with open(testset_path) as f:
        testset = json.load(f)
    print(f"[eval] 加载测试集: {len(testset)} 条, version={args.version}")

    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient() as client:

        async def eval_one(item: dict) -> dict:
            async with sem:
                result = await call_chat_api(
                    client, args.base_url, item["question"], args.kb_id, args.top_k
                )
                result["id"] = item.get("id", "?")
                result["question"] = item["question"]
                result["ground_truth"] = item.get("expected_answer", "")
                result["contexts"] = [c.get("chunk_text", "") for c in result.get("chunks", [])]
                result["answer"] = result.get("answer", "")
                result["ground_truth"] = item.get("expected_answer", "")
                return result

        tasks = [eval_one(item) for item in testset]
        results = await asyncio.gather(*tasks)

    errors = [r for r in results if r.get("error")]
    valid = [r for r in results if not r.get("error")]
    print(f"[eval] 完成: {len(valid)} 成功, {len(errors)} 失败")

    # Judge 4 维评分
    judge_samples = [
        {
            "id": r["id"],
            "question": r["question"],
            "answer": r["answer"],
            "contexts": r["contexts"],
            "ground_truth": r["ground_truth"],
            "langfuse_trace_id": r.get("langfuse_trace_id", ""),
        }
        for r in valid
    ]
    print(f"[eval] Judge 4 维评分 ({len(judge_samples)} 条)...")
    eval_result = await compute_judge_metrics(judge_samples)

    # 推送 Langfuse（judge 分数 + trace_id 已在 eval_result 中）
    if not args.no_langfuse:
        pushed = push_judge_to_langfuse(eval_result["per_sample"], args.version)
        print(f"[langfuse] 推送 {pushed} 条 score")

    # 报告
    ts = time.strftime("%Y%m%d_%H%M%S")
    json_path, md_path = generate_report(
        args.version, eval_result["per_sample"], eval_result["scores"], args.output, ts
    )
    print(f"[report] JSON: {json_path}")
    print(f"[report] Markdown: {md_path}")

    # 打印汇总
    print("\n  Aggregate scores:")
    for metric, vals in eval_result["scores"].items():
        print(f"    {metric}: {vals['aggregate']:.4f}")


def cmd_compare(args: argparse.Namespace) -> None:
    """对比两个评估报告。"""
    with open(args.report_a) as f:
        report_a = json.load(f)
    with open(args.report_b) as f:
        report_b = json.load(f)
    md_path = generate_compare_report(report_a, report_b, args.output)
    print(f"[compare] 报告: {md_path}")


# ── CLI ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Judge 端到端评估")
    sub = parser.add_subparsers(dest="command")

    # eval
    p_eval = sub.add_parser("eval", help="运行评估")
    p_eval.add_argument("--version", required=True, help="版本标签 (v1-baseline)")
    p_eval.add_argument("--kb-id", required=True, help="知识库 UUID")
    p_eval.add_argument("--testset", default=DEFAULT_TEST_SET, help="测试集 JSON 路径")
    p_eval.add_argument("--base-url", default=DEFAULT_BASE_URL, help="AI service URL")
    p_eval.add_argument("--output", default=DEFAULT_OUTPUT, help="报告输出目录")
    p_eval.add_argument("--top-k", type=int, default=10, help="检索 top_k")
    p_eval.add_argument("--concurrency", type=int, default=4, help="并发数")
    p_eval.add_argument("--no-langfuse", action="store_true", help="跳过 Langfuse 推送")

    # compare
    p_cmp = sub.add_parser("compare", help="对比两个版本")
    p_cmp.add_argument("--report-a", required=True, help="版本 A 的 JSON 报告")
    p_cmp.add_argument("--report-b", required=True, help="版本 B 的 JSON 报告")
    p_cmp.add_argument("--output", default=DEFAULT_OUTPUT, help="输出目录")

    args = parser.parse_args()
    if args.command == "eval":
        asyncio.run(run_eval(args))
    elif args.command == "compare":
        cmd_compare(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
