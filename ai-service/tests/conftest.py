"""共享测试 fixtures。

为检索、LLM、MCP 等模块的测试提供可复用的 mock 对象和工厂函数。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from retrieval.models import ScoredChunk, IntentResult, RewriteResult, RetrievalContext


# ============================================================
# 数据工厂 fixtures
# ============================================================

@pytest.fixture
def scored_chunk_factory():
    """构造测试用 ScoredChunk 的工厂函数。"""
    def _create(chunk_id="chunk-001", content="这是测试内容", score=0.85,
                chunk_type="text", title=None, source_file="test.pdf",
                page_range=None, metadata=None):
        return ScoredChunk(
            chunk_id=chunk_id,
            content=content,
            score=score,
            chunk_type=chunk_type,
            title=title,
            source_file=source_file,
            page_range=page_range,
            metadata=metadata or {},
        )
    return _create


@pytest.fixture
def sample_chunks(scored_chunk_factory):
    """一组用于测试的 ScoredChunk 列表。"""
    return [
        scored_chunk_factory(chunk_id="c1", content="知识库架构设计", score=0.95),
        scored_chunk_factory(chunk_id="c2", content="权限模型：ACE 三层权限", score=0.82),
        scored_chunk_factory(chunk_id="c3", content="MCP 协议实现方案", score=0.71),
    ]


@pytest.fixture
def sample_retrieval_context(sample_chunks):
    """完整的 RetrievalContext 测试数据。"""
    return RetrievalContext(
        query="什么是 ACE 权限模型",
        chunks=sample_chunks,
        parent_chunks=[],
        toc_sections=[],
        citations=[],
        intent="factoid",
        keywords=["ACE", "权限"],
    )


@pytest.fixture
def sample_intent_result():
    """标准的 IntentResult 测试数据。"""
    return IntentResult(
        intent="factoid",
        method="rule",
        top_k=5,
        sub_queries=[],
    )


@pytest.fixture
def sample_rewrite_result():
    """标准的 RewriteResult 测试数据。"""
    return RewriteResult(
        rewritten_query="什么是企业 ACE 三层权限模型",
        keywords=["ACE", "三层权限", "企业权限"],
        skipped=False,
    )


# ============================================================
# Mock fixtures — LLM / Embedding / 基础设施
# ============================================================

@pytest.fixture
def mock_llm():
    """返回一个预配置的 AsyncMock BaseLLM。"""
    from models.llm import LLMResponse
    llm = AsyncMock()

    async def _gen():
        yield "这是"
        yield "LLM"
        yield "回答"

    llm.generate_content.return_value = LLMResponse(
        content="这是 LLM 生成的回答",
        model="test-model",
        usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    )
    llm.stream_content.return_value = _gen()
    return llm


@pytest.fixture
def mock_embedding():
    """返回一个预配置的 AsyncMock BaseEmbedding。"""
    emb = AsyncMock()
    emb.embed_documents.return_value = [[0.1] * 1024, [0.2] * 1024]
    emb.embed_query.return_value = [0.15] * 1024
    return emb


@pytest.fixture
def mock_httpx_client():
    """返回用于 mock httpx.AsyncClient 的 AsyncMock。"""
    import httpx
    client = AsyncMock(spec=httpx.AsyncClient)

    async def _mock_response(status_code=200, json_data=None, text=""):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = text
        return resp

    client.post.return_value = _mock_response()
    client.get.return_value = _mock_response()
    return client


@pytest.fixture
def mock_redis():
    """返回用于 mock redis.asyncio.Redis 的 AsyncMock。"""
    import redis.asyncio as aioredis
    r = AsyncMock(spec=aioredis.Redis)
    r.get.return_value = None
    r.set.return_value = True
    r.delete.return_value = 1
    r.expire.return_value = True
    return r


# ============================================================
# Pytest 配置钩子
# ============================================================

def pytest_configure(config):
    """设置测试环境变量，避免意外读取真实配置。"""
    import os
    os.environ.setdefault("KES_JAVA_URL", "http://localhost:8080")
    os.environ.setdefault("KES_API_KEY", "test-api-key-for-unit-tests")
