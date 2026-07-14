"""MCP Tool 实现 — search_chunks / report_quality。

每个 Tool 在执行业务逻辑前强制做权限解析（kb_ids 交集）。
检索链路使用 McpQueryPreparator（纯本地增强） + QueryPlanner（DAG 拆解）
  + RetrievalOrchestrator.execute()（共享执行层）。
"""

import json
import time
from typing import Any

import httpx

from common import get_logger
from retrieval.trace_context import TraceContext
from kes_mcp.auth import (
    KeyAuthError,
    _JAVA_BASE,
)
from retrieval.feedback import RetrievalTracer
from retrieval.mcp_query_preparator import McpQueryPreparator

logger = get_logger(__name__)

# 全局单例
_preparator = McpQueryPreparator()
_tracer: RetrievalTracer | None = None


def _get_tracer(retrieval_orch) -> RetrievalTracer | None:
    """延迟获取或创建 RetrievalTracer（复用 pgvector 连接池）。"""
    global _tracer
    if _tracer is not None:
        return _tracer
    try:
        pool = retrieval_orch._hybrid_search._dense._pgvector.pool
        if pool:
            _tracer = RetrievalTracer(pool=pool)
    except Exception:
        pass
    return _tracer


# ---- 权限解析 ----

async def resolve_kb_ids(context_token: str, space_id: str) -> list[str]:
    """调用 Java 鉴权 API 获取当前用户有权限的 kb_ids。"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_JAVA_BASE}/api/auth/accessible-kbs",
            headers={"Authorization": f"Bearer {context_token}"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"权限查询失败 ({resp.status_code})")
        kbs = resp.json().get("data", [])
        return [kb["kb_id"] for kb in kbs]


def intersect_kb_ids(tool_kb_ids: list[str] | None, ace_kb_ids: list[str],
                      scope_kb_ids: list[str] | None = None) -> list[str]:
    """三层交集——tool ∩ ace ∩ scope，每层只减不增。

    Args:
        tool_kb_ids: Agent 调用时传入的 kb_ids（可选）
        ace_kb_ids:  Java ACE 解析的用户完整权限
        scope_kb_ids: API Key 级别的 KB 白名单（可选）
    """
    if not ace_kb_ids:
        return []
    result = set(ace_kb_ids)
    if tool_kb_ids:
        result &= set(tool_kb_ids)
    if scope_kb_ids:
        result &= set(scope_kb_ids)
    return list(result)


# ---- 共享鉴权解析（search_chunks 等公用）----

async def _resolve_effective_kb_ids(auth, tool_kb_ids: list[str] | None) -> list[str] | None:
    """鉴权 + 三层权限交集。返回 None 表示鉴权失败（调用方自行处理错误消息）。"""
    try:
        token = await auth.ensure_token()
    except KeyAuthError as e:
        return None  # 调用方返回 [{"error": str(e)}]

    try:
        ace_kb_ids = await resolve_kb_ids(token, auth.space_id)
    except Exception as e:
        return None  # 调用方返回 [{"error": f"权限查询失败: {e}"}]

    return intersect_kb_ids(tool_kb_ids, ace_kb_ids, auth.scope_kb_ids)



# ---- 元数据过滤 ----

def _apply_doc_type_filter(chunks: list[dict], doc_type: str | None) -> list[dict]:
    """按文档类型过滤检索结果（简易实现：依赖 chunk metadata 中的 file_type）。"""
    if not doc_type or doc_type == "any":
        return chunks
    return [
        c for c in chunks
        if c.get("metadata", {}).get("doc_type", "").startswith(doc_type)
        or c.get("source", {}).get("filename", "").endswith(_doc_type_ext(doc_type))
    ]


def _doc_type_ext(doc_type: str) -> str:
    """将语义类型映射为常见文件扩展名。"""
    _map = {
        "manual": ".md",
        "specification": ".md",
        "policy": ".md",
        "report": ".docx",
        "guide": ".md",
    }
    return _map.get(doc_type, "")


# ---- Tool: search_chunks ----

async def search_chunks(
    retrieval_orch,
    auth,
    arguments: dict,
) -> list[dict]:
    """混合检索文档块，返回带完整元数据的结构化结果。

    链路: McpQueryPreparator（jieba 关键词提取）
       → QueryPlanner（LLM DAG 拆解，失败自动降级简单路径）
       → RetrievalOrchestrator.execute()（DAG 或简单路径 + 三路混合检索 + Reranker）
    """
    query = arguments.get("query", "")
    kb_ids: list[str] | None = arguments.get("kb_ids")
    top_k: int = max(1, min(30, arguments.get("top_k", 10)))  # 钳位到 1~30
    include_context: bool = arguments.get("include_context", True)
    context_hint: str | None = arguments.get("context_hint")
    focus_aspects: list[str] | None = arguments.get("focus_aspects")
    doc_type: str | None = arguments.get("doc_type")

    if not query.strip():
        return [{"error": "query 不能为空"}]

    # 鉴权 + 三层权限交集
    effective = await _resolve_effective_kb_ids(auth, kb_ids)
    if effective is None:
        return [{"error": "鉴权失败或权限查询异常"}]
    if not effective:
        return [{"total": 0, "chunks": [], "notice": "无权限访问任何匹配的知识库"}]

    # ── TraceContext: MCP 统一追踪 ──
    trace_ctx = TraceContext(
        query=query, source="mcp",
        metadata={"kb_ids": effective, "top_k": top_k,
                   "focus_aspects": focus_aspects, "doc_type": doc_type},
    )

    # MCP 查询准备 — jieba 关键词提取（零 LLM 调用）
    _t_prep_start = time.monotonic()
    prepared = _preparator.prepare(
        query=query,
        top_k=top_k,
        context_hint=context_hint,
        focus_aspects=focus_aspects,
        doc_type=doc_type,
    )

    # ── TraceContext: 记录 MCP 查询准备 ──
    trace_ctx.span("mcp_query_preparation", input={
        "query": query, "top_k": top_k,
        "focus_aspects": focus_aspects, "doc_type": doc_type,
    }).finish(output={
        "resolved_query": prepared.query,
        "keywords": prepared.keywords,
        "prep_ms": int((time.monotonic() - _t_prep_start) * 1000),
    })

    # QueryPlanner — DAG 拆解（复用 Web Chat 的查询规划能力）
    plan = None
    if retrieval_orch._planner is not None:
        try:
            plan = await retrieval_orch._planner.plan(prepared.query, history_len=0)
            logger.info(
                f"MCP QueryPlan: complexity={plan.complexity}, "
                f"sub_queries={len(plan.sub_queries)}"
            )
            trace_ctx.span("query_planner", input={
                "query": prepared.query, "history_len": 0,
            }).finish(output={
                "complexity": plan.complexity,
                "sub_query_count": len(plan.sub_queries) if plan.sub_queries else 0,
                "sub_query_ids": [sq.id for sq in plan.sub_queries] if plan.sub_queries else [],
            })
        except Exception as e:
            logger.warning(f"MCP QueryPlanner 失败，降级简单路径: {e}")
            plan = None

    # 检索执行 — 共享执行层（MCP 路径启用置信度过滤 + DAG 拆解）
    _MCP_MIN_SCORE = 0.3  # MCP 专用阈值：低于此分的 chunk 视为不可信
    _start_retrieval = time.monotonic()
    try:
        ctx = await retrieval_orch.execute(
            query=prepared.query,
            kb_ids=effective,
            keywords=prepared.keywords,
            top_k=prepared.top_k,
            plan=plan,
            min_score=_MCP_MIN_SCORE,
            trace_ctx=trace_ctx,
        )
    except Exception as e:
        logger.error(f"检索失败: {e}")
        return [{"error": f"检索失败: {e}"}]
    _retrieval_ms = int((time.monotonic() - _start_retrieval) * 1000)

    # ---- 检索质量 Trace 构建（MCP 侧：内存缓存 + 采样落库）----
    trace_id = ""
    tracer = _get_tracer(retrieval_orch)
    if tracer is not None:
        try:
            trace = tracer.build_trace(
                query=query,
                rewritten_query=prepared.query,
                kb_ids=effective,
                keywords=prepared.keywords,
                ctx=ctx,
                timings={"total_ms": _retrieval_ms},
                source="mcp",
            )
            trace["min_score"] = _MCP_MIN_SCORE
            trace["top_k"] = prepared.top_k
            if plan is not None:
                trace["retrieval_path"] = plan.complexity
                trace["extra"]["dag_sub_query_count"] = len(plan.sub_queries) if plan.sub_queries else 0

            trace_id = trace["trace_id"]
            if tracer.should_sample():
                await tracer.save_trace(trace)
            else:
                tracer.cache_trace(trace_id, trace)
        except Exception as e:
            logger.warning(f"MCP Trace 构建失败: {e}")

    chunks: list[dict] = []
    for c in ctx.chunks:
        source = {
            "doc_id": c.metadata.get("doc_id", ""),
            "filename": c.source_file,
            "page_range": list(c.page_range) if c.page_range else None,
            "doc_version": c.metadata.get("doc_version"),
            "doc_effective_date": c.metadata.get("doc_effective_date"),
            "doc_expiry_date": c.metadata.get("doc_expiry_date"),
            "is_expired": c.metadata.get("is_expired", False),
        }
        # 清理 None 值
        source = {k: v for k, v in source.items() if v is not None}

        chunks.append({
            "chunk_id": c.chunk_id,
            "content": c.content if include_context else c.content,
            "content_exact": c.content,
            "score": round(c.score, 4),
            "source": source,
            "metadata": {
                "retriever": c.metadata.get("retriever", "fused"),
                "chunk_indexed_at": c.metadata.get("chunk_indexed_at"),
            },
        })

    # 元数据过滤（可选）— 文档类型
    if doc_type and doc_type != "any":
        chunks = _apply_doc_type_filter(chunks, doc_type)

    # 时间范围过滤 — expired 策略
    time_range = arguments.get("time_range", {}) or {}
    expired_strategy = (time_range.get("expired") if isinstance(time_range, dict) else None) or "exclude"
    if expired_strategy == "exclude":
        chunks = [c for c in chunks if not c.get("source", {}).get("is_expired", False)]
    elif expired_strategy == "only":
        chunks = [c for c in chunks if c.get("source", {}).get("is_expired", False)]

    result_data: dict[str, Any] = {
        "total": len(chunks),
        "chunks": chunks,
        "query": query,
    }
    if trace_id:
        result_data["trace_id"] = trace_id
    if prepared.keywords:
        result_data["keywords_applied"] = prepared.keywords
    if ctx.reranked_count > 0:
        result_data["reranked_count"] = ctx.reranked_count
    if ctx.filtered_count > 0:
        result_data["filtered_count"] = ctx.filtered_count

    return [result_data]


# ---- Tool: report_quality ----

async def report_quality(
    retrieval_orch,
    auth,
    arguments: dict,
) -> list[dict]:
    """Agent 上报检索质量反馈。

    从内存缓存中取出 trace，补入 rating + reason，持久化到 PG。

    参数:
        trace_id: search_chunks 返回的 trace_id（必需）
        rating: "like" | "dislike"（必需）
        reason: 可选反馈原因（"答非所问"、"内容过时"、"缺少关键信息" 等）
    """
    trace_id = arguments.get("trace_id", "")
    rating = arguments.get("rating", "")
    reason = arguments.get("reason", "")

    if not trace_id:
        return [{"error": "trace_id 不能为空"}]
    if rating not in ("like", "dislike"):
        return [{"error": "rating 必须为 'like' 或 'dislike'"}]

    tracer = _get_tracer(retrieval_orch)
    if tracer is None:
        return [{"error": "追踪组件未初始化"}]

    # 从缓存取出 trace → 补反馈 → INSERT
    trace = tracer.pop_cached(trace_id)
    if trace is None:
        # 可能已被采样落库，直接 UPDATE
        updated = await tracer.update_feedback(trace_id, rating, reason)
        if not updated:
            return [{"error": f"Trace 不存在或已过期: {trace_id}"}]
        return [{"status": "ok", "trace_id": trace_id, "rating": rating}]

    # 缓存命中：补反馈 → INSERT
    trace["rating"] = rating
    trace["feedback_reason"] = reason
    await tracer.save_trace(trace)
    logger.info(f"MCP 反馈已记录: {trace_id} rating={rating} reason={reason}")

    return [{"status": "ok", "trace_id": trace_id, "rating": rating}]


# ---- Tool: submit_document ----

async def submit_document(
    retrieval_orch,
    auth,
    arguments: dict,
) -> list[dict]:
    """向 KES 提交新文档——仅限 AI 原生 Space。

    流程:
      1. 鉴权 → 拿到 context_token + space_id
      2. 校验 space_type == "ai_native"
      3. 写 content 为临时 .md 文件
      4. 调 Java API 上传
    """
    doc_title = arguments.get("doc_title", "")
    content = arguments.get("content", "")
    summary = arguments.get("summary", "")
    keywords = arguments.get("keywords", [])
    doc_type = arguments.get("doc_type", "manual")
    kb_id = arguments.get("kb_id")

    # 基本校验
    if not doc_title.strip():
        return [{"error": "doc_title 不能为空"}]
    if not content.strip():
        return [{"error": "content 不能为空"}]
    if not summary.strip():
        return [{"error": "summary 不能为空"}]

    # 鉴权 → context_token
    try:
        token = await auth.ensure_token()
    except KeyAuthError as e:
        return [{"error": f"鉴权失败: {e}"}]

    # 校验 space_type — 从 accessible-kbs 响应获取
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{_JAVA_BASE}/api/auth/accessible-kbs",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            return [{"error": f"权限查询失败 ({resp.status_code})"}]

        kbs = resp.json().get("data", [])
        space_type = kbs[0].get("spaceType", "default") if kbs else "default"

        if space_type != "ai_native":
            return [{"error": f"此 Space 类型为 '{space_type}'，不支持 submit_document。仅 AI 原生 Space (ai_native) 支持此功能。"}]

        # 构造 Markdown 文件（加上 frontmatter 元数据）
        frontmatter = "---\n"
        frontmatter += f"title: {doc_title}\n"
        frontmatter += f"doc_type: {doc_type}\n"
        frontmatter += f"keywords: {', '.join(keywords)}\n"
        frontmatter += f"summary: {summary}\n"
        frontmatter += "---\n\n"
        full_content = frontmatter + content

        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(full_content)
            tmp_path = f.name

        try:
            # 调 Java 上传 API
            target_kb = kb_id or (kbs[0].get("kbId") if kbs else None)
            if not target_kb:
                os.unlink(tmp_path)
                return [{"error": "未找到可用的知识库，请先创建 KB 或指定 kb_id"}]

            with open(tmp_path, "rb") as f:
                upload_resp = await client.post(
                    f"{_JAVA_BASE}/api/documents",
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": (f"{doc_title}.md", f, "text/markdown")},
                    data={
                        "kb_id": target_kb,
                        "version": json.dumps({
                            "doc_type": doc_type,
                            "keywords": keywords,
                            "summary": summary,
                        }, ensure_ascii=False),
                    },
                )

            if upload_resp.status_code in (200, 201):
                result = upload_resp.json().get("data", {})
                doc_id = result.get("id", "")
                logger.info(f"MCP 文档提交成功: {doc_title} → doc_id={doc_id}")
                return [{"status": "ok", "doc_id": doc_id, "kb_id": target_kb,
                         "message": f"文档「{doc_title}」已提交，等待入库处理"}]
            else:
                return [{"error": f"上传失败 ({upload_resp.status_code}): {upload_resp.text[:200]}"}]
        finally:
            os.unlink(tmp_path)
