"""MCP Tool 定义与路由 — 协议层强化版。

由 server.py 调用 register_tools() 注册到 MCP Server 实例。
组件通过 MCPComponents 对象注入，消除全局可变状态。
"""

import json

from common import get_logger
from kes_mcp.auth import (
    KeyAuthError,
    KeyRevokedError,
    KeyExpiredError,
    KeyInvalidError,
    KeyConnectionError,
)
from kes_mcp.tools import search_chunks, read_document, ask_expert

logger = get_logger(__name__)

# ---- 共享描述常量 ----

_QUERY_DESCRIPTION = (
    "搜索查询。为了获得最佳检索效果，请：\n"
    "1. 包含具体的产品/系统名称、版本号、模块名、技术术语\n"
    "2. 包含关键实体：错误码、配置项名称、文件名、API 名称等\n"
    "3. 如果用户提供了背景信息（系统版本、运行环境、已尝试的步骤），请将其融入 query\n"
    '4. 避免过于宽泛的提问（如 "怎么用"），尽量具体化（如 "XX系统后台管理界面如何添加新用户并分配角色"）\n\n'
    "示例 —\n"
    '优: "XX系统 v3.0 Ubuntu 22.04 Docker 部署时出现 Error 10061 端口冲突"\n'
    '劣: "部署报错"'
)

_CONTEXT_HINT_DESC = (
    "补充背景信息（可选）。如果你已知用户的系统环境、之前讨论过的内容、"
    "相关的模块或功能名称，请在此提供。这些信息不会被直接作为检索关键词，"
    "而是帮助检索系统更好地理解查询意图。\n"
    '例: "用户在使用XX系统 v3.0 企业版，环境为 Ubuntu 22.04 + Docker 24+，'
    '之前提到过已经完成基础安装，现在卡在配置阶段"'
)

_FOCUS_ASPECTS_DESC = (
    "限定检索关注的方面（可选）。当用户明确要查某个特定类型的信息时使用。\n"
    "可选值: installation(安装部署), configuration(配置参数), "
    "troubleshooting(故障排查), api_reference(API参考), "
    "best_practices(最佳实践), security(安全相关), version_history(版本变更)"
)

_DOC_TYPE_DESC = (
    "限定文档类型（可选）。不传则搜索全部类型。\n"
    "可选值: manual(手册), policy(制度规范), report(报告), "
    "guide(指南), specification(技术规格), any(不限定)"
)

_KB_IDS_DESC = (
    "可选，限定搜索的知识库 ID 列表。"
    "如果已知目标知识库，优先传入以缩小检索范围、提高精度。"
    "可先调用 doc://catalog Resource 获取可用的 KB 列表及概览。"
)

# ---- 内部工具 ----

def _tool_error(message: str) -> dict:
    """构造 MCP 协议级错误响应 — 含 isError 标记。"""
    return {
        "content": [{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
        "isError": True,
    }


# ---- 注册入口 ----

def register_tools(server, components):
    """向 MCP Server 注册所有 Tool 的 schema、路由和执行逻辑。"""

    @server.list_tools()
    async def handle_list_tools():
        return [
            _search_chunks_schema(),
            _read_document_schema(),
            _ask_expert_schema(),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        logger.info(f"MCP Tool 调用: {name}")

        try:
            if name == "search_chunks":
                result = await search_chunks(
                    components.retrieval_orch, components.auth, arguments)
            elif name == "read_document":
                result = await read_document(components.auth, arguments)
            elif name == "ask_expert":
                result = await ask_expert(
                    components.llm, components.retrieval_orch,
                    components.context_assembler, components.auth, arguments)
            else:
                return _tool_error(f"未知 Tool: {name}")

            for r in result:
                if isinstance(r, dict) and "error" in r:
                    return _tool_error(r["error"])

            return [{"type": "text", "text": json.dumps(r, ensure_ascii=False)} for r in result]

        except KeyRevokedError as e:
            logger.warning(f"Tool {name}: API 密钥已撤销")
            return _tool_error(f"API 密钥已撤销，请到 KES 管理界面创建新密钥: {e}")
        except KeyExpiredError as e:
            logger.warning(f"Tool {name}: API 密钥已过期")
            return _tool_error(f"API 密钥已过期，请到 KES 管理界面续期或创建新密钥: {e}")
        except KeyInvalidError as e:
            logger.warning(f"Tool {name}: API 密钥无效")
            return _tool_error(f"API 密钥无效: {e}")
        except KeyConnectionError as e:
            logger.error(f"Tool {name}: 认证服务连接失败")
            return _tool_error(f"无法连接到 KES 认证服务，请检查网络或 KES 服务状态: {e}")
        except KeyAuthError as e:
            logger.error(f"Tool {name}: 鉴权异常")
            return _tool_error(f"鉴权失败: {e}")
        except Exception as e:
            logger.error(f"Tool {name} 执行失败: {e}")
            return _tool_error(f"工具执行失败: {e}")


def _search_chunks_schema():
    return {
        "name": "search_chunks",
        "description": (
            "在 KES 企业知识库中执行语义 + 关键词混合检索，返回相关文档块及完整元数据"
            "（来源文档、页码、相关性分数）。\n\n"
            "🔍 适用场景：\n"
            "- Agent 需要获取原始事实片段，自己组合上下文\n"
            "- Agent 需要向用户展示原始文档出处和页码\n"
            "- Agent 需要分析多个来源、综合判断\n"
            "- 需要精确的文档位置信息（页码、文档名、相关性分数）\n\n"
            "💡 建议工作流: 先调用 doc://catalog 了解可用的知识库及其内容概况 → 再用本 tool 精确检索。\n\n"
            "⚠️ 与 ask_expert 的区别: search_chunks 只返回检索到的原始文档块，不调用 LLM 生成答案。"
            "如果你需要直接的自然语言回答（带引用），请使用 ask_expert。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": _QUERY_DESCRIPTION},
                "kb_ids": {"type": "array", "items": {"type": "string"}, "description": _KB_IDS_DESC},
                "top_k": {"type": "integer", "description": "返回结果数，默认 10。需要更多候选时调大（如 20），需要更精确时调小（如 5）"},
                "include_context": {"type": "boolean", "description": "是否包含上下文扩充文本（标题、前后文），默认 true"},
                "context_hint": {"type": "string", "description": _CONTEXT_HINT_DESC},
                "focus_aspects": {"type": "array", "items": {"type": "string", "enum": [
                    "installation", "configuration", "troubleshooting",
                    "api_reference", "best_practices", "security", "version_history",
                ]}, "description": _FOCUS_ASPECTS_DESC},
                "doc_type": {"type": "string", "enum": ["manual", "policy", "report", "guide", "specification", "any"], "description": _DOC_TYPE_DESC},
            },
            "required": ["query"],
        },
    }


def _read_document_schema():
    return {
        "name": "read_document",
        "description": (
            "读取指定文档的完整元数据和内容。\n\n"
            "🔍 适用场景：\n"
            "- Agent 需要确认文档来源、作者、创建时间、生效日期\n"
            "- Agent 需要获取文档的完整内容（非片段）\n"
            "- Agent 需要验证检索结果中的文档是否可信（检查版本、状态）\n\n"
            "💡 doc_id 可从 search_chunks 返回结果中的 source.doc_id 字段获取。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string", "description": "文档 ID。可从 search_chunks 返回的 source.doc_id 字段获取"}},
            "required": ["doc_id"],
        },
    }


def _ask_expert_schema():
    return {
        "name": "ask_expert",
        "description": (
            "向 KES 企业知识库提问，获得基于检索文档生成的带引用自然语言答案。\n\n"
            "此 tool 内部执行: 检索 → 上下文组装 → LLM 生成 → 引用标注。\n\n"
            "🔍 适用场景：\n"
            "- Agent 需要直接获取答案、结论或操作指南（而非自己拼装上下文）\n"
            "- 用户期望自然语言回答而非原始文档片段\n"
            "- 答案需要有明确的文档出处以支撑事实核查\n\n"
            "⚠️ 与 search_chunks 的区别: ask_expert 多一层 LLM 生成，返回带引用的自然语言答案。"
            "如果你需要更精细控制检索结果或自己组合分析，请使用 search_chunks。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": _QUERY_DESCRIPTION},
                "kb_ids": {"type": "array", "items": {"type": "string"}, "description": _KB_IDS_DESC},
                "top_k": {"type": "integer", "description": "检索数量，默认 5。检索越多，答案覆盖越全但可能引入噪音"},
                "context_hint": {"type": "string", "description": _CONTEXT_HINT_DESC},
                "focus_aspects": {"type": "array", "items": {"type": "string", "enum": [
                    "installation", "configuration", "troubleshooting",
                    "api_reference", "best_practices", "security", "version_history",
                ]}, "description": _FOCUS_ASPECTS_DESC},
            },
            "required": ["query"],
        },
    }
