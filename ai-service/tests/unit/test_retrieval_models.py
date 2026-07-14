"""检索数据模型测试。

ScoredChunk、IntentResult、RewriteResult、RetrievalContext 的构造和属性。
"""

from retrieval.models import ScoredChunk, IntentResult, RewriteResult, RetrievalContext, SubQuery


class TestScoredChunk:
    """测试 ScoredChunk 数据类。"""

    def test_default_values(self):
        c = ScoredChunk(chunk_id="c-1", content="测试")
        assert c.score == 0.0
        assert c.chunk_type == "text"
        assert c.title is None
        assert c.source_file == ""
        assert c.page_range is None
        assert c.metadata == {}

    def test_full_construction(self):
        c = ScoredChunk(
            chunk_id="c-1",
            content="ACE 权限模型设计",
            score=0.92,
            chunk_type="text",
            title="权限模型",
            source_file="design.pdf",
            page_range=(3, 5),
            metadata={"kb_id": "kb-001"},
        )
        assert c.chunk_id == "c-1"
        assert c.page_range == (3, 5)
        assert c.metadata["kb_id"] == "kb-001"

    def test_metadata_defaults_to_empty_dict(self):
        c = ScoredChunk(chunk_id="c-1", content="测试")
        assert isinstance(c.metadata, dict)
        assert len(c.metadata) == 0


class TestIntentResult:
    """测试 IntentResult / QueryPlan 数据类。"""

    def test_default_values(self):
        r = IntentResult(complexity="simple")
        assert r.method == "llm"
        assert r.top_k == 5
        assert r.sub_queries == []

    def test_compare_intent(self):
        sq = SubQuery(id="q1", query="A")
        r = IntentResult(complexity="simple", method="llm", sub_queries=[sq])
        assert r.complexity == "simple"
        assert r.method == "llm"
        assert len(r.sub_queries) == 1


class TestRewriteResult:
    """测试 RewriteResult 数据类。"""

    def test_default_values(self):
        r = RewriteResult(rewritten_query="test")
        assert r.keywords == []
        assert r.skipped is False

    def test_skipped_flag(self):
        r = RewriteResult(rewritten_query="test", skipped=True)
        assert r.skipped is True


class TestRetrievalContext:
    """测试 RetrievalContext 数据类。"""

    def test_total_tokens_with_chunks(self, sample_chunks):
        ctx = RetrievalContext(query="什么是 ACE", chunks=sample_chunks)
        assert ctx.total_tokens > 0

    def test_total_tokens_empty(self):
        ctx = RetrievalContext(query="test", chunks=[])
        # 仅 query 有 token 数
        assert ctx.total_tokens >= 0

    def test_total_tokens_with_parents(self, sample_chunks):
        ctx = RetrievalContext(
            query="什么是 ACE",
            chunks=sample_chunks,
            parent_chunks=sample_chunks[:1],
        )
        assert ctx.total_tokens > 0

    def test_toc_sections_included_in_tokens(self, sample_chunks):
        ctx_with = RetrievalContext(
            query="什么是 ACE",
            chunks=sample_chunks,
            toc_sections=["第一章", "第二章"],
        )
        ctx_without = RetrievalContext(
            query="什么是 ACE",
            chunks=sample_chunks,
            toc_sections=[],
        )
        assert ctx_with.total_tokens >= ctx_without.total_tokens

    def test_default_values(self):
        ctx = RetrievalContext(query="test", chunks=[])
        assert ctx.parent_chunks == []
        assert ctx.toc_sections == []
        assert ctx.citations == []
        assert ctx.intent == "factoid"
        assert ctx.keywords == []
        assert ctx.reranked_count == 0
        assert ctx.filtered_count == 0

    def test_filtered_count_fields(self):
        """reranked_count 和 filtered_count 记录过滤统计。"""
        from retrieval.models import ScoredChunk
        chunks = [ScoredChunk(chunk_id="c1", content="test", score=0.9)]
        ctx = RetrievalContext(
            query="test",
            chunks=chunks,
            reranked_count=5,
            filtered_count=4,
        )
        assert ctx.reranked_count == 5
        assert ctx.filtered_count == 4
        assert len(ctx.chunks) == 1  # 过滤后只剩 1 条
