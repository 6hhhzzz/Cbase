"""意图路由器测试（向后兼容层）。

旧 IntentRouter 映射到新的 QueryPlan 模型。
测试规则匹配、LLM 兜底分类、_split_compare_query()。
"""

import pytest
from unittest.mock import AsyncMock

from retrieval.intent_router import IntentRouter
from retrieval.models import QueryPlan


class TestRuleBasedRouting:
    """测试规则匹配路径（不需要 LLM）。"""

    async def _route(self, query, mock_llm):
        router = IntentRouter(llm=mock_llm)
        return await router.route(query)

    @pytest.mark.asyncio
    async def test_compare_intent_by_rule(self, mock_llm):
        result = await self._route("A和B有什么区别", mock_llm)
        assert result.complexity == "simple"
        assert result.method == "rule"
        assert result.top_k == 8
        # 对比查询应生成子查询
        assert len(result.sub_queries) >= 2

    @pytest.mark.asyncio
    async def test_summary_intent_by_rule(self, mock_llm):
        result = await self._route("总结一下这个文档的内容", mock_llm)
        assert result.complexity == "simple"
        assert result.method == "rule"
        assert result.top_k == 15

    @pytest.mark.asyncio
    async def test_howto_intent_by_rule(self, mock_llm):
        result = await self._route("如何配置 Nginx 反向代理", mock_llm)
        assert result.complexity == "simple"
        assert result.method == "rule"
        assert result.top_k == 8

    @pytest.mark.asyncio
    async def test_compare_generates_sub_queries(self, mock_llm):
        """对比意图生成子查询（SubQuery 对象）。"""
        result = await self._route("Ubuntu 和 CentOS 的 Nginx 配置有什么不同", mock_llm)
        assert result.complexity == "simple"
        assert len(result.sub_queries) >= 2
        # 子查询是 SubQuery 对象
        for sq in result.sub_queries:
            assert sq.id.startswith("cq")
            assert sq.query

    @pytest.mark.asyncio
    async def test_howto_with_steps_keyword(self, mock_llm):
        result = await self._route("部署步骤", mock_llm)
        assert result.complexity == "simple"

    @pytest.mark.asyncio
    async def test_summary_with_overview_keyword(self, mock_llm):
        result = await self._route("项目概述", mock_llm)
        assert result.complexity == "simple"


class TestLLMFallback:
    """测试 LLM 兜底分类。"""

    @pytest.mark.asyncio
    async def test_fallback_to_llm_when_no_rule_match(self, mock_llm):
        """无规则匹配时调用 LLM。"""
        mock_llm.generate_content.return_value.content = "factoid"
        router = IntentRouter(llm=mock_llm)
        result = await router.route("请详细说明一下这个技术方案的优缺点")
        assert result.method == "llm"
        assert result.complexity == "simple"

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_factoid(self, mock_llm):
        """LLM 失败时降级为 simple。"""
        mock_llm.generate_content.side_effect = Exception("API 不可用")
        router = IntentRouter(llm=mock_llm)
        result = await router.route("一个无规则匹配的查询")
        assert result.complexity == "simple"
        assert result.method == "fallback"


class TestSplitCompareQuery:
    """测试对比查询拆分。"""

    def _route_direct(self, query, mock_llm):
        """直接调用 _split_compare_query。"""
        router = IntentRouter(llm=mock_llm)
        return router._split_compare_query(query)

    def test_split_by_he(self, mock_llm):
        parts = self._route_direct("MySQL 和 PostgreSQL 对比", mock_llm)
        assert len(parts) >= 2
        assert "MySQL" in parts[0]

    def test_split_by_vs(self, mock_llm):
        parts = self._route_direct("Redis vs Memcached 性能对比", mock_llm)
        assert len(parts) >= 2

    def test_single_entity_no_split(self, mock_llm):
        parts = self._route_direct("数据库性能优化方案", mock_llm)
        assert parts == []

    def test_split_by_yu(self, mock_llm):
        parts = self._route_direct("Docker 与 Kubernetes 区别", mock_llm)
        assert len(parts) >= 2
