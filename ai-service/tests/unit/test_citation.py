"""引用标注器纯函数测试。

测试 _split_sentences、_cosine、_text_overlap、_build_doc_order。
"""

import pytest

from retrieval.citation import (
    _split_sentences,
    _cosine,
    _text_overlap,
    _build_doc_order,
    CitationInserter,
)
from retrieval.models import ScoredChunk


class TestSplitSentences:
    """测试中英文分句。"""

    def test_chinese_sentences(self):
        text = "ACE 权限模型是三层架构。它包含用户和组的映射。"
        sentences = _split_sentences(text)
        assert len(sentences) >= 2
        assert "权限模型" in sentences[0]

    def test_english_sentences(self):
        text = "This is the first sentence. Here is the second one."
        sentences = _split_sentences(text)
        assert len(sentences) >= 2

    def test_mixed_chinese_english(self):
        text = "系统使用 PostgreSQL 存储数据。The Redis cache is used for sessions."
        sentences = _split_sentences(text)
        assert len(sentences) >= 2

    def test_empty_string(self):
        sentences = _split_sentences("")
        assert sentences == [""]

    def test_single_sentence(self):
        text = "只有一个句子"
        sentences = _split_sentences(text)
        assert len(sentences) >= 1

    def test_short_sentences_merged(self):
        """过短的句子会被合并。"""
        text = "A。B。C。这是一个比较长的句子需要单独成句。"
        sentences = _split_sentences(text)
        # "A。B。C。" 可能被合并为一个
        assert len(sentences) >= 1

    def test_no_period(self):
        """没有标点的文本。"""
        text = "这是一段没有标点的文本"
        sentences = _split_sentences(text)
        assert len(sentences) >= 1


class TestCosine:
    """测试余弦相似度。"""

    def test_identical_vectors(self):
        vec = [0.5, 0.3, 0.2]
        assert _cosine(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert _cosine(a, b) == pytest.approx(-1.0)

    def test_zero_vector(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 2.0, 3.0]
        assert _cosine(a, b) == 0.0

    def test_both_zero_vectors(self):
        a = [0.0, 0.0]
        b = [0.0, 0.0]
        assert _cosine(a, b) == 0.0

    def test_partial_overlap(self):
        a = [0.8, 0.6, 0.0]
        b = [0.6, 0.8, 0.0]
        score = _cosine(a, b)
        assert 0.9 < score < 1.0  # 应该相当接近


class TestTextOverlap:
    """测试文本重叠度降级匹配。"""

    def test_overlapping_content(self):
        chunk = ScoredChunk(chunk_id="c1", content="ACE 权限模型设计文档")
        score = _text_overlap("权限模型", chunk)
        assert score > 0

    def test_no_overlap(self):
        chunk = ScoredChunk(chunk_id="c1", content="数据库配置")
        score = _text_overlap("前端布局", chunk)
        assert score == 0.0

    def test_empty_text(self):
        chunk = ScoredChunk(chunk_id="c1", content="")
        score = _text_overlap("测试", chunk)
        assert score == 0.0

    def test_empty_sentence(self):
        chunk = ScoredChunk(chunk_id="c1", content="有内容")
        score = _text_overlap("", chunk)
        assert score == 0.0

    def test_complete_match(self):
        chunk = ScoredChunk(chunk_id="c1", content="完整匹配")
        score = _text_overlap("完整匹配", chunk)
        # 应该接近 1.0
        assert score > 0.5


class TestBuildDocOrder:
    """测试按 page_range 构建文档顺序。"""

    def test_ordered_by_page_range(self):
        chunks = [
            ScoredChunk(chunk_id="c1", content="a", page_range=(5, 6)),
            ScoredChunk(chunk_id="c2", content="b", page_range=(1, 2)),
            ScoredChunk(chunk_id="c3", content="c", page_range=(3, 4)),
        ]
        order = _build_doc_order(chunks)
        # c2 (p1-2) < c3 (p3-4) < c5 (p5-6)
        assert order["c2"] < order["c3"] < order["c1"]

    def test_no_page_range_sorted_last(self):
        chunks = [
            ScoredChunk(chunk_id="c1", content="a", page_range=(1, 1)),
            ScoredChunk(chunk_id="c2", content="b", page_range=None),
        ]
        order = _build_doc_order(chunks)
        assert order["c1"] < order["c2"]

    def test_same_page_range(self):
        chunks = [
            ScoredChunk(chunk_id="c1", content="a", page_range=(1, 1)),
            ScoredChunk(chunk_id="c2", content="b", page_range=(1, 1)),
        ]
        order = _build_doc_order(chunks)
        # 应都有 order，且不同（稳定排序）
        assert order["c1"] != order["c2"]

    def test_empty_list(self):
        assert _build_doc_order([]) == {}


class TestCitationInserter:
    """测试 CitationInserter 核心方法。"""

    @pytest.mark.asyncio
    async def test_insert_empty_answer(self, mock_embedding):
        inserter = CitationInserter(embedding=mock_embedding)
        result_text, citations = await inserter.insert("", [])
        assert result_text == ""
        assert citations == []

    @pytest.mark.asyncio
    async def test_insert_empty_chunks(self, mock_embedding):
        inserter = CitationInserter(embedding=mock_embedding)
        result_text, citations = await inserter.insert("一些回答内容。", [])
        assert result_text == "一些回答内容。"
        assert citations == []

    @pytest.mark.asyncio
    async def test_insert_single_sentence(self, mock_embedding):
        """单句答案不标注引用。"""
        chunks = [
            ScoredChunk(chunk_id="c1", content="参考内容", metadata={"_embedding": [0.1] * 10}),
        ]
        mock_embedding.embed_query.return_value = [0.1] * 10
        inserter = CitationInserter(embedding=mock_embedding)
        result_text, citations = await inserter.insert("单句。", chunks)
        # 单句不分句，直接返回
        assert len(citations) == 0
