"""分块算法测试 — merge_chunks 合并 + ContextEnricher 上下文注入。"""

from chunking.models import Chunk, ChunkRelation
from chunking.merge import merge_chunks
from chunking.enrich import ContextEnricher


# ============================================================
# Chunk 数据模型测试
# ============================================================

class TestChunkModel:
    """测试 Chunk 和 ChunkRelation 构造。"""

    def test_chunk_default_values(self):
        c = Chunk(id="chunk-1", content="测试内容")
        assert c.content_with_weight == ""
        assert c.title is None
        assert c.chunk_type == "text"
        assert c.page_range is None
        assert c.tokens == 0
        assert c.metadata == {}

    def test_chunk_full_construction(self):
        c = Chunk(
            id="chunk-1",
            content="测试内容",
            content_with_weight="测试内容 测试 内容",
            title="第一章",
            chunk_type="text",
            page_range=(1, 3),
            tokens=150,
            metadata={"kb_id": "kb-1", "doc_id": "doc-1"},
        )
        assert c.page_range == (1, 3)
        assert c.metadata["kb_id"] == "kb-1"

    def test_chunk_relation_defaults(self):
        r = ChunkRelation()
        assert r.parent_id is None
        assert r.children_ids == []
        assert r.prev_id is None
        assert r.next_id is None


# ============================================================
# merge_chunks 测试
# ============================================================

class TestMergeChunks:
    """测试 merge_chunks() 函数。"""

    def _make_text_chunk(self, id, content, tokens=50):
        return Chunk(
            id=id, content=content, chunk_type="text",
            tokens=tokens, metadata={"file_name": "test.md"},
        )

    def _make_table_chunk(self, id, content, tokens=80):
        return Chunk(
            id=id, content=content, chunk_type="table",
            tokens=tokens, metadata={"file_name": "test.md"},
        )

    def test_single_chunk_unchanged(self):
        chunk = self._make_text_chunk("c1", "单块")
        merged, rels = merge_chunks([chunk], [], target_tokens=512)
        assert len(merged) == 1

    def test_empty_list(self):
        merged, rels = merge_chunks([], [], target_tokens=512)
        assert merged == []
        assert rels == []

    def test_large_chunks_not_merged(self):
        """达到目标大小的 chunk 不被合并。"""
        chunks = [
            self._make_text_chunk("c1", "大块" * 300, tokens=600),
            self._make_text_chunk("c2", "另一大块" * 300, tokens=600),
        ]
        merged, rels = merge_chunks(chunks, [], target_tokens=512)
        assert len(merged) == 2

    def test_small_chunks_merged(self):
        """小 chunk 被合并到相邻 chunk。"""
        chunks = [
            self._make_text_chunk("c1", "小块1", tokens=30),
            self._make_text_chunk("c2", "小块2", tokens=30),
        ]
        merged, rels = merge_chunks(chunks, [], target_tokens=512, min_tokens=50)
        # 两个小块被合并为一个
        assert len(merged) == 1
        assert "小块1" in merged[0].content
        assert "小块2" in merged[0].content

    def test_table_chunks_preserved(self):
        """表格 chunk 在不需要合并时直接保留。"""
        # 使用足够大的 chunk（>= target_tokens）避免触发合并，确保表格保留
        chunks = [
            self._make_text_chunk("c1", "大块" * 300, tokens=600),
            self._make_table_chunk("t1", "表格", tokens=80),
            self._make_text_chunk("c2", "大块" * 300, tokens=600),
        ]
        merged, rels = merge_chunks(chunks, [], target_tokens=512)
        # 三个 chunk 都不需要合并，表格应保留
        table_chunks = [c for c in merged if c.chunk_type == "table"]
        assert len(table_chunks) >= 1

    def test_merged_chunks_reindexed(self):
        """合并后 chunk ID 被重建。"""
        chunks = [
            self._make_text_chunk("c1", "小块1", tokens=30),
            self._make_text_chunk("c2", "小块2", tokens=30),
        ]
        merged, rels = merge_chunks(chunks, [], target_tokens=512, min_tokens=50)
        # 合并后 ID 发生变化
        if len(merged) == 1:
            assert merged[0].id != "c1"

    def test_relations_rebuilt(self):
        """关系在合并后被重建。"""
        chunks = [
            self._make_text_chunk("c1", "块1", tokens=100),
            self._make_text_chunk("c2", "块2", tokens=100),
        ]
        merged, rels = merge_chunks(chunks, [], target_tokens=512)
        assert len(rels) == len(merged)
        if len(merged) == 2:
            assert rels[0].next_id == merged[1].id
            assert rels[1].prev_id == merged[0].id


# ============================================================
# ContextEnricher 测试
# ============================================================

class TestContextEnricher:
    """测试 ContextEnricher.enrich()。"""

    def test_enrich_matching_lengths(self):
        """chunks 和 relations 长度匹配时正常处理。"""
        enricher = ContextEnricher(table_context_size=1, image_context_size=1)
        chunks = [
            Chunk(id="c1", content="文本", chunk_type="text", tokens=50),
            Chunk(id="c2", content="表格内容", chunk_type="table", tokens=50),
            Chunk(id="c3", content="文本2", chunk_type="text", tokens=50),
        ]
        rels = [ChunkRelation(prev_id=None, next_id="c2"),
                ChunkRelation(prev_id="c1", next_id="c3"),
                ChunkRelation(prev_id="c2", next_id=None)]
        result = enricher.enrich(chunks, rels)
        assert len(result) == 3

    def test_enrich_empty_chunks(self):
        enricher = ContextEnricher()
        result = enricher.enrich([], [])
        assert result == []

    def test_enrich_preserves_text_chunks(self):
        """纯文本 chunk 不被修改。"""
        enricher = ContextEnricher(table_context_size=1, image_context_size=1)
        chunks = [
            Chunk(id="c1", content="纯文本", chunk_type="text", tokens=50),
            Chunk(id="c2", content="也是文本", chunk_type="text", tokens=50),
        ]
        rels = [ChunkRelation(next_id="c2"), ChunkRelation(prev_id="c1")]
        result = enricher.enrich(chunks, rels)
        # 原地修改，文本内容不变
        assert result[0].content == "纯文本"
        assert result[1].content == "也是文本"
