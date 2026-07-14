"""MCP Resource 数据格式验证 — 2 个 Resource: catalog + docs。"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestResourceDataFormat:

    def _mock_row(self, **kwargs):
        data = dict(kwargs)

        class _Row(dict):
            def __getattr__(self, key):
                return self.get(key)

        row = _Row(data)
        return row

    def _setup_pool(self, fetch_rows=None, fetchrow_result=None):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=fetch_rows or [])
        conn.fetchrow = AsyncMock(return_value=fetchrow_result)

        class _MockContext:
            async def __aenter__(self):
                return conn
            async def __aexit__(self, *_):
                pass

        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_MockContext())
        return pool

    def _setup_components(self, pool):
        components = MagicMock()
        components.retrieval_orch = MagicMock()
        components.retrieval_orch._hybrid_search = MagicMock()
        components.retrieval_orch._hybrid_search._dense = MagicMock()
        components.retrieval_orch._hybrid_search._dense._pgvector = MagicMock()
        components.retrieval_orch._hybrid_search._dense._pgvector.pool = pool
        components.auth = MagicMock()
        components.auth.ensure_token = AsyncMock(return_value="fake-token")
        components.auth.scope_kb_ids = None
        components.rate_limiter = MagicMock()
        components.rate_limiter.consume = AsyncMock(return_value=(True, 0))
        return components

    @pytest.mark.asyncio
    async def test_catalog_includes_kb_summary(self):
        """catalog 返回 kb_summary + space_type。"""
        from kes_mcp.resources_def import _read_catalog

        # Java API mock
        mock_kb_resp = MagicMock()
        mock_kb_resp.status_code = 200
        mock_kb_resp.json.return_value = {
            "data": [
                {"kbId": "kb-001", "name": "技术规范", "description": "",
                 "doc_count": 3, "spaceType": "ai_native"},
            ]
        }

        # DB mock for kb_summary
        pool = self._setup_pool([
            self._mock_row(summary="PostgreSQL 部署指南", topics='["PostgreSQL", "部署"]'),
            self._mock_row(summary="Redis 缓存配置", topics='["Redis", "缓存"]'),
            self._mock_row(summary="Nginx 反向代理", topics='["Nginx", "代理"]'),
        ])

        components = self._setup_components(pool)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_kb_resp)
            result = await _read_catalog(components)

        data = json.loads(result[0]["text"])
        assert len(data) == 1
        assert data[0]["kb_id"] == "kb-001"
        assert data[0]["space_type"] == "ai_native"
        assert "PostgreSQL" in data[0]["kb_summary"]
        assert data[0]["doc_count"] == 3

    @pytest.mark.asyncio
    async def test_docs_returns_document_list(self):
        """docs 返回文档列表含 summary/type/topics/not_covered/status。"""
        from kes_mcp.resources_def import _read_kb_docs

        pool = self._setup_pool([
            self._mock_row(doc_file="tech/高可用架构.md",
                          doc_id="doc-001",
                          summary="PostgreSQL 高可用架构设计指南",
                          doc_type="guide",
                          topics='["PostgreSQL", "高可用"]',
                          not_covered="不包含性能调优",
                          doc_expiry_date=None,
                          doc_version="v2.0"),
            self._mock_row(doc_file="policy/安全规范.md",
                          doc_id="doc-002",
                          summary="数据库安全配置规范",
                          doc_type="policy",
                          topics='["安全", "配置"]',
                          not_covered="",
                          doc_expiry_date=None,
                          doc_version=None),
        ])

        components = self._setup_components(pool)
        result = await _read_kb_docs(components, "kb-001")

        data = json.loads(result[0]["text"])
        assert data["kb_id"] == "kb-001"
        assert data["document_count"] == 2

        doc1 = data["documents"][0]
        assert doc1["doc_id"] == "doc-001"
        assert "PostgreSQL" in doc1["summary"]
        assert doc1["doc_type"] == "guide"
        assert "高可用" in doc1["topics"]
        assert doc1["status"] == "active"
        assert doc1["version"] == "v2.0"

    @pytest.mark.asyncio
    async def test_docs_title_extraction(self):
        """doc title 从文件路径提取。"""
        from kes_mcp.resources_def import _read_kb_docs

        pool = self._setup_pool([
            self._mock_row(doc_file="kb-001/员工手册-2025.docx",
                          doc_id="doc-001",
                          summary="员工手册", doc_type="manual",
                          topics='["制度"]', not_covered="",
                          doc_expiry_date=None, doc_version=None),
        ])

        components = self._setup_components(pool)
        result = await _read_kb_docs(components, "kb-001")

        data = json.loads(result[0]["text"])
        doc = data["documents"][0]
        assert doc["title"] == "员工手册-2025"

    @pytest.mark.asyncio
    async def test_docs_empty_kb(self):
        """空 KB 返回 isError。"""
        from kes_mcp.resources_def import _read_kb_docs

        pool = self._setup_pool([])
        components = self._setup_components(pool)
        result = await _read_kb_docs(components, "kb-empty")

        assert result.get("isError") is True
        data = json.loads(result["content"][0]["text"])
        assert "error" in data

    def test_resource_count(self):
        """验证 2 个 Resource 注册成功。"""
        from kes_mcp.resources_def import register_resources

        server = MagicMock()
        server.read_resource = lambda: (lambda fn: fn)

        called = None

        def _mock_list():
            def decorator(fn):
                nonlocal called
                called = fn
                return fn
            return decorator

        server.list_resources = _mock_list
        components = MagicMock()
        components.auth = MagicMock()
        components.auth.ensure_token = AsyncMock(return_value="fake-token")

        register_resources(server, components)
        assert called is not None

        import asyncio
        loop = asyncio.new_event_loop()
        resources = loop.run_until_complete(called())
        loop.close()

        assert len(resources) == 2
        uris = {r["uri"] for r in resources}
        assert "doc://catalog" in uris
        assert "doc://kb/{kb_id}/docs" in uris
