"""ETL Pipeline Step 单元测试。

每个 Step 使用 mock 依赖独立测试，验证单个 Step 的输入/输出行为。
"""
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from etl.steps import (
    PipelineStep,
    DownloadStep,
    ParseStep,
    SanitizeStep,
    ChunkStep,
    IndexStep,
)
from etl.parsers.registry import ParserRegistry
from etl.sanitizers.presidio_sanitizer import PresidioSanitizer
from models.document import (
    DocumentIngestMessage,
    DocumentMetadata,
    ParseResult,
    DocumentChunk,
    IngestCallbackMessage,
    IngestStatus,
)


# ================================================================
# Fixtures
# ================================================================

@pytest.fixture
def sample_msg():
    """构造一个标准的 pdf 文档入库消息。"""
    return DocumentIngestMessage(
        doc_id=uuid4(),
        file_path="test-docs/report.pdf",
        file_type="pdf",
        metadata=DocumentMetadata(
            kb_id="kb-001",
            uploader_role="admin",
            effective_date="2026-01-01",
        ),
    )


@pytest.fixture
def sample_parse_result():
    """构造一个解析结果。"""
    return ParseResult(
        file_type="pdf",
        raw_text="这是测试文档的文本内容。包含足够多的字符用于分块测试。" * 20,
        page_count=3,
    )


@pytest.fixture
def sample_ctx(sample_msg):
    """构造基础 context dict。"""
    return {"msg": sample_msg, "temp_path": "/tmp/test_file.pdf"}


# ================================================================
# ParseStep 测试
# ================================================================

class TestParseStep:
    """解析步骤测试。"""

    @pytest.mark.asyncio
    async def test_parse_supported_type(self, sample_ctx, tmp_path):
        """支持的文件类型应该成功解析。"""
        # 创建真实的 txt 文件供解析器读取
        test_file = tmp_path / "test.txt"
        test_file.write_text("这是文本解析测试文档的内容。\n包含多行文本。" * 20)
        sample_ctx["temp_path"] = str(test_file)
        # 将 msg 的 file_type 改为 txt 以匹配实际文件
        sample_ctx["msg"] = sample_ctx["msg"].model_copy(update={"file_type": "txt"})

        registry = ParserRegistry()
        step = ParseStep(registry)
        ctx = await step.execute(sample_ctx)
        assert "parse_result" in ctx
        assert "_early_exit" not in ctx
        assert ctx["parse_result"].file_type == "txt"
        assert len(ctx["parse_result"].raw_text) > 0

    @pytest.mark.asyncio
    async def test_parse_unsupported_type(self, sample_ctx):
        """不支持的文件类型应该设置 early_exit。"""
        sample_ctx["msg"] = sample_ctx["msg"].model_copy(update={"file_type": "exe"})
        registry = ParserRegistry()
        step = ParseStep(registry)
        ctx = await step.execute(sample_ctx)
        assert "_early_exit" in ctx
        callback = ctx["_early_exit"]
        assert callback.status == IngestStatus.FAILED
        assert "不支持" in callback.error_message


# ================================================================
# SanitizeStep 测试
# ================================================================

class TestSanitizeStep:
    """脱敏步骤测试。"""

    @pytest.mark.asyncio
    async def test_sanitize_pii_detection(self, sample_ctx, sample_parse_result):
        """检测到身份证号应脱敏（中间部分被掩码）。"""
        sample_ctx["parse_result"] = ParseResult(
            file_type="txt",
            raw_text="张三的身份证号是110101199001011234，请处理。",
        )
        step = SanitizeStep(PresidioSanitizer(), security_level=2)
        ctx = await step.execute(sample_ctx)
        # 身份证格式：前6位+****+后4位 → "110101****1234"
        assert "****" in ctx["parse_result"].raw_text
        assert "19900101" not in ctx["parse_result"].raw_text

    @pytest.mark.asyncio
    async def test_sanitize_no_pii(self, sample_ctx, sample_parse_result):
        """无敏感信息的文本不应修改。"""
        original = "这是一段普通的文本内容。"
        sample_ctx["parse_result"] = ParseResult(file_type="txt", raw_text=original)
        step = SanitizeStep(PresidioSanitizer(), security_level=2)
        ctx = await step.execute(sample_ctx)
        assert ctx["parse_result"].raw_text == original

    @pytest.mark.asyncio
    async def test_sanitize_skip_low_security(self, sample_ctx):
        """低安全级别应跳过脱敏。"""
        original = "张三的身份证号是110101199001011234。"
        sample_ctx["parse_result"] = ParseResult(file_type="txt", raw_text=original)
        step = SanitizeStep(PresidioSanitizer(), security_level=1)
        ctx = await step.execute(sample_ctx)
        assert ctx["parse_result"].raw_text == original  # 未修改


# ================================================================
# ChunkStep 测试
# ================================================================

class TestChunkStep:
    """分块步骤测试。"""

    @pytest.mark.asyncio
    async def test_chunk_metadata_injection(self, sample_ctx, sample_parse_result):
        """分块后每个 chunk 应包含权限元数据。"""
        from etl.chunkers.text_chunker import TextChunker
        sample_ctx["parse_result"] = sample_parse_result
        step = ChunkStep(TextChunker())
        ctx = await step.execute(sample_ctx)
        assert "chunks" in ctx
        for chunk in ctx["chunks"]:
            assert chunk.metadata["kb_id"] == "kb-001"
            assert "source_file" in chunk.metadata

    @pytest.mark.asyncio
    async def test_empty_text_produces_no_chunks(self, sample_ctx):
        """空文本应设置 early_exit。"""
        from etl.chunkers.text_chunker import TextChunker
        sample_ctx["parse_result"] = ParseResult(file_type="txt", raw_text="")
        step = ChunkStep(TextChunker())
        ctx = await step.execute(sample_ctx)
        assert "_early_exit" in ctx


# ================================================================
# IndexStep 测试
# ================================================================

class TestIndexStep:
    """索引写入步骤测试。"""

    @pytest.mark.asyncio
    async def test_insert_count(self, sample_ctx):
        """索引写入应返回正确的块数。"""
        mock_pgvector = MagicMock()
        mock_pgvector.insert_chunks = AsyncMock(return_value=5)
        sample_ctx["chunks"] = [MagicMock() for _ in range(5)]
        step = IndexStep(mock_pgvector)
        ctx = await step.execute(sample_ctx)
        assert ctx["inserted_count"] == 5
        mock_pgvector.insert_chunks.assert_called_once()


# ================================================================
# PipelineStep ABC 测试
# ================================================================

class TestPipelineStepABC:
    """验证 PipelineStep 抽象基类。"""

    def test_cannot_instantiate_abstract(self):
        """不能直接实例化 PipelineStep。"""
        with pytest.raises(TypeError):
            PipelineStep()

    def test_subclass_must_implement(self):
        """子类必须实现 execute 方法。"""

        class BadStep(PipelineStep):
            pass

        with pytest.raises(TypeError):
            BadStep()
