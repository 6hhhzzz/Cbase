"""Reranker 降级链测试。

测试三层策略：Cross-Encoder → LLM → 分数截断。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from retrieval.reranker import Reranker
from retrieval.models import ScoredChunk


class TestReranker:
    """测试 Reranker.rerank() 三层降级链。"""

    @pytest.fixture
    def sample_candidates(self, scored_chunk_factory):
        return [
            scored_chunk_factory(chunk_id="c1", content="知识库架构设计", score=0.95),
            scored_chunk_factory(chunk_id="c2", content="权限模型 ACE 三层", score=0.82),
            scored_chunk_factory(chunk_id="c3", content="MCP 协议实现", score=0.71),
            scored_chunk_factory(chunk_id="c4", content="文档解析引擎", score=0.65),
            scored_chunk_factory(chunk_id="c5", content="前端组件设计", score=0.58),
            scored_chunk_factory(chunk_id="c6", content="数据库迁移脚本", score=0.45),
            scored_chunk_factory(chunk_id="c7", content="Docker 编排配置", score=0.32),
        ]

    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        reranker = Reranker()
        result = await reranker.rerank("查询", [], top_n=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_fewer_than_top_n_returns_all(self, sample_candidates):
        """候选数 <= top_n 时直接返回所有。"""
        candidates = sample_candidates[:3]
        reranker = Reranker()
        result = await reranker.rerank("查询", candidates, top_n=5)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_cross_encoder_path(self, sample_candidates):
        """Cross-Encoder 正常工作时优先使用。"""
        mock_ce = MagicMock()
        # predict 返回分数列表
        mock_ce.predict.return_value = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]

        reranker = Reranker(cross_encoder=mock_ce)
        result = await reranker.rerank("查询", sample_candidates, top_n=3)

        assert len(result) == 3
        mock_ce.predict.assert_called_once()
        # 分数已更新为 Cross-Encoder 分数
        assert result[0].score != 0.95  # 不再是原始分

    @pytest.mark.asyncio
    async def test_cross_encoder_failure_falls_to_llm(self, sample_candidates, mock_llm):
        """Cross-Encoder 失败时降级到 LLM。"""
        mock_ce = MagicMock()
        mock_ce.predict.side_effect = RuntimeError("模型加载失败")

        reranker = Reranker(llm=mock_llm, cross_encoder=mock_ce)
        result = await reranker.rerank("查询", sample_candidates, top_n=3)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_llm_reranker_failure_falls_to_truncation(self, sample_candidates, mock_llm):
        """LLM 也失败时降级为分数截断（LLM rerank 失败返回默认分 50→归一化为 0.5）。"""
        mock_llm.generate_content.side_effect = Exception("LLM 超时")

        reranker = Reranker(llm=mock_llm)
        result = await reranker.rerank("查询", sample_candidates, top_n=3)

        assert len(result) == 3
        # LLM 失败降级时使用默认分 50，归一化到 0~1 范围
        for c in result:
            assert 0.0 <= c.score <= 1.0

    @pytest.mark.asyncio
    async def test_llm_score_normalized_to_zero_one(self, sample_candidates, mock_llm):
        """LLM 降级路径：0~100 分数归一化到 0~1。"""
        import json
        from models.llm import LLMResponse

        # 构造 LLM 返回的 JSON 分数（0~100 范围）
        mock_llm.generate_content.return_value = LLMResponse(
            content=json.dumps([
                {"id": "c1", "score": 90},
                {"id": "c2", "score": 75},
                {"id": "c3", "score": 60},
                {"id": "c4", "score": 45},
                {"id": "c5", "score": 30},
                {"id": "c6", "score": 20},
                {"id": "c7", "score": 10},
            ]),
            model="test-model",
        )

        # 没有 Cross-Encoder，走 LLM 降级
        reranker = Reranker(llm=mock_llm, cross_encoder=None)
        result = await reranker.rerank("查询", sample_candidates, top_n=5)

        assert len(result) == 5
        # 所有分数都应在 0~1 范围
        for c in result:
            assert 0.0 <= c.score <= 1.0, f"期望 0~1，实际 {c.score}"
        # 最高分 chunk 应为 c1（原始 90 → 0.9）
        assert result[0].chunk_id == "c1"
        assert result[0].score == pytest.approx(0.9, abs=0.01)

    @pytest.mark.asyncio
    async def test_no_llm_no_ce_uses_truncation(self, sample_candidates):
        """无 LLM 也无 Cross-Encoder → 直接截断。"""
        reranker = Reranker(llm=None, cross_encoder=None)
        result = await reranker.rerank("查询", sample_candidates, top_n=3)

        assert len(result) == 3
        assert result[0].chunk_id == "c1"  # 最高分

    @pytest.mark.asyncio
    async def test_cross_encoder_scalar_scores(self, sample_candidates):
        """Cross-Encoder 返回标量分数列表。"""
        mock_ce = MagicMock()
        mock_ce.predict.return_value = [0.88, 0.77, 0.66, 0.55, 0.44, 0.33, 0.22]

        reranker = Reranker(cross_encoder=mock_ce)
        result = await reranker.rerank("查询", sample_candidates, top_n=3)

        for chunk in result:
            assert isinstance(chunk.score, float)

    @pytest.mark.asyncio
    async def test_cross_encoder_list_scores(self, sample_candidates):
        """Cross-Encoder 返回嵌套列表分数。"""
        mock_ce = MagicMock()
        # 某些模型返回 [[score1], [score2], ...]
        mock_ce.predict.return_value = [[0.9], [0.8], [0.7], [0.6], [0.5], [0.4], [0.3]]

        reranker = Reranker(cross_encoder=mock_ce)
        result = await reranker.rerank("查询", sample_candidates, top_n=3)

        assert len(result) == 3
