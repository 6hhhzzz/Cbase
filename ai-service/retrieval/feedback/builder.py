"""Trace 构建器 — 从检索上下文构建结构化 trace dict（纯数据转换，无 I/O）。"""

import time
import uuid
from typing import Any


def _pick_title(source_file: str) -> str:
    """从 source_file 中提取可读标题。"""
    if not source_file:
        return ""
    if "/" in source_file:
        return source_file.rsplit("/", 1)[-1]
    return source_file


def build_trace(
    *,
    query: str,
    rewritten_query: str = "",
    kb_ids: list[str] | None = None,
    keywords: list[str] | None = None,
    ctx=None,  # RetrievalContext
    timings: dict | None = None,
    recall_stats: dict | None = None,
    generated_response: str = "",
    source: str = "web_chat",
    user_id: str = "",
    space_id: str = "",
    session_id: str = "",
    resolved_filters: dict | None = None,
    llm_tokens: dict | None = None,
    trace_ctx=None,  # TraceContext | None (★ v12.2)
) -> dict:
    """从检索上下文构建 7 模块 trace dict。

    Args:
        query: 原始查询
        rewritten_query: 改写/规划后的查询
        kb_ids: 生效的知识库 ID 列表
        keywords: 提取的关键词
        ctx: RetrievalContext（含 chunks + 元数据）
        timings: 各阶段耗时
        recall_stats: 各通道召回数
        generated_response: LLM 生成答案（截断至前 500 字符）
        source: 'web_chat' | 'mcp'
        user_id: 用户标识
        space_id: 空间标识
        session_id: 会话标识
        resolved_filters: 元数据过滤条件
        llm_tokens: LLM token 消耗

    Returns:
        结构化 trace dict
    """
    timings = timings or {}
    recall_stats = recall_stats or {}
    llm_tokens = llm_tokens or {}

    # ---- 模块 1: 基础上下文 ----
    trace: dict[str, Any] = {
        "trace_id": str(uuid.uuid4()),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(source),
        "user_id": str(user_id) if user_id else "",
        "space_id": str(space_id) if space_id else "",
        "session_id": str(session_id) if session_id else "",
    }

    # ---- 模块 2: 查询预处理 ----
    trace.update({
        "original_query": query,
        "rewritten_query": rewritten_query or query,
        "kb_ids": kb_ids or [],
        "keywords": keywords or [],
        "resolved_filters": resolved_filters or {},
    })

    # ---- 模块 3: 检索与重排指标 ----
    retrieval_path = "simple"
    dag_extra = {}
    if ctx is not None and ctx.intent == "complex":
        retrieval_path = "dag"
        sq_count = len(ctx.sub_query_groups) if ctx.sub_query_groups else 0
        dag_extra = {
            "dag_sub_query_count": sq_count,
            "dag_wave_count": 0,
            "circuit_breaker_tripped": False,
        }

    trace.update({
        "retrieval_path": retrieval_path,
        "top_k": len(ctx.chunks) if ctx else 0,
        "min_score": 0.0,
        "latency_breakdown": {
            "hybrid_ms": timings.get("hybrid_ms", 0),
            "rerank_ms": timings.get("rerank_ms", 0),
            "planner_ms": timings.get("planner_ms", 0),
            "total_ms": timings.get("total_ms", 0),
        },
        "recall_stats": {
            "dense_hits": recall_stats.get("dense_hits", 0),
            "bm25_hits": recall_stats.get("bm25_hits", 0),
            "splade_hits": recall_stats.get("splade_hits", 0),
        },
        "reranked_count": ctx.reranked_count if ctx else 0,
        "filtered_count": ctx.filtered_count if ctx else 0,
        "llm_tokens": llm_tokens,
        "extra": dag_extra,
    })

    # ---- 模块 4: 结果快照 ----
    chunks_snapshot = []
    if ctx is not None:
        for c in ctx.chunks[:10]:
            chunks_snapshot.append({
                "chunk_id": c.chunk_id,
                "source_doc_id": c.metadata.get("doc_id", "") if c.metadata else "",
                "doc_title": _pick_title(c.source_file or ""),
                "final_score": round(c.score, 4),
                "content_snippet": (c.content or "")[:150],
            })

    trace["chunks"] = chunks_snapshot

    # ---- 模块 5: 生成内容 ----
    trace["generated_response"] = (generated_response or "")[:500]

    # ---- 模块 6~7: Judge + 反馈（留空） ----
    trace.update({
        "faithfulness_score": None,
        "answer_relevance": None,
        "context_relevance": None,
        "judge_model": None,
        "judge_latency_ms": None,
        "rating": None,
        "feedback_reason": None,
        "feedback_at": None,
    })

    # ---- stages_detail: 兼容旧 trace_detail + 新 TraceContext spans ----
    stages = {}
    # 旧 trace_detail dict
    td = getattr(ctx, 'trace_detail', {}) if ctx else {}
    if td:
        stages = td
    # 新 TraceContext spans（合并到 stages_detail 中，key='spans' 区分来源）
    if trace_ctx is not None:
        tc_dict = trace_ctx.to_trace_dict()
        stages["_trace_spans"] = tc_dict.get("spans", [])
        stages["_trace_id"] = tc_dict["trace_id"]
    trace["stages_detail"] = stages

    return trace
