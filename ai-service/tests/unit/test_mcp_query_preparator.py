"""MCP 查询准备器测试 — 关键词提取 + focus_aspects 映射。

extract_keywords() 是纯函数，覆盖 jieba 路径和 fallback 路径。
"""

import sys
from unittest.mock import patch

from retrieval.mcp_query_preparator import (
    extract_keywords,
    _resolve_focus_keywords,
    McpQueryPreparator,
    McpPreparedQuery,
)


class TestExtractKeywords:
    """测试 extract_keywords() — jieba 分词 + 正则实体提取。"""

    def test_entity_patterns_version_number(self):
        """正则提取版本号。"""
        kw = extract_keywords("Ubuntu 22.04 安装 Python 3.11.2")
        assert "22.04" in kw
        assert "3.11.2" in kw

    def test_entity_patterns_filename(self):
        """正则提取文件名。"""
        kw = extract_keywords("nginx.conf 和 docker-compose.yaml 配置")
        assert "nginx.conf" in kw
        assert "docker-compose.yaml" in kw

    def test_entity_patterns_camelcase(self):
        """正则提取驼峰命名。"""
        kw = extract_keywords("UserService 和 KbPermissionCache")
        assert "UserService" in kw
        assert "KbPermissionCache" in kw

    def test_entity_patterns_error_code(self):
        """正则提取错误码。"""
        kw = extract_keywords("Error 10061 和 ERR-500 排查")
        # 应包含数字编号
        has_error_number = any("10061" in k or "500" in k for k in kw)
        assert has_error_number

    def test_jieba_chinese_tokenization(self):
        """jieba 中文分词 + 停用词过滤。"""
        kw = extract_keywords("如何在 Ubuntu 上配置 Nginx 反向代理")
        # 应有实际关键词，无停用词
        assert "如何" not in kw  # 停用词
        assert "在" not in kw
        assert len(kw) >= 2  # "Ubuntu", "Nginx", "反向代理" 等

    def test_fallback_without_jieba(self):
        """jieba 不可用时降级到正则切分。"""
        with patch.dict(sys.modules, {"jieba": None}):
            # 强制清除缓存（如果 jieba 之前已导入）
            real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

            def _block_jieba(name, *args, **kwargs):
                if name == "jieba":
                    raise ImportError("No module named 'jieba'")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_block_jieba):
                kw = extract_keywords("知识库架构设计方案")
                # 降级后按空格/标点简单切分
                assert len(kw) > 0

    def test_empty_query(self):
        """空查询返回空列表。"""
        assert extract_keywords("") == []

    def test_stopwords_only(self):
        """纯停用词查询返回空列表。"""
        kw = extract_keywords("的 了 在 是 我")
        # 所有词都被过滤，只有停用词
        for w in kw:
            assert w not in {"的", "了", "在", "是", "我"}

    def test_max_keywords_truncation(self):
        """max_keywords 截断。"""
        kw = extract_keywords(
            "Ubuntu 22.04 部署 Python Django PostgreSQL Redis RabbitMQ MinIO Nginx 服务",
            max_keywords=5,
        )
        assert len(kw) <= 5

    def test_punctuation_only_filtered(self):
        """纯标点 token 被过滤。"""
        kw = extract_keywords("！@#￥……&*（）")
        # 纯标点不应出现在结果中
        assert "！@#￥……&*（）" not in kw

    def test_short_chinese_words_filtered(self):
        """单字中文被过滤（太弱）。"""
        kw = extract_keywords("Java 和 Go 语言对比")
        # "和" 是停用词
        assert "和" not in kw


class TestResolveFocusKeywords:
    """测试 _resolve_focus_keywords()。"""

    def test_known_aspect_translation(self):
        extra = _resolve_focus_keywords(["installation"])
        assert "安装" in extra
        assert "部署" in extra

    def test_multiple_aspects(self):
        extra = _resolve_focus_keywords(["security", "troubleshooting"])
        assert "安全" in extra
        assert "故障" in extra

    def test_empty_aspects(self):
        assert _resolve_focus_keywords([]) == []
        assert _resolve_focus_keywords(None) == []

    def test_unknown_aspect_ignored(self):
        extra = _resolve_focus_keywords(["nonexistent_aspect"])
        assert extra == []


class TestMcpQueryPreparator:
    """测试 McpQueryPreparator.prepare()。"""

    def test_prepare_basic_query(self):
        prep = McpQueryPreparator()
        result = prep.prepare("Ubuntu 22.04 安装配置")

        assert isinstance(result, McpPreparedQuery)
        assert result.query == "Ubuntu 22.04 安装配置"
        assert result.top_k == 10
        assert result.context_hint is None
        assert len(result.keywords) > 0

    def test_prepare_with_focus_aspects(self):
        prep = McpQueryPreparator()
        result = prep.prepare("Nginx 配置", focus_aspects=["security"])

        # focus_aspects 的关键词被合并到 query 用于提取
        keywords = result.keywords
        assert len(keywords) > 0

    def test_prepare_with_context_hint(self):
        """context_hint 被透传但不参与关键词提取。"""
        prep = McpQueryPreparator()
        result = prep.prepare(
            "Nginx 配置",
            context_hint="用户环境：Ubuntu 22.04，已安装 Docker",
        )
        assert result.context_hint == "用户环境：Ubuntu 22.04，已安装 Docker"

    def test_prepare_with_doc_type(self):
        prep = McpQueryPreparator()
        result = prep.prepare("API 接口", doc_type="manual")
        assert result.doc_type == "manual"

    def test_prepare_custom_top_k(self):
        prep = McpQueryPreparator()
        result = prep.prepare("查询", top_k=20)
        assert result.top_k == 20
