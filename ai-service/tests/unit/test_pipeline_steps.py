"""ETL Pipeline Step 单元测试。

每个 Step 使用 mock 依赖独立测试，验证单个 Step 的输入/输出行为。
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from etl.steps import (
    PipelineStep,
    SanitizeStep,
    IndexStep,
)
from etl.sanitizers.presidio_sanitizer import PresidioSanitizer
from models.document import (
    DocumentIngestMessage,
    DocumentMetadata,
    ParseResult,
    DocumentChunk,
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


# ================================================================
# LlmMetadataEnrichStep 测试
# ================================================================

class TestLlmMetadataEnrichStep:
    """LLM 增强元数据提取步骤测试。"""

    @pytest.fixture
    def sample_llm(self):
        """构造 mock LLM。"""
        llm = MagicMock()
        llm.generate_content = AsyncMock()
        return llm

    @pytest.fixture
    def ctx_with_title_chunks(self, sample_msg):
        """构造含 title chunk 的 context。"""
        chunks = [
            DocumentChunk(
                doc_id=sample_msg.doc_id,
                chunk_index=0,
                chunk_text="第1章 项目概述",
                metadata={"chunk_type": "title", "title": "第1章 项目概述"},
            ),
            DocumentChunk(
                doc_id=sample_msg.doc_id,
                chunk_index=1,
                chunk_text="这是项目背景介绍。本文档描述了IWMS系统的...",
                metadata={"chunk_type": "text"},
            ),
            DocumentChunk(
                doc_id=sample_msg.doc_id,
                chunk_index=2,
                chunk_text="1.1 技术架构",
                metadata={"chunk_type": "title", "title": "1.1 技术架构"},
            ),
        ]
        return {"msg": sample_msg, "chunks": chunks}

    @pytest.mark.asyncio
    async def test_llm_success_applies_results(self, sample_llm, ctx_with_title_chunks):
        """LLM 成功返回 JSON → metadata 应正确写入。"""
        from models.llm import LLMResponse
        sample_llm.generate_content.return_value = LLMResponse(
            content='{"chunks": ['
                    '{"index": 0, "level": 1, "heading": "项目概述", "chunk_type": "title", "entities": ["IWMS"]},'
                    '{"index": 2, "level": 2, "heading": "技术架构", "chunk_type": "title", "entities": []}'
                    ']}',
            model="test-model",
            usage={"total_tokens": 100},
        )

        from etl.steps import LlmMetadataEnrichStep
        step = LlmMetadataEnrichStep(llm=sample_llm)
        ctx = await step.execute(ctx_with_title_chunks)

        chunks = ctx["chunks"]
        # chunk 0 (title): LLM 结果
        assert chunks[0].metadata["level"] == 1
        assert chunks[0].metadata["heading"] == "项目概述"
        assert chunks[0].metadata["entities"] == ["IWMS"]
        # chunk 1 (text): 不受影响
        assert "level" not in chunks[1].metadata
        # chunk 2 (title): LLM 结果
        assert chunks[2].metadata["level"] == 2
        assert chunks[2].metadata["heading"] == "技术架构"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_rules(self, sample_llm, ctx_with_title_chunks):
        """LLM 失败 → 静默降级到规则逻辑。"""
        sample_llm.generate_content.side_effect = Exception("API 超时")

        from etl.steps import LlmMetadataEnrichStep
        step = LlmMetadataEnrichStep(llm=sample_llm)
        ctx = await step.execute(ctx_with_title_chunks)

        chunks = ctx["chunks"]
        # 降级后 heading 应取 chunk_text 前 80 字符
        assert "heading" in chunks[0].metadata
        assert chunks[0].metadata["heading"] == "第1章 项目概述"
        # 降级后 level 默认 1
        assert chunks[0].metadata["level"] == 1

    @pytest.mark.asyncio
    async def test_no_llm_configured_uses_rules(self, ctx_with_title_chunks):
        """LLM=None → 纯规则模式。"""
        from etl.steps import LlmMetadataEnrichStep
        step = LlmMetadataEnrichStep(llm=None)
        ctx = await step.execute(ctx_with_title_chunks)

        chunks = ctx["chunks"]
        assert chunks[0].metadata["heading"] == "第1章 项目概述"
        assert chunks[0].metadata["level"] == 1

    @pytest.mark.asyncio
    async def test_no_title_chunks_skips_llm(self, sample_llm, sample_msg):
        """无 title chunk → 不调用 LLM。"""
        chunks = [
            DocumentChunk(
                doc_id=sample_msg.doc_id,
                chunk_index=0,
                chunk_text="这是纯正文内容。",
                metadata={"chunk_type": "text"},
            ),
        ]
        ctx = {"msg": sample_msg, "chunks": chunks}

        from etl.steps import LlmMetadataEnrichStep
        step = LlmMetadataEnrichStep(llm=sample_llm)
        ctx = await step.execute(ctx)

        # LLM 不应被调用
        sample_llm.generate_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_chunks_skips(self, sample_llm, sample_msg):
        """空 chunks → 跳过。"""
        ctx = {"msg": sample_msg, "chunks": []}

        from etl.steps import LlmMetadataEnrichStep
        step = LlmMetadataEnrichStep(llm=sample_llm)
        result = await step.execute(ctx)

        assert result is ctx  # 原样返回

    @pytest.mark.asyncio
    async def test_llm_json_in_code_block(self, sample_llm, ctx_with_title_chunks):
        """LLM 输出包裹在 ```json 中 → 应正确提取。"""
        from models.llm import LLMResponse
        sample_llm.generate_content.return_value = LLMResponse(
            content='```json\n{"chunks": ['
                    '{"index": 0, "level": 1, "heading": "项目概述", "chunk_type": "title", "entities": ["IWMS"]},'
                    '{"index": 2, "level": 2, "heading": "技术架构", "chunk_type": "title", "entities": ["Spring Cloud"]}'
                    ']}\n```',
            model="test-model",
            usage={"total_tokens": 100},
        )

        from etl.steps import LlmMetadataEnrichStep
        step = LlmMetadataEnrichStep(llm=sample_llm)
        ctx = await step.execute(ctx_with_title_chunks)

        assert ctx["chunks"][0].metadata["level"] == 1
        assert ctx["chunks"][2].metadata["entities"] == ["Spring Cloud"]

    @pytest.mark.asyncio
    async def test_llm_bad_json_falls_back(self, sample_llm, ctx_with_title_chunks):
        """LLM 返回非法 JSON → 降级到规则。"""
        from models.llm import LLMResponse
        sample_llm.generate_content.return_value = LLMResponse(
            content='not valid json at all',
            model="test-model",
            usage={"total_tokens": 50},
        )

        from etl.steps import LlmMetadataEnrichStep
        step = LlmMetadataEnrichStep(llm=sample_llm)
        ctx = await step.execute(ctx_with_title_chunks)

        # 应降级到规则
        assert "heading" in ctx["chunks"][0].metadata
        assert ctx["chunks"][0].metadata["level"] == 1

    @pytest.mark.asyncio
    async def test_level_from_chunker_is_preserved(self, sample_msg):
        """ChunkStepV5 修复后 level 由 TitleChunker 传入 → 规则降级使用它。"""
        chunks = [
            DocumentChunk(
                doc_id=sample_msg.doc_id,
                chunk_index=0,
                chunk_text="系统架构设计",
                metadata={
                    "chunk_type": "title",
                    "title": "系统架构设计",
                    # 模拟 TitleChunker 已设置 level=2
                    "level": 2,
                },
            ),
        ]
        ctx = {"msg": sample_msg, "chunks": chunks}

        from etl.steps import LlmMetadataEnrichStep
        step = LlmMetadataEnrichStep(llm=None)
        ctx = await step.execute(ctx)

        # 规则降级应保留 ChunkStepV5 传入的 level
        assert ctx["chunks"][0].metadata["level"] == 2
        assert ctx["chunks"][0].metadata["heading"] == "系统架构设计"
