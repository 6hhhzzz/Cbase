"""DAGExecutor — DAG 执行 + 3D 提取 + HyDE + 熔断。

从 orchestrator.py 提取，封装为独立类，通过构造函数注入共享依赖。
"""

import asyncio
import json
import re
import time
from typing import Any

from common import get_logger
from common.utils import tokenize_chinese
from llm.base import BaseLLM
from llm.prompts.hyde import HYDE_PROMPT
from .circuit_breaker import DAGCircuitBreaker
from .dedup import merge_dedup, dedup_chunks, dedup_docs, merge_adjacent
from .hybrid_search import HybridSearch
from .models import (
    RetrievalContext, ScoredChunk, SubQuery, UpstreamContext, QueryPlan,
)
from .reranker import Reranker
from .trace_context import SpanSnapshot

logger = get_logger(__name__)

# Token / DAG 预算常量
PARENT_MAX_TOKENS = 1000
CHAPTER_BUDGET_TOKENS = 800
MAX_DAG_TOTAL_CHUNKS = 30


# ================================================================
# 3D 提取 + 证据校验 + 模板注入
# ================================================================

class ThreeDExtractor:
    """三维提取器 — SLM 一次调用提取 entities / reasoning_state / filters。"""

    def __init__(self, slm: BaseLLM):
        self._slm = slm

    async def extract_upstream_context(
        self,
        sub_query: SubQuery,
        upstream_chunks: list[ScoredChunk],
    ) -> UpstreamContext:
        """从上游检索结果提取三维信息。"""
        if not upstream_chunks:
            return UpstreamContext()

        chunk_texts = "\n---\n".join(
            f"[{c.source_file}] {c.content[:300]}" for c in upstream_chunks[:2]
        )

        entities_desc = ""
        if sub_query.extract_entities:
            entities_desc = "\n".join(
                f"  - {e['key']}: {e.get('description', e['key'])}"
                for e in sub_query.extract_entities
            )

        reasoning_desc = sub_query.extract_reasoning or "不需要"
        filters_desc = ", ".join(sub_query.extract_filters) if sub_query.extract_filters else "不需要"

        prompt = f"""你是一个信息提取助手。从以下上游检索结果中提取三类信息。

上游检索结果：
{chunk_texts}

## 提取任务

1. 实体提取：
{entities_desc if entities_desc else "不需要"}

2. 推理中间态提取：
{reasoning_desc}

3. 元数据约束提取：
{filters_desc}

## 铁律
- 如果上游 Chunks 中不存在目标实体，值必须设为 null，严禁猜测。
- 每个实体必须附带原文证据片段（evidence）。

## 输出 JSON
{{{{
  "entities": {{{{
    "key1": {{{{ "value": "提取值", "evidence": "原文证据片段" }}}},
    "key2": {{{{ "value": null, "evidence": null }}}}
  }}}},
  "reasoning_state": "推理背景（不需要则为空字符串）",
  "filters": {{}}
}}

只返回 JSON："""

        try:
            response_wrapper = await self._slm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )

            response = response.strip()
            if response.startswith("```"):
                response = re.sub(r"^```(?:json)?\s*", "", response)
                response = re.sub(r"\s*```$", "", response)

            data = json.loads(response)

            entities = {}
            raw_entities = data.get("entities", {})
            for key, entry in raw_entities.items():
                if isinstance(entry, dict) and entry.get("value"):
                    entities[key] = str(entry["value"])

            return UpstreamContext(
                entities=entities,
                reasoning_state=data.get("reasoning_state", ""),
                filters=data.get("filters", {}),
            )

        except Exception as e:
            logger.warning(f"三维提取失败: {e}")
            entities = {}
            if sub_query.extract_entities and upstream_chunks:
                tokens = tokenize_chinese(upstream_chunks[0].content).split()[:5]
                for ent in sub_query.extract_entities:
                    entities[ent["key"]] = " ".join(tokens)
            return UpstreamContext(
                entities=entities,
                reasoning_state=upstream_chunks[0].content[:200] if upstream_chunks else "",
                filters={},
            )

    def validate_evidence(
        self, entities: dict[str, str], raw_chunks: list[str]
    ) -> dict[str, str]:
        """证据锚点校验 — 检查提取的实体是否有原文支撑。"""
        validated = {}
        for key, value in entities.items():
            if not value:
                continue
            found = any(value in c or c in value for c in raw_chunks)
            if found:
                validated[key] = value
            else:
                logger.warning(f"实体 {key}={value} 证据校验失败，判定为幻觉")
        return validated

    @staticmethod
    def fill_template(template: str, entities: dict[str, str]) -> str:
        """模板变量注入 — 用实体填充 query_template。"""
        result = template
        for key, value in entities.items():
            placeholder = "{{extracted." + key + "}}"
            result = result.replace(placeholder, value)
        result = re.sub(r"\{\{extracted\.\w+\}\}", "", result).strip()
        return result or " ".join(entities.values())


# ================================================================
# DAG Executor
# ================================================================

def _chunk_snapshot(c: ScoredChunk, include_snippet: bool = True) -> dict:
    """将 ScoredChunk 序列化为 trace 用的精简 dict（本地副本，避免循环导入）。"""
    d = {
        "chunk_id": c.chunk_id,
        "doc_id": c.metadata.get("doc_id", "") if c.metadata else "",
        "doc_title": c.source_file or "",
        "score": round(c.score, 4),
    }
    if include_snippet:
        d["snippet"] = (c.content or "")[:150]
    return d


class DAGExecutor:
    """DAG 检索执行器。

    封装：简单检索、多路检索、DAG 执行、HyDE、3D 提取、熔断、合并重排。
    通过构造函数注入共享依赖，无 orchestrator 状态耦合。
    """

    def __init__(
        self,
        hybrid_search: HybridSearch,
        reranker: Reranker,
        llm: BaseLLM,
        slm: BaseLLM | None = None,
        tracer: Any = None,
    ):
        self._hybrid_search = hybrid_search
        self._reranker = reranker
        self._llm = llm
        self._slm = slm or llm
        self._tracer = tracer
        self._extractor = ThreeDExtractor(self._slm)


    async def execute_simple(
        self,
        query: str,
        kb_ids: list[str],
        keywords: list[str],
        top_k: int,
        min_score: float,
        use_hyde: bool = False,
        trace_ctx = None,  # TraceContext | None
    ) -> "RetrievalContext":
        """单次检索 — 简单查询路径（可选 HyDE）。"""
        _t0 = time.monotonic()
        # ★ use_hyde=True 时走 HyDE 桥接术语差异
        all_chunks = await self._search_with_hyde(
            original_query=query,
            search_query=query,
            kb_ids=kb_ids,
            top_k=top_k * 2,
            keywords=keywords,
            use_hyde=use_hyde,
            trace_ctx=trace_ctx,
        )
        _t_hybrid = time.monotonic()

        stats = self._hybrid_search.last_stats.copy()
        splade_degraded = (stats.get("splade_hits", 0) == 0 and
                           getattr(self._hybrid_search._sparse, "_splade_available", True) is False)

        if not all_chunks:
            logger.warning(f"检索无结果: query='{query[:50]}'")
            return RetrievalContext(
                query=query, chunks=[], keywords=keywords,
                trace_detail={"retrieval": {
                    "path": "simple",
                    "simple": {
                        "dense_hits": stats.get("dense_hits", 0),
                        "bm25_hits": stats.get("bm25_hits", 0),
                        "splade_hits": stats.get("splade_hits", 0),
                        "splade_degraded": splade_degraded,
                        "candidates_before_rerank": 0,
                        "reranker_method": "none", "reranker_ms": 0,
                        "final_count": 0, "filtered_count": 0,
                        "hybrid_search_ms": int((_t_hybrid - _t0) * 1000),
                        "chunks": [],
                    },
                }}
            )

        all_chunks = dedup_chunks(all_chunks)
        deduped = dedup_docs(all_chunks)
        deduped = merge_adjacent(deduped)
        if len(deduped) >= top_k * 2:
            all_chunks = deduped

        # ★ parent-child: 用 parent 全文替换 child 片段
        all_chunks = _resolve_parents(all_chunks, query)

        reranked = await self._reranker.rerank(query, all_chunks, top_n=top_k)
        _t_rerank = time.monotonic()

        # ── TraceContext: 记录 reranker 节点 ──
        if trace_ctx is not None:
            rerank_h = trace_ctx.span("reranker", input={
                "query": query, "candidates": len(all_chunks),
                "strategy": getattr(self._reranker, "_last_strategy", "unknown"),
            })
            rerank_h.finish(output={
                "result_count": len(reranked),
                "chunk_ids": [c.chunk_id for c in reranked],
                "method": getattr(self._reranker, "_last_strategy", "unknown"),
                "rerank_ms": int((_t_rerank - _t_hybrid) * 1000),
            })

        _step_timings = {
            "hybrid_ms": int((_t_hybrid - _t0) * 1000),
            "rerank_ms": int((_t_rerank - _t_hybrid) * 1000),
        }
        reranked_count = len(reranked)

        if min_score > 0:
            filtered = [c for c in reranked if c.score >= min_score]
            filtered_count = reranked_count - len(filtered)
        else:
            filtered = reranked
            filtered_count = 0

        reranker_method = getattr(self._reranker, "_last_strategy", "unknown")

        logger.info(
            f"简单检索完成: query='{query[:50]}', "
            f"candidates={len(all_chunks)}, reranked={reranked_count}, returned={len(filtered)}"
        )

        return RetrievalContext(
            query=query, chunks=filtered, keywords=keywords,
            reranked_count=reranked_count, filtered_count=filtered_count,
            recall_stats=stats, timings=_step_timings,
            trace_detail={"retrieval": {
                "path": "simple",
                "simple": {
                    "dense_hits": stats.get("dense_hits", 0),
                    "bm25_hits": stats.get("bm25_hits", 0),
                    "splade_hits": stats.get("splade_hits", 0),
                    "splade_degraded": splade_degraded,
                    "candidates_before_rerank": len(all_chunks),
                    "reranker_method": reranker_method,
                    "reranker_ms": _step_timings["rerank_ms"],
                    "final_count": len(filtered), "filtered_count": filtered_count,
                    "hybrid_search_ms": _step_timings["hybrid_ms"],
                    "chunks": [_chunk_snapshot(c) for c in filtered],
                },
            }},
        )

    async def execute_simple_multi(
        self,
        query: str,
        kb_ids: list[str],
        keywords: list[str],
        top_k: int,
        sub_queries: list[str],
        min_score: float,
        trace_ctx = None,  # TraceContext | None
    ) -> "RetrievalContext":
        """多路检索 — 向后兼容旧 sub_queries (list[str])。"""
        tasks = [
            self._hybrid_search.search(sq, kb_ids, max(top_k, 5) * 2, keywords,
                                        trace_ctx=trace_ctx)
            for sq in sub_queries
        ]
        wave_results = await asyncio.gather(*tasks)

        all_chunks: list[ScoredChunk] = []
        sub_query_groups: dict[str, list[str]] = {}
        total_stats = {"dense_hits": 0, "bm25_hits": 0, "splade_hits": 0}

        for sq, chunks in zip(sub_queries, wave_results):
            chunk_ids = [c.chunk_id for c in chunks]
            sub_query_groups[sq] = chunk_ids
            all_chunks.extend(chunks)
            s = self._hybrid_search.last_stats
            total_stats["dense_hits"] += s.get("dense_hits", 0)
            total_stats["bm25_hits"] += s.get("bm25_hits", 0)
            total_stats["splade_hits"] += s.get("splade_hits", 0)

        merged = merge_dedup(all_chunks)
        merged = dedup_chunks(merged)
        deduped = dedup_docs(merged)
        deduped = merge_adjacent(deduped)
        if len(deduped) >= top_k * 2:
            merged = deduped

        if not merged:
            logger.warning(f"多路检索无结果: query='{query[:50]}'")
            return RetrievalContext(
                query=query, chunks=[], keywords=keywords,
                sub_query_groups=sub_query_groups, recall_stats=total_stats,
                trace_detail={"retrieval": {"path": "simple_multi"}},
            )

        reranked = await self._reranker.rerank(query, merged, top_n=top_k)
        reranked_count = len(reranked)

        if min_score > 0:
            filtered = [c for c in reranked if c.score >= min_score]
            filtered_count = reranked_count - len(filtered)
        else:
            filtered = reranked
            filtered_count = 0

        return RetrievalContext(
            query=query, chunks=filtered, keywords=keywords,
            reranked_count=reranked_count, filtered_count=filtered_count,
            sub_query_groups=sub_query_groups, recall_stats=total_stats,
        )

    async def execute_dag(
        self,
        plan: QueryPlan,
        kb_ids: list[str],
        keywords: list[str],
        top_k: int,
        min_score: float,
        trace_ctx = None,  # TraceContext | None
    ) -> RetrievalContext:
        """DAG 执行 — 拓扑排序 → wave 并行/串行 → 合并 → Rerank。"""
        sub_queries = plan.sub_queries
        waves = self._topological_sort(sub_queries)
        breaker = DAGCircuitBreaker()

        logger.info(
            f"DAG 执行: query='{plan.rewritten_query[:50]}', "
            f"sub_queries={len(sub_queries)}, waves={len(waves)}"
        )

        sub_results: dict[str, list[ScoredChunk]] = {}
        upstream_contexts: dict[str, UpstreamContext] = {}
        all_chunks: list[ScoredChunk] = []
        sub_query_groups: dict[str, list[str]] = {}
        dag_recall = {"dense_hits": 0, "bm25_hits": 0, "splade_hits": 0}

        _sq_handles: dict[str, Any] = {}  # sub-query id → SpanHandle（供 trace_ctx 依赖嵌套）

        trace_waves: list[dict] = []
        breaker_tripped_at_wave = -1
        breaker_trip_reason = ""

        for wave_idx, wave in enumerate(waves):
            if breaker.tripped:
                logger.warning(f"DAG 熔断: {breaker.trip_reason}，打包已有结果")
                breaker_tripped_at_wave = wave_idx
                breaker_trip_reason = breaker.trip_reason
                break

            logger.debug(f"Wave {wave_idx}: {[sq.id for sq in wave]}")

            tasks = []
            _task_meta = []
            wave_sq_traces: list[dict] = []

            for sq in wave:
                effective_query = sq.query
                sq_trace: dict[str, Any] = {
                    "id": sq.id,
                    "purpose": sq.purpose or "",
                    "dependencies": list(sq.depends_on) if sq.depends_on else [],
                    "needs_context": sq.needs_context,
                    "hyde_used": False,
                    "extraction": {},
                    "hyde": {"used": False, "ms": 0},
                    "search": {"dense_hits": 0, "bm25_hits": 0, "splade_hits": 0,
                               "splade_degraded": False, "chunks": [], "search_ms": 0},
                }

                _t_extract_ms = 0
                if sq.needs_context and sq.depends_on:
                    raw_chunks: list[str] = []
                    context_chunks: list[ScoredChunk] = []
                    for dep_id in sq.depends_on:
                        if dep_id in sub_results:
                            context_chunks.extend(sub_results[dep_id][:2])

                    if context_chunks:
                        raw_chunks = [c.content for c in context_chunks]

                        _t_ext_start = time.monotonic()
                        upstream_ctx = await self._extractor.extract_upstream_context(sq, context_chunks)
                        _t_extract_ms = int((time.monotonic() - _t_ext_start) * 1000)
                        upstream_contexts[sq.id] = upstream_ctx

                        entities = self._extractor.validate_evidence(upstream_ctx.entities, raw_chunks)

                        sq_trace["extraction"] = {
                            "entities": dict(entities) if entities else {},
                            "evidence_valid": bool(entities),
                            "ms": _t_extract_ms,
                        }

                        if not entities:
                            logger.warning(f"  {sq.id}: 关键实体提取为空，跳过")
                            breaker.check_extract_failure({})
                            sub_results[sq.id] = []
                            wave_sq_traces.append(sq_trace)
                            continue

                        breaker.check_extract_failure(entities)

                        effective_query = self._extractor.fill_template(sq.query_template, entities)

                        if upstream_ctx.reasoning_state:
                            effective_query = (
                                effective_query + " " + upstream_ctx.reasoning_state[:200]
                            )

                # ── TraceContext: 提前创建 dag_sub_query span（供 search 内部挂载子节点）──
                sq_h: Any = None
                _use_hyde = sq.hyde
                if trace_ctx is not None:
                    sq_parent_h = None
                    if sq.depends_on:
                        for dep_id in sq.depends_on:
                            if dep_id in _sq_handles:
                                sq_parent_h = _sq_handles[dep_id]
                                break
                    if sq_parent_h is not None:
                        sq_h = sq_parent_h.child("dag_sub_query", input={
                            "sub_query_id": sq.id,
                            "query": sq.query or effective_query,
                            "depends_on": list(sq.depends_on) if sq.depends_on else [],
                            "needs_context": sq.needs_context,
                            "hyde_used": _use_hyde,
                        })
                    else:
                        sq_h = trace_ctx.span("dag_sub_query", input={
                            "sub_query_id": sq.id,
                            "query": sq.query or effective_query,
                            "depends_on": list(sq.depends_on) if sq.depends_on else [],
                            "needs_context": sq.needs_context,
                            "hyde_used": _use_hyde,
                        })
                    _sq_handles[sq.id] = sq_h

                sub_top_k = max(top_k, 5)
                _t_sq_search_start = time.monotonic()
                tasks.append(
                    self._search_with_hyde(
                        original_query=sq.query or effective_query,
                        search_query=effective_query,
                        kb_ids=kb_ids,
                        top_k=sub_top_k * 2,
                        keywords=keywords,
                        use_hyde=sq.hyde,
                        trace_ctx=trace_ctx,
                        parent_h=sq_h,
                    )
                )
                _task_meta.append((sq_trace, _t_sq_search_start, sq.hyde))

            wave_results = await asyncio.gather(*tasks)

            for i, (sq, chunks) in enumerate(zip(wave, wave_results)):
                sq_trace, _t_start, _use_hyde = _task_meta[i]
                sq_trace["search"]["search_ms"] = int((time.monotonic() - _t_start) * 1000)
                sq_trace["hyde"]["used"] = _use_hyde
                if sq_trace["hyde"]["used"]:
                    sq_trace["hyde"]["ms"] = sq_trace["search"]["search_ms"]

                sub_results[sq.id] = chunks
                all_chunks.extend(chunks)
                sub_query_groups[sq.id] = [c.chunk_id for c in chunks]

                s = self._hybrid_search.last_stats
                dag_recall["dense_hits"] += s.get("dense_hits", 0)
                dag_recall["bm25_hits"] += s.get("bm25_hits", 0)
                dag_recall["splade_hits"] += s.get("splade_hits", 0)

                sq_trace["search"]["dense_hits"] = s.get("dense_hits", 0)
                sq_trace["search"]["bm25_hits"] = s.get("bm25_hits", 0)
                sq_trace["search"]["splade_hits"] = s.get("splade_hits", 0)
                sq_trace["search"]["chunks"] = [
                    {"chunk_id": c.chunk_id, "score": round(c.score, 4),
                     "doc_title": c.source_file or "",
                     "doc_id": c.metadata.get("doc_id", "") if c.metadata else ""}
                    for c in chunks
                ]

                breaker.check_empty(not chunks)
                breaker.check_timeout()

                # ── TraceContext: 完成 dag_sub_query span（已在 wave 循环中创建）──
                sq_h = _sq_handles.get(sq.id) if trace_ctx is not None else None
                if sq_h is not None:
                    # 3D 提取子 span（仅当有提取结果时）
                    extraction = sq_trace.get("extraction", {})
                    if extraction.get("entities"):
                        sq_h._snapshot.children.append(SpanSnapshot(
                            node="three_d_extraction",
                            input={"upstream_chunk_ids": [c.chunk_id for c in sub_results.get(sq.depends_on[0], [])[:2]] if sq.depends_on else []},
                            output={"entities": extraction["entities"], "evidence_valid": extraction.get("evidence_valid", False)},
                            timing_ms=extraction.get("ms", 0),
                        ))
                    # HyDE 子 span
                    if _use_hyde:
                        sq_h._snapshot.children.append(SpanSnapshot(
                            node="hyde_generation",
                            input={"query": sq.query or effective_query},
                            output={"generated": True},
                        ))
                    sq_h.finish(output={
                        "chunks_found": len(chunks),
                        "chunk_ids": [c.chunk_id for c in chunks],
                        "dense_hits": s.get("dense_hits", 0),
                        "bm25_hits": s.get("bm25_hits", 0),
                        "splade_hits": s.get("splade_hits", 0),
                        "search_ms": sq_trace["search"]["search_ms"],
                    })

                wave_sq_traces.append(sq_trace)

            trace_waves.append({"wave_index": wave_idx, "sub_queries": wave_sq_traces})

        # ── TraceContext: 熔断器状态 ──
        if trace_ctx is not None:
            trace_ctx.span("circuit_breaker", input={
                "waves_total": len(waves),
                "empty_streak_max": breaker._max_empty_streak,
                "timeout_ms": breaker.total_timeout_ms,
            }).finish(output={
                "tripped": breaker.tripped,
                "reason": breaker_trip_reason,
                "at_wave": breaker_tripped_at_wave,
            })

        # 合并去重
        _t_merge_start = time.monotonic()
        merged = merge_dedup(all_chunks)
        dedup_removed = len(all_chunks) - len(merged)

        # ── TraceContext: 融合节点 ──
        if trace_ctx is not None:
            trace_ctx.span("hybrid_fusion", input={
                "before_count": len(all_chunks),
                "sub_query_count": len(sub_queries),
            }).finish(output={
                "after_count": len(merged),
                "dedup_removed": dedup_removed,
                "merge_ms": int((time.monotonic() - _t_merge_start) * 1000),
            })

        if len(merged) > MAX_DAG_TOTAL_CHUNKS:
            merged = merged[:MAX_DAG_TOTAL_CHUNKS]
        _t_merge_ms = int((time.monotonic() - _t_merge_start) * 1000)

        if not merged:
            logger.warning(f"DAG 检索无结果: query='{plan.rewritten_query[:50]}'")
            return RetrievalContext(
                query=plan.rewritten_query, chunks=[], keywords=keywords,
                sub_query_groups=sub_query_groups, upstream_contexts=upstream_contexts,
                recall_stats=dag_recall,
                trace_detail={"retrieval": {
                    "path": "dag",
                    "dag": {
                        "wave_count": len(waves), "total_sub_queries": len(sub_queries),
                        "circuit_breaker": {"tripped": breaker.tripped,
                            "reason": breaker_trip_reason, "at_wave": breaker_tripped_at_wave},
                        "waves": trace_waves,
                        "merge_ms": _t_merge_ms, "dedup_removed": dedup_removed,
                        "reranker_method": "none", "reranker_ms": 0,
                        "final_chunks": [],
                    },
                }},
            )

        # ★ parent-child: 用 parent 全文替换 child 片段
        merged = _resolve_parents(merged, plan.rewritten_query)

        # 三层去重
        merged = dedup_chunks(merged)
        deduped = dedup_docs(merged)
        deduped = merge_adjacent(deduped)
        if len(deduped) >= top_k * 2:
            merged = deduped

        # Reranker
        _t_rerank_start = time.monotonic()
        reranked = await self._reranker.rerank(plan.rewritten_query, merged, top_n=top_k)
        _t_rerank_ms = int((time.monotonic() - _t_rerank_start) * 1000)
        reranked_count = len(reranked)
        reranker_method = getattr(self._reranker, "_last_strategy", "unknown")

        if min_score > 0:
            filtered = [c for c in reranked if c.score >= min_score]
            filtered_count = reranked_count - len(filtered)
        else:
            filtered = reranked
            filtered_count = 0

        _quality_warning = None
        if reranked:
            _top_rerank = reranked[0].score
            if _top_rerank < 0.3:
                _quality_warning = f"reranker top-1 分数过低 ({_top_rerank:.3f})"
            elif all(c.score < 0.3 for c in reranked):
                _quality_warning = "所有重排分数 < 0.3"
        elif not merged:
            _quality_warning = "合并后无候选 chunk"

        logger.info(
            f"DAG 检索完成: query='{plan.rewritten_query[:50]}', "
            f"waves={len(waves)}, total_chunks={len(all_chunks)}, "
            f"merged={len(merged)}, reranked={reranked_count}, returned={len(filtered)}"
        )

        return RetrievalContext(
            query=plan.rewritten_query,
            chunks=filtered,
            keywords=plan.keywords if plan.keywords else keywords,
            reranked_count=reranked_count,
            filtered_count=filtered_count,
            sub_query_groups=sub_query_groups,
            upstream_contexts=upstream_contexts,
            recall_stats=dag_recall,
            trace_detail={"retrieval": {
                "path": "dag",
                "dag": {
                    "wave_count": len(waves),
                    "total_sub_queries": len(sub_queries),
                    "circuit_breaker": {
                        "tripped": breaker.tripped,
                        "reason": breaker_trip_reason,
                        "at_wave": breaker_tripped_at_wave,
                    },
                    "waves": trace_waves,
                    "merge_ms": _t_merge_ms, "dedup_removed": dedup_removed,
                    "reranker_method": reranker_method, "reranker_ms": _t_rerank_ms,
                    "final_count": len(filtered), "filtered_count": filtered_count,
                    "final_chunks": [
                        {"chunk_id": c.chunk_id, "doc_id": c.metadata.get("doc_id", "") if c.metadata else "",
                         "doc_title": c.source_file or "", "score": round(c.score, 4),
                         "snippet": (c.content or "")[:150]}
                        for c in filtered
                    ],
                    "quality_warning": _quality_warning,
                },
            }},
        )

    # ================================================================
    # DAG 工具方法
    # ================================================================

    def _topological_sort(self, sub_queries: list[SubQuery]) -> list[list[SubQuery]]:
        """拓扑排序 — Kahn 算法，将子查询按依赖关系分 wave。"""
        id_to_sq = {sq.id: sq for sq in sub_queries}
        in_degree = {sq.id: len(sq.depends_on) for sq in sub_queries}
        dependents: dict[str, list[str]] = {sq.id: [] for sq in sub_queries}

        for sq in sub_queries:
            for dep_id in sq.depends_on:
                if dep_id in dependents:
                    dependents[dep_id].append(sq.id)

        waves: list[list[SubQuery]] = []
        remaining = set(sq.id for sq in sub_queries)

        while remaining:
            wave_ids = [sid for sid in remaining if in_degree[sid] == 0]
            if not wave_ids:
                logger.error(f"DAG 拓扑排序失败: 剩余节点 {remaining} 存在未解决的依赖")
                break

            wave = [id_to_sq[sid] for sid in sorted(wave_ids)]
            waves.append(wave)

            for sid in wave_ids:
                remaining.remove(sid)
                for dep_id in dependents.get(sid, []):
                    in_degree[dep_id] -= 1

        return waves

    async def _search_with_hyde(
        self,
        original_query: str,
        search_query: str,
        kb_ids: list[str],
        top_k: int,
        keywords: list[str],
        use_hyde: bool,
        trace_ctx = None,       # TraceContext | None
        parent_h = None,        # SpanHandle | None — DAG 子查询 handle
    ) -> list[ScoredChunk]:
        """执行单次检索（含可选 HyDE）。"""
        if use_hyde:
            hyde_doc = await self._generate_hyde(original_query)
            if hyde_doc:
                logger.debug(f"HyDE: '{original_query[:30]}' → 假答案已生成")
                return await self._hybrid_search.search(
                    hyde_doc, kb_ids, top_k, keywords,
                    trace_ctx=trace_ctx, parent_h=parent_h,
                )

        return await self._hybrid_search.search(
            search_query, kb_ids, top_k, keywords,
            trace_ctx=trace_ctx, parent_h=parent_h,
        )

    async def _generate_hyde(self, query: str) -> str | None:
        """生成 HyDE 假答案 — LLM 写一段 100-200 字技术文档风格段落。"""
        try:
            prompt = HYDE_PROMPT.render(query=query)
            response_wrapper = await self._llm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )
            if response and len(response.strip()) > 20:
                return response.strip()
        except Exception as e:
            logger.warning(f"HyDE 生成失败: {e}")
        return None

    async def rewrite_with_context(
        self, query: str, context_chunks: list[ScoredChunk]
    ) -> str:
        """用前一步检索结果改写当前子查询（串行依赖）。"""
        if not context_chunks:
            return query

        context_text = "\n---\n".join(c.content[:300] for c in context_chunks[:3])

        try:
            prompt = (
                f"根据以下检索到的背景信息，将用户问题改写为更精确的搜索查询。"
                f"只输出改写后的查询文本，不要解释。\n\n"
                f"背景信息：\n{context_text}\n\n"
                f"用户问题：{query}\n\n"
                f"改写后的搜索查询："
            )
            response_wrapper = await self._llm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )
            if response and len(response.strip()) > 3:
                return response.strip()[:200]
        except Exception as e:
            logger.warning(f"needs_context 改写失败: {e}")

        return query


# ═══════════════════════════════════════════════════════════
# Parent-Child 解析 — 两级分块检索支持
# ═══════════════════════════════════════════════════════════

def _resolve_parents(chunks: list, query: str = "") -> list:
    """将 child chunk 替换为 parent 全文，按 parent_id 去重。

    每个 child chunk 的 metadata 中存储了 parent_content（父 chunk 完整内容）。
    相同 parent_id 的多个 child → 只保留一个，content 设为 parent 全文。
    """
    if not chunks:
        return chunks

    parent_seen: set[str] = set()
    resolved = []

    for c in chunks:
        meta = c.metadata if hasattr(c, "metadata") else {}
        parent_id = meta.get("parent_id")
        parent_content = meta.get("parent_content")

        if parent_id and parent_content:
            if parent_id in parent_seen:
                continue
            parent_seen.add(parent_id)
            c.content = parent_content
            c.title = meta.get("parent_title", c.title) if hasattr(c, "title") else None

        resolved.append(c)

    if parent_seen:
        logger.debug(
            f"_resolve_parents: {len(chunks)} children → "
            f"{len(resolved)} chunks ({len(parent_seen)} unique parents)"
        )

    return resolved
