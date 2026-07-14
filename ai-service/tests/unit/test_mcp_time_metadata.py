"""MCP 时间元数据端到端验证。

模拟从检索层 → MCP 返回层的完整元数据传递链路，
验证 time_range 参数和 is_expired 标志位是否正确工作。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from retrieval.models import ScoredChunk, RetrievalContext


class TestTimeMetadataFlow:
    """验证时间元数据从 ScoredChunk → MCP search_chunks 结果的完整传递。"""

    @pytest.fixture
    def chunks_with_time_meta(self):
        """构造模拟 DB 返回的带时间元数据的 ScoredChunk 列表。"""
        return [
            ScoredChunk(
                chunk_id="c1",
                content="PostgreSQL 16 主库配置：wal_level=replica, max_wal_senders=5",
                score=0.92,
                source_file="高可用架构设计.md",
                page_range=(12, 14),
                metadata={
                    "retriever": "dense",
                    "doc_id": "doc-001",
                    "doc_effective_date": "2025-04-01",
                    "doc_expiry_date": "2026-12-31",
                    "doc_version": "v2.3",
                    "is_expired": False,
                    "chunk_indexed_at": 1710500000000,
                },
            ),
            ScoredChunk(
                chunk_id="c2",
                content="PostgreSQL 9.6 主从配置：使用 trigger_file 切换",
                score=0.78,
                source_file="旧版运维手册.md",
                page_range=(3, 5),
                metadata={
                    "retriever": "sparse",
                    "doc_id": "doc-002",
                    "doc_effective_date": "2020-01-01",
                    "doc_expiry_date": "2021-12-31",
                    "doc_version": "v1.0",
                    "is_expired": True,
                    "chunk_indexed_at": 1577800000000,
                },
            ),
            ScoredChunk(
                chunk_id="c3",
                content="流复制监控：pg_stat_replication 字段说明",
                score=0.85,
                source_file="运维监控手册.md",
                page_range=(23, 24),
                metadata={
                    "retriever": "dense",
                    "doc_id": "doc-003",
                    # 无 expiry_date — 永不失效
                    "doc_effective_date": "2025-06-01",
                    "doc_version": "v3.0",
                    "is_expired": False,
                    "chunk_indexed_at": 1718000000000,
                },
            ),
        ]

    @pytest.fixture
    def mock_retrieval_orch(self, chunks_with_time_meta):
        """模拟 RetrievalOrchestrator.execute() 返回。"""
        orch = AsyncMock()
        orch.execute.return_value = RetrievalContext(
            query="PostgreSQL 主从复制配置",
            chunks=chunks_with_time_meta,
            keywords=["PostgreSQL", "主从", "复制"],
        )
        return orch

    @pytest.mark.asyncio
    async def test_search_chunks_returns_time_metadata(
        self, mock_retrieval_orch, chunks_with_time_meta
    ):
        """验证 search_chunks 返回的每条 chunk 都包含完整时间元数据。"""
        from kes_mcp.tools import search_chunks, _resolve_effective_kb_ids

        # Mock auth and permission resolution
        mock_auth = MagicMock()
        mock_auth.ensure_token = AsyncMock(return_value="fake-context-token")
        mock_auth.space_id = "sp-001"
        mock_auth.scope_kb_ids = None

        with patch("kes_mcp.tools._resolve_effective_kb_ids",
                   new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = ["kb-001", "kb-002"]

            result = await search_chunks(
                retrieval_orch=mock_retrieval_orch,
                auth=mock_auth,
                arguments={
                    "query": "PostgreSQL 主从复制配置",
                    "kb_ids": ["kb-001"],
                    "top_k": 3,
                    "time_range": {"expired": "include"},  # 包含过期，验证完整元数据
                },
            )

        # ---- 断言 ----
        assert isinstance(result, list)
        assert len(result) == 1
        data = result[0]
        assert "chunks" in data
        assert data["total"] == 3

        chunks = data["chunks"]

        # === Chunk 1: 有效文档（未过期） ===
        c1 = chunks[0]
        assert c1["chunk_id"] == "c1"
        assert c1["source"]["doc_id"] == "doc-001"
        assert c1["source"]["doc_version"] == "v2.3"
        assert c1["source"]["doc_effective_date"] == "2025-04-01"
        assert c1["source"]["doc_expiry_date"] == "2026-12-31"
        assert c1["source"]["is_expired"] is False
        assert c1["source"]["page_range"] == [12, 14]
        # verify no None values leaked
        assert None not in c1["source"].values()

        # === Chunk 2: 过期文档 ===
        c2 = chunks[1]
        assert c2["chunk_id"] == "c2"
        assert c2["source"]["doc_version"] == "v1.0"
        assert c2["source"]["doc_effective_date"] == "2020-01-01"
        assert c2["source"]["doc_expiry_date"] == "2021-12-31"
        assert c2["source"]["is_expired"] is True  # ← 关键：Agent 可从这判断
        assert c2["source"]["page_range"] == [3, 5]

        # === Chunk 3: 无过期日期（永不失效） ===
        c3 = chunks[2]
        assert c3["chunk_id"] == "c3"
        assert c3["source"]["doc_version"] == "v3.0"
        assert c3["source"]["doc_effective_date"] == "2025-06-01"
        assert "doc_expiry_date" not in c3["source"]  # None 被清理
        assert c3["source"]["is_expired"] is False

        # === metadata 层验证 ===
        assert c1["metadata"]["retriever"] == "dense"
        assert c1["metadata"]["chunk_indexed_at"] == 1710500000000

    @pytest.mark.asyncio
    async def test_time_range_exclude_expired(
        self, mock_retrieval_orch, chunks_with_time_meta
    ):
        """time_range.expired='exclude' 应过滤掉 is_expired=True 的 chunk。"""
        from kes_mcp.tools import search_chunks

        mock_auth = MagicMock()
        mock_auth.ensure_token = AsyncMock(return_value="fake-token")
        mock_auth.space_id = "sp-001"
        mock_auth.scope_kb_ids = None

        with patch("kes_mcp.tools._resolve_effective_kb_ids",
                   new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = ["kb-001"]

            result = await search_chunks(
                retrieval_orch=mock_retrieval_orch,
                auth=mock_auth,
                arguments={
                    "query": "PostgreSQL 主从复制",
                    "time_range": {"expired": "exclude"},
                },
            )

        data = result[0]
        # 3 个 chunk 中 c2 已过期，应被排除
        expired_chunks = [c for c in data["chunks"] if c["source"].get("is_expired")]
        assert len(expired_chunks) == 0, f"过期 chunk 应被排除，但仍有 {len(expired_chunks)} 个"
        assert data["total"] == 2  # c1 + c3

    @pytest.mark.asyncio
    async def test_time_range_only_expired(
        self, mock_retrieval_orch, chunks_with_time_meta
    ):
        """time_range.expired='only' 应仅返回已过期的历史文档。"""
        from kes_mcp.tools import search_chunks

        mock_auth = MagicMock()
        mock_auth.ensure_token = AsyncMock(return_value="fake-token")
        mock_auth.space_id = "sp-001"
        mock_auth.scope_kb_ids = None

        with patch("kes_mcp.tools._resolve_effective_kb_ids",
                   new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = ["kb-001"]

            result = await search_chunks(
                retrieval_orch=mock_retrieval_orch,
                auth=mock_auth,
                arguments={
                    "query": "PostgreSQL 旧版配置",
                    "time_range": {"expired": "only"},
                },
            )

        data = result[0]
        # 仅返回 c2（过期的）
        assert data["total"] == 1
        assert data["chunks"][0]["chunk_id"] == "c2"
        assert data["chunks"][0]["source"]["is_expired"] is True

    @pytest.mark.asyncio
    async def test_time_range_include_all(
        self, mock_retrieval_orch, chunks_with_time_meta
    ):
        """time_range.expired='include' 应返回所有 chunk（含过期）。"""
        from kes_mcp.tools import search_chunks

        mock_auth = MagicMock()
        mock_auth.ensure_token = AsyncMock(return_value="fake-token")
        mock_auth.space_id = "sp-001"
        mock_auth.scope_kb_ids = None

        with patch("kes_mcp.tools._resolve_effective_kb_ids",
                   new_callable=AsyncMock) as mock_resolve:
            mock_resolve.return_value = ["kb-001"]

            result = await search_chunks(
                retrieval_orch=mock_retrieval_orch,
                auth=mock_auth,
                arguments={
                    "query": "PostgreSQL 配置",
                    "time_range": {"expired": "include"},
                },
            )

        data = result[0]
        assert data["total"] == 3  # 全部返回

        # 验证同时包含过期和未过期
        has_expired = any(c["source"].get("is_expired") for c in data["chunks"])
        has_valid = any(not c["source"].get("is_expired") for c in data["chunks"])
        assert has_expired and has_valid, "include 模式应同时包含过期和未过期文档"


class TestIntersectKbIds:
    """验证权限交集不受时间元数据影响。"""

    def test_intersect_still_works(self):
        from kes_mcp.tools import intersect_kb_ids

        result = intersect_kb_ids(
            tool_kb_ids=["kb-1", "kb-2"],
            ace_kb_ids=["kb-1", "kb-2", "kb-3"],
            scope_kb_ids=["kb-1", "kb-2", "kb-3"],
        )
        assert set(result) == {"kb-1", "kb-2"}

    def test_empty_ace_returns_empty(self):
        from kes_mcp.tools import intersect_kb_ids
        assert intersect_kb_ids(["kb-1"], [], None) == []
