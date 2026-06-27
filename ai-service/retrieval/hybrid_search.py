"""HybridSearch — 混合检索（Dense + Sparse → RRF 融合）。"""

import asyncio

from common import get_logger
from .dense import DenseRetriever
from .sparse import SparseRetriever
from .fusion import Fusion
from .models import ScoredChunk

logger = get_logger(__name__)


class HybridSearch:
    """混合检索器。

    并行执行稠密向量检索和稀疏关键词检索，然后用 RRF 融合结果。
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

    async def search(
        self,
        query: str,
        kb_ids: list[str],
        top_k: int = 10,
        keywords: list[str] | None = None,
        excluded_doc_ids: list[str] | None = None,
    ) -> list[ScoredChunk]:
        """执行混合检索。

        并行执行 Dense 和 Sparse 检索，各取 top_k * 3 候选，
        然后 RRF 融合到 top_k * 2（给 Reranker 留足候选）。

        Args:
            query: 查询文本
            kb_ids: 权限过滤 kb_id 列表
            top_k: 最终期望结果数
            keywords: 额外关键词（来自 QueryRewriter）
            excluded_doc_ids: 排除的文档 ID

        Returns:
            融合后的 ScoredChunk 列表
        """
        if not query.strip() and not keywords:
            return []

        candidate_k = top_k * 3  # 取更多候选给 RRF 融合

        # 并行执行
        dense_future = asyncio.create_task(
            self._dense.search(query, kb_ids, candidate_k, excluded_doc_ids)
        )
        sparse_future = asyncio.create_task(
            self._sparse.search(query, kb_ids, candidate_k, keywords, excluded_doc_ids)
        )

        dense_results, sparse_results = await dense_future, await sparse_future

        # RRF 融合
        merged = self._fusion.reciprocal_rank_fusion(
            dense_results, sparse_results, final_k=top_k * 2
        )

        logger.info(
            f"HybridSearch: query='{query[:50]}...', "
            f"dense={len(dense_results)}, sparse={len(sparse_results)}, "
            f"merged={len(merged)}"
        )
        return merged
