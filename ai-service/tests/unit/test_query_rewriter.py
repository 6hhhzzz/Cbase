"""Query 改写器测试。

测试 should_rewrite() 短路条件、_has_concrete_entities()、_parse_rewrite_response()。
"""

import json
import pytest

from retrieval.query_rewriter import (
    QueryRewriter,
    _parse_rewrite_response,
)


class TestShouldRewrite:
    """测试 should_rewrite() 短路条件。"""

    def test_no_history_returns_false(self, mock_llm):
        rewriter = QueryRewriter(llm=mock_llm)
        assert rewriter.should_rewrite("任何查询", history_len=0) is False

    def test_long_query_with_entities_returns_false(self, mock_llm):
        """长查询(>80字符)含具体实体 → 不需要改写。"""
        rewriter = QueryRewriter(llm=mock_llm)
        very_long = "请详细说明在 Ubuntu 22.04 LTS 系统上如何配置和优化 PostgreSQL 16 数据库的主从流复制和自动故障转移方案的完整步骤和注意事项" * 2
        result = rewriter.should_rewrite(very_long, history_len=3)
        assert result is False

    def test_short_query_with_history_returns_true(self, mock_llm):
        """短查询有历史 → 需要改写。"""
        rewriter = QueryRewriter(llm=mock_llm)
        assert rewriter.should_rewrite("怎么做", history_len=3) is True

    def test_short_query_without_entities(self, mock_llm):
        """短查询且无具体实体 → 需要改写。"""
        rewriter = QueryRewriter(llm=mock_llm)
        assert rewriter.should_rewrite("它怎么配置", history_len=2) is True

    def test_rate_limit_within_60_seconds(self, mock_llm):
        """60 秒内刚做过改写 → 跳过。"""
        rewriter = QueryRewriter(llm=mock_llm)
        # 手动设置上次改写时间
        import time
        rewriter._last_rewrite_time = time.time()
        assert rewriter.should_rewrite("怎么做", history_len=3) is False


class TestHasConcreteEntities:
    """测试 _has_concrete_entities()。"""

    def test_alphanumeric_code(self, mock_llm):
        rewriter = QueryRewriter(llm=mock_llm)
        assert rewriter._has_concrete_entities("如何配置 nginx1.20") is True

    def test_quoted_text(self, mock_llm):
        rewriter = QueryRewriter(llm=mock_llm)
        assert rewriter._has_concrete_entities('关于「知识库架构」的设计') is True

    def test_long_query(self, mock_llm):
        rewriter = QueryRewriter(llm=mock_llm)
        long_text = "这是一个很长很长的问题包含了非常多的细节信息需要仔细考虑和处理分析" * 3
        assert rewriter._has_concrete_entities(long_text) is True

    def test_short_generic_query(self, mock_llm):
        rewriter = QueryRewriter(llm=mock_llm)
        assert rewriter._has_concrete_entities("怎么做") is False


class TestParseRewriteResponse:
    """测试 _parse_rewrite_response()。"""

    def test_valid_json(self):
        resp = json.dumps({
            "rewritten_query": "如何配置 Ubuntu 22.04 上的 Nginx",
            "keywords": ["Ubuntu", "Nginx", "配置"],
        })
        result = _parse_rewrite_response(resp, "原查询")
        assert result.rewritten_query == "如何配置 Ubuntu 22.04 上的 Nginx"
        assert "Nginx" in result.keywords
        assert result.skipped is False

    def test_json_in_markdown_code_block(self):
        resp = '''```json
{"rewritten_query": "改写后的查询", "keywords": ["A", "B"]}
```'''
        result = _parse_rewrite_response(resp, "原查询")
        assert result.rewritten_query == "改写后的查询"

    def test_invalid_response_falls_back(self):
        resp = "这不是一个有效的 JSON 响应"
        result = _parse_rewrite_response(resp, "原始问题")
        assert result.rewritten_query == "原始问题"
        assert result.skipped is True

    def test_missing_fields_uses_fallback(self):
        resp = '{"keywords": ["a"]}'
        result = _parse_rewrite_response(resp, "备份查询")
        assert result.rewritten_query == "备份查询"
        assert result.keywords == ["a"]


class TestRewrite:
    """测试 rewrite() 异步流程。"""

    @pytest.mark.asyncio
    async def test_rewrite_without_history_returns_skipped(self, mock_llm):
        rewriter = QueryRewriter(llm=mock_llm)
        result = await rewriter.rewrite("查询", history=None)
        assert result.skipped is True
        assert result.rewritten_query == "查询"

    @pytest.mark.asyncio
    async def test_rewrite_with_history_calls_llm(self, mock_llm):
        mock_llm.generate_content.return_value.content = json.dumps({
            "rewritten_query": "如何在 Ubuntu 上安装 PostgreSQL",
            "keywords": ["Ubuntu", "PostgreSQL", "安装"],
        })
        rewriter = QueryRewriter(llm=mock_llm)
        history = [
            {"role": "user", "content": "如何安装 MySQL"},
            {"role": "assistant", "content": "请使用 apt install mysql-server"},
        ]
        result = await rewriter.rewrite("那 PostgreSQL 呢", history)
        assert result.skipped is False
        assert "PostgreSQL" in result.rewritten_query

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self, mock_llm):
        mock_llm.generate_content.side_effect = Exception("LLM 不可用")
        rewriter = QueryRewriter(llm=mock_llm)
        history = [{"role": "user", "content": "你好"}]
        result = await rewriter.rewrite("那怎么配置", history)
        assert result.skipped is True
        assert result.rewritten_query == "那怎么配置"
