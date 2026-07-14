"""RRF（Reciprocal Rank Fusion）融合算法测试。

fusion.py 是纯算法，无外部依赖，是"最快产出"的测试目标。
"""

from retrieval.fusion import Fusion


class TestReciprocalRankFusion:
    """测试 Fusion.reciprocal_rank_fusion() 核心算法。"""

    # ---- 基础功能 ----

    def test_both_sides_have_results_interleave(self, scored_chunk_factory):
        """两端都有结果时应交叠排列，分数由两侧排名共同决定。"""
        dense = [
            scored_chunk_factory(chunk_id="a", score=0.95),
            scored_chunk_factory(chunk_id="b", score=0.80),
        ]
        sparse = [
            scored_chunk_factory(chunk_id="a", score=0.90),  # 唯一重合项
            scored_chunk_factory(chunk_id="c", score=0.70),
        ]
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion(dense, sparse, final_k=10)

        assert len(result) == 3
        # chunk "a" 在两个列表中都有排名 → RRF 分数最高
        assert result[0].chunk_id == "a"
        # 所有返回结果的分数已被替换为 RRF 分数（不是原始分数）
        for chunk in result:
            assert 0 < chunk.score < 1

    def test_dense_only_results(self, scored_chunk_factory):
        """仅稠密检索有结果时应直接透传（按 RRF 分数降序）。"""
        dense = [
            scored_chunk_factory(chunk_id="x", score=0.90),
            scored_chunk_factory(chunk_id="y", score=0.80),
        ]
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion(dense, [], final_k=10)

        assert len(result) == 2
        assert result[0].chunk_id == "x"
        assert result[1].chunk_id == "y"
        # 分数应为 RRF 分数而非原始分数
        assert result[0].score != 0.90

    def test_sparse_only_results(self, scored_chunk_factory):
        """仅稀疏检索有结果时同理。"""
        sparse = [
            scored_chunk_factory(chunk_id="m", score=0.75),
            scored_chunk_factory(chunk_id="n", score=0.65),
        ]
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion([], sparse, final_k=10)

        assert len(result) == 2
        assert result[0].chunk_id == "m"

    def test_both_empty(self):
        """两个列表都为空时返回空列表。"""
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion([], [], final_k=10)
        assert result == []

    # ---- RRF k 值影响 ----

    def test_k_60_smoothes_rank_difference(self, scored_chunk_factory):
        """k=60 时排名差异被平滑，相邻排名分数接近。"""
        dense = [
            scored_chunk_factory(chunk_id="a", score=0.90),
            scored_chunk_factory(chunk_id="b", score=0.50),
        ]
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion(dense, [], final_k=10)

        # rank 1: 1/61 ≈ 0.0164, rank 2: 1/62 ≈ 0.0161
        assert abs(result[0].score - result[1].score) < 0.001

    def test_k_1_sensitive_to_rank(self, scored_chunk_factory):
        """k=1 时排名差异被放大。"""
        dense = [
            scored_chunk_factory(chunk_id="a", score=0.90),
            scored_chunk_factory(chunk_id="b", score=0.50),
        ]
        fusion = Fusion(k=1)
        result = fusion.reciprocal_rank_fusion(dense, [], final_k=10)

        # rank 1: 1/2 = 0.5, rank 2: 1/3 ≈ 0.333
        assert result[0].score > result[1].score * 1.3

    # ---- 分数累加 ----

    def test_duplicate_chunk_scores_accumulate(self, scored_chunk_factory):
        """同一个 chunk_id 在两侧都出现时，RRF 分数应累加。"""
        chunk_a_dense = scored_chunk_factory(chunk_id="a", score=0.95)
        chunk_a_sparse = scored_chunk_factory(chunk_id="a", score=0.90)
        chunk_b = scored_chunk_factory(chunk_id="b", score=0.80)

        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion(
            [chunk_a_dense], [chunk_a_sparse, chunk_b], final_k=10
        )

        # "a" 在 dense rank=1 + sparse rank=1 → 分数最高
        assert result[0].chunk_id == "a"
        # "a" 累加了两个 RRF 分数，应高于仅出现在一侧的 "b"
        assert result[0].score > result[1].score

    # ---- final_k 截断 ----

    def test_final_k_truncation(self, scored_chunk_factory):
        """final_k 应正确截断结果数量。"""
        dense = [scored_chunk_factory(chunk_id=f"c{i}", score=0.90 - i * 0.05) for i in range(20)]
        fusion = Fusion(k=60)

        result_k5 = fusion.reciprocal_rank_fusion(dense, [], final_k=5)
        result_k10 = fusion.reciprocal_rank_fusion(dense, [], final_k=10)

        assert len(result_k5) == 5
        assert len(result_k10) == 10
        # 前 5 个应相同
        assert [c.chunk_id for c in result_k5] == [c.chunk_id for c in result_k10[:5]]

    def test_final_k_larger_than_results(self, scored_chunk_factory):
        """final_k 大于实际结果数时返回全部。"""
        dense = [
            scored_chunk_factory(chunk_id="a"),
            scored_chunk_factory(chunk_id="b"),
        ]
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion(dense, [], final_k=100)
        assert len(result) == 2

    # ---- 边界情况 ----

    def test_single_result_each_side_no_overlap(self, scored_chunk_factory):
        """两侧各一个不重合的结果。"""
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion(
            [scored_chunk_factory(chunk_id="a")],
            [scored_chunk_factory(chunk_id="b")],
            final_k=10,
        )
        assert len(result) == 2

    def test_complete_overlap(self, scored_chunk_factory):
        """两侧返回完全相同的结果集。"""
        chunks_dense = [
            scored_chunk_factory(chunk_id="a"),
            scored_chunk_factory(chunk_id="b"),
        ]
        chunks_sparse = [
            scored_chunk_factory(chunk_id="a"),
            scored_chunk_factory(chunk_id="b"),
        ]
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion(chunks_dense, chunks_sparse, final_k=10)

        # 不应有重复 chunk_id
        ids = [c.chunk_id for c in result]
        assert len(ids) == len(set(ids))
        assert len(result) == 2

    def test_scores_are_overwritten_with_rrf(self, scored_chunk_factory):
        """原始 score 被 RRF 分数完全覆盖。"""
        dense = [scored_chunk_factory(chunk_id="a", score=0.9999)]
        fusion = Fusion(k=60)
        result = fusion.reciprocal_rank_fusion(dense, [], final_k=10)

        # RRF 分数不可能等于原始分数
        assert result[0].score != 0.9999
        # rank 1, k=60 → RRF = 1/61 ≈ 0.0164
        assert 0.016 < result[0].score < 0.017
