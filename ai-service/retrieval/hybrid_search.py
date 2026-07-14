"""HybridSearch — 混合检索（Dense + BM25 → RRF 融合, v12）。

两路并行检索 + RRF 融合：
  - Dense: 稠密向量语义检索（HNSW cosine）
  - BM25: jieba 分词 tsquery 关键词检索

TraceContext 集成：当传入 trace_ctx 时，记录三路子 span：
  hybrid_search
   ├── dense_search    (输入 query/top_k，输出 hits/chunk_ids)
   ├── sparse_search   (输入 query/top_k/keywords，输出 hits/chunk_ids)
   └── rrf_fusion      (输入两路命中数，输出合并后 chunk_ids)
"""

import asyncio
import time
from typing import Any

from common import get_logger
from .dense import DenseRetriever
from .sparse import SparseRetriever
from .fusion import Fusion
from .models import ScoredChunk

logger = get_logger(__name__)


class HybridSearch:
    """两路混合检索器。

    并行执行 Dense、BM25 两路检索，然后用 RRF 融合结果。
    """

    def __init__(
        self,
        dense: DenseRetriever,
        sparse: SparseRetriever,
        fusion: Fusion | None = None,
    ):
        self._dense = dense
        self._sparse = sparse
        self._fusion = fusion or Fusion()
        self.last_stats: dict[str, int] = {}  # {dense_hits, bm25_hits}

    async def search(
        self,
        query: str,
        kb_ids: list[str],
        top_k: int = 10,
        keywords: list[str] | None = None,
        excluded_doc_ids: list[str] | None = None,
        trace_ctx: Any = None,       # TraceContext | None
        parent_h: Any = None,        # SpanHandle | None — 父 span（如 DAG 的 dag_sub_query）
    ) -> list[ScoredChunk]:
        """执行两路混合检索。

        并行执行 Dense、BM25，各取 top_k * 3 候选，
        然后 RRF 融合到 top_k * 2（给 Reranker 留足候选）。

        Args:
            query: 查询文本
            kb_ids: 权限过滤 kb_id 列表
            top_k: 最终期望结果数
            keywords: 额外关键词（BM25 用）
            excluded_doc_ids: 排除的文档 ID
            trace_ctx: 可选 TraceContext，传入时记录 dense_search/sparse_search/rrf_fusion 子 span
            parent_h: 可选父 SpanHandle，用于 DAG 子查询下挂载（dag_sub_query → hybrid_search）

        Returns:
            融合后的 ScoredChunk 列表
        """
        if not query.strip() and not keywords:
            return []

        candidate_k = top_k * 3  # 取更多候选给 RRF 融合

        # ── TraceContext: 创建 hybrid_search 父 span ──
        _has_trace = trace_ctx is not None
        hs_h: Any = None
        if _has_trace:
            if parent_h is not None:
                hs_h = parent_h.child("hybrid_search", input={
                    "query": query, "top_k": top_k * 2, "kb_ids": kb_ids,
                    "keywords": keywords,
                })
            else:
                hs_h = trace_ctx.span("hybrid_search", input={
                    "query": query, "top_k": top_k * 2, "kb_ids": kb_ids,
                    "keywords": keywords,
                })

        # 两路并行执行
        _t0 = time.monotonic()
        dense_future = asyncio.create_task(
            self._dense.search(query, kb_ids, candidate_k, excluded_doc_ids)
        )
        bm25_future = asyncio.create_task(
            self._sparse.search(query, kb_ids, candidate_k, keywords, excluded_doc_ids)
        )

        dense_results = await dense_future
        _t_dense = time.monotonic()
        bm25_results = await bm25_future
        _t_sparse = time.monotonic()

        # ── TraceContext: dense_search 子 span ──
        if _has_trace:
            hs_h._snapshot.children.append(type(hs_h._snapshot)(
                node="dense_search",
                input={"query": query, "top_k": candidate_k, "kb_ids": kb_ids},
                output={
                    "hits": len(dense_results),
                    "chunk_ids": [c.chunk_id for c in dense_results],
                    "search_ms": int((_t_dense - _t0) * 1000),
                },
                timing_ms=int((_t_dense - _t0) * 1000),
            ))

        # ── TraceContext: sparse_search 子 span ──
        if _has_trace:
            hs_h._snapshot.children.append(type(hs_h._snapshot)(
                node="sparse_search",
                input={"query": query, "top_k": candidate_k, "kb_ids": kb_ids,
                       "keywords": keywords or []},
                output={
                    "hits": len(bm25_results),
                    "chunk_ids": [c.chunk_id for c in bm25_results],
                    "search_ms": int((_t_sparse - _t_dense) * 1000),
                },
                timing_ms=int((_t_sparse - _t_dense) * 1000),
            ))

        # RRF 融合（两路）
        merged = self._fusion.reciprocal_rank_fusion(
            dense_results, bm25_results,
            final_k=top_k * 2,
        )
        _t_fusion = time.monotonic()

        # ── TraceContext: rrf_fusion 子 span ──
        if _has_trace:
            hs_h._snapshot.children.append(type(hs_h._snapshot)(
                node="rrf_fusion",
                input={"dense_hits": len(dense_results),
                       "sparse_hits": len(bm25_results),
                       "final_k": top_k * 2},
                output={
                    "merged_count": len(merged),
                    "chunk_ids": [c.chunk_id for c in merged],
                    "fusion_ms": int((_t_fusion - _t_sparse) * 1000),
                },
                timing_ms=int((_t_fusion - _t_sparse) * 1000),
            ))

            hs_h.finish(output={
                "hits": len(merged),
                "chunk_ids": [c.chunk_id for c in merged],
                "dense_hits": len(dense_results),
                "bm25_hits": len(bm25_results),
                "splade_hits": 0,
                "splade_degraded": False,
                "search_ms": int((_t_fusion - _t0) * 1000),
            })

        self.last_stats = {
            "dense_hits": len(dense_results),
            "bm25_hits": len(bm25_results),
            "splade_hits": 0,  # 保留字段，向后兼容
        }
        logger.info(
            f"HybridSearch: query='{query[:50]}...', "
            f"dense={len(dense_results)}, bm25={len(bm25_results)}, "
            f"merged={len(merged)}"
        )
        return merged
