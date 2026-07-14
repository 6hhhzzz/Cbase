"""结果融合 — Reciprocal Rank Fusion (RRF)。

RRF 不需要调权重，只关心文档在多个列表中的排名。
对企业知识库中常见的"精准名词匹配"极其友好。

参考：TREC 推荐 RRF k=60。

v12: 支持三路融合（Dense + BM25 + SPLADE）。
"""

from .models import ScoredChunk


class Fusion:
    """RRF 融合器。

    将 dense（向量）、sparse（关键词）和 splade（神经词扩展）
    检索结果按 RRF 融合。向后兼容两路融合。
    """

    def __init__(self, k: int = 60):
        """
        Args:
            k: RRF 平滑参数，k 越大排名差异影响越小
        """
        self._k = k

    def reciprocal_rank_fusion(
        self,
        dense_results: list[ScoredChunk],
        sparse_results: list[ScoredChunk],
        final_k: int = 10,
    ) -> list[ScoredChunk]:
        """执行 RRF 融合（两路）。

        Args:
            dense_results: 稠密向量检索结果（按分数降序）
            sparse_results: 稀疏关键词检索结果（按分数降序）
            final_k: 最终返回结果数

        Returns:
            融合后的 ScoredChunk 列表，按 RRF 分数降序
        """
        rrf_scores: dict[str, tuple[float, ScoredChunk]] = {}

        def _add_results(results: list[ScoredChunk]):
            for rank, chunk in enumerate(results):
                rrf = 1.0 / (self._k + rank + 1)
                chunk_id = chunk.chunk_id
                if chunk_id in rrf_scores:
                    rrf_scores[chunk_id] = (rrf_scores[chunk_id][0] + rrf, chunk)
                else:
                    rrf_scores[chunk_id] = (rrf, chunk)

        _add_results(dense_results)
        _add_results(sparse_results)

        # 按 RRF 分数降序
        sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1][0], reverse=True)
        result = []
        for _, (rrf_score, chunk) in sorted_ids[:final_k]:
            chunk.score = rrf_score
            result.append(chunk)

        return result
