"""MCP Tool 定义与路由 — 协议层强化版。

由 server.py 调用 register_tools() 注册到 MCP Server 实例。
组件通过 MCPComponents 对象注入，消除全局可变状态。
"""

import asyncio
import json

from common import get_logger
from kes_mcp.auth import (
    KeyAuthError,
    KeyRevokedError,
    KeyExpiredError,
    KeyInvalidError,
    KeyConnectionError,
)
from kes_mcp.tools import search_chunks, report_quality, submit_document

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

# ---- Tool 执行超时 ----

_TOOL_TIMEOUT_SECONDS = 30
_TOOL_SEMAPHORE = asyncio.Semaphore(5)  # 最多 5 个 Tool 并发，pgvector pool=10


def _timeout_error(tool_name: str) -> dict:
    """构造超时错误响应。"""
    return _tool_error(
        f"Tool '{tool_name}' 执行超时（{_TOOL_TIMEOUT_SECONDS}s）。"
        f"请检查查询是否过于宽泛，或缩小 kb_ids 范围后重试。"
    )


# ---- 内部工具 ----

def _tool_error(message: str) -> dict:
    """构造 MCP 协议级错误响应 — 含 isError 标记。"""
    return {
        "content": [{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
        "isError": True,
    }


def _rate_limit_error(retry_after: float) -> dict:
    """构造频率限制错误响应。"""
    wait = max(1, int(retry_after))
    return _tool_error(
        f"调用频率超限（突发容量 30 次，填充速率 1 次/秒），请在 {wait} 秒后重试"
    )


# ---- 注册入口 ----

def register_tools(server, components):
    """向 MCP Server 注册所有 Tool 的 schema、路由和执行逻辑。"""

    @server.list_tools()
    async def handle_list_tools():
        return [
            _search_chunks_schema(),
            _report_quality_schema(),
            _submit_document_schema(),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        logger.info(f"MCP Tool 调用: {name}")

        # 频率限制检查
        if components.rate_limiter:
            allowed, retry_after = await components.rate_limiter.consume()
            if not allowed:
                logger.warning(f"Tool '{name}' 被限流，建议等待 {retry_after:.1f}s")
                return _rate_limit_error(retry_after)

        async def _execute():
            async with _TOOL_SEMAPHORE:
                if name == "search_chunks":
                    result = await search_chunks(
                        components.retrieval_orch, components.auth, arguments)
                elif name == "report_quality":
                    result = await report_quality(
                        components.retrieval_orch, components.auth, arguments)
                elif name == "submit_document":
                    result = await submit_document(
                        components.retrieval_orch, components.auth, arguments)
                else:
                    return _tool_error(f"未知 Tool: {name}")

                for r in result:
                    if isinstance(r, dict) and "error" in r:
                        return _tool_error(r["error"])

                return [{"type": "text", "text": json.dumps(r, ensure_ascii=False)} for r in result]

        try:
            return await asyncio.wait_for(_execute(), timeout=_TOOL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(f"Tool '{name}' 执行超时 ({_TOOL_TIMEOUT_SECONDS}s)")
            return _timeout_error(name)
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
            "在 KES 企业知识库中执行 2 路混合检索（语义向量 + BM25 关键词），"
            "返回相关文档块及完整元数据（来源文档、页码、相关性分数）。\n\n"
            "🔍 适用场景：\n"
            "- Agent 需要获取原始事实片段，自己组合上下文\n"
            "- Agent 需要向用户展示原始文档出处和页码\n"
            "- Agent 需要分析多个来源、综合判断\n"
            "- 需要精确的文档位置信息（页码、文档名、相关性分数）\n\n"
            "💡 建议工作流: 先调用 doc://catalog 了解可用的知识库及其内容概况 → 再用本 tool 精确检索。\n\n"
            "🔬 检索机制：\n"
            "- Dense（语义向量）：基于 HNSW 向量索引的语义检索，理解查询意图\n"
            "- BM25（关键词）：基于 jieba 分词的精确关键词匹配，确保专有名词召回\n"
            "- SPLADE（神经扩展）：用神经网络扩展查询词，桥接用户用语和文档术语的鸿沟\n"
            "- 以上三路结果经 RRF（Reciprocal Rank Fusion）融合后由 Cross-Encoder Reranker 重排序\n\n"
            "⚠️ 注意: search_chunks 只返回检索到的原始文档块，不调用 LLM 生成答案。"
            "Agent 应基于返回结果自行组装上下文并生成回答。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": _QUERY_DESCRIPTION},
                "kb_ids": {"type": "array", "items": {"type": "string"}, "description": _KB_IDS_DESC},
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "description": (
                        "最大返回 chunk 数（默认 10，范围 1~30）。注意这是上限而非保证数——"
                        "低置信度（reranker 分数 < 0.3）的 chunk 会被自动过滤，实际返回数可能更少。\n\n"
                        "检索使用 3 路混合（语义 + 关键词 + SPLADE 神经扩展），"
                        "因此即使 Agent 使用的术语与文档不完全一致，仍有较高召回概率。\n\n"
                        "选择建议：\n"
                        "- 5~8: 精确事实查找（如查某个配置项、错误码含义）\n"
                        "- 10~15: 一般性技术问题（默认范围）\n"
                        "- 15~20: 探索性搜索，需要更多候选来综合分析\n"
                        "- 20~30: 全面调研，需要覆盖多个方面\n\n"
                        "策略提示：\n"
                        "- 如果不确定知识库覆盖情况，先用较小值（5~8）试探\n"
                        "- 如果返回数远小于请求数（+ filtered_count 不为零），说明匹配度低，"
                        "应尝试重构 query 或放宽 focus_aspects\n"
                        "- 如果已限定 focus_aspects 或 doc_type，可适当增大 top_k 以在限定范围内获取更多结果"
                    ),
                },
                "include_context": {"type": "boolean", "description": "是否包含上下文扩充文本（标题、前后文），默认 true"},
                "context_hint": {"type": "string", "description": _CONTEXT_HINT_DESC},
                "focus_aspects": {"type": "array", "items": {"type": "string", "enum": [
                    "installation", "configuration", "troubleshooting",
                    "api_reference", "best_practices", "security", "version_history",
                ]}, "description": _FOCUS_ASPECTS_DESC},
                "doc_type": {"type": "string", "enum": ["manual", "policy", "report", "guide", "specification", "any"], "description": _DOC_TYPE_DESC},
                "time_range": {
                    "type": "object",
                    "description": (
                        "按文档时效过滤（可选）。KES 中的文档有生效日期(doc_effective_date)和失效日期(doc_expiry_date)。"
                        "检索结果中每条 chunk 的 source 字段包含这些时间信息和一个 is_expired 标志位。"
                    ),
                    "properties": {
                        "expired": {
                            "type": "string",
                            "enum": ["exclude", "include", "only"],
                            "description": (
                                "过期文档策略。exclude=排除过期文档(默认), "
                                "include=包含过期文档(新旧混合), "
                                "only=仅查看已过期的历史文档(用于查询'之前的规定是什么')"
                            ),
                        },
                    },
                },
            },
            "required": ["query"],
        },
    }


def _report_quality_schema():
    return {
        "name": "report_quality",
        "description": (
            "上报检索质量反馈。当你（Agent）发现 search_chunks 返回的结果不够好，"
            "导致无法正确回答用户问题时，调用此 Tool 记录问题。"
            "KES 会根据反馈数据持续优化检索策略。\n\n"
            "🔍 使用方式：\n"
            "1. 从 search_chunks 的返回结果中获取 trace_id\n"
            "2. 如果检索结果不佳，调用本 Tool 上报\n"
            "3. 如果结果满意，无需调用（不上报即视为默认满意）\n\n"
            "⚠️ 注意：trace_id 有效期为 10 分钟，过期后无法上报。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "trace_id": {
                    "type": "string",
                    "description": "search_chunks 返回的 trace_id（必需）",
                },
                "rating": {
                    "type": "string",
                    "enum": ["like", "dislike"],
                    "description": "评价：like=检索结果满意，dislike=检索结果不佳",
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "可选反馈原因，dislike 时建议填写。"
                        "如: '答非所问'、'内容过时'、'缺少关键信息'、'检索结果不相关'"
                    ),
                },
            },
            "required": ["trace_id", "rating"],
        },
    }


def _submit_document_schema():
    return {
        "name": "submit_document",
        "description": (
            "向 KES 知识库提交一份新文档。仅可在 AI 原生 Space（space_type=ai_native）中使用。\n\n"
            "📝 文档格式要求（Markdown）：\n"
            "1. 必须有标题（# 开头的顶级标题）\n"
            "2. 内容结构化：使用 ##/### 分隔章节，列表用 - 或 1.\n"
            "3. 关键术语使用**加粗**标注\n"
            "4. 如果是修订旧文档，在 content 开头注明「替代: <旧文档标题>」\n\n"
            "🔍 提交后，KES 内部 Agent 会：\n"
            "1. 校验文档格式和内容一致性\n"
            "2. 自动归类到合适的知识库\n"
            "3. 生成文档摘要供后续检索使用\n\n"
            "⚠️ 仅 AI 原生 Space 支持此功能。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_title": {
                    "type": "string",
                    "description": "文档标题（必填）。用作后续检索时的文档标识。",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "文档正文（Markdown 格式，必填）。\n"
                        "规范：\n"
                        "- # 顶级标题（文档名）\n"
                        "- ## 章节标题\n"
                        "- ### 子章节\n"
                        "- 列表用 - 或 1. 2. 3.\n"
                        "- 关键术语 **加粗**\n"
                        "- 表格用 markdown table"
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "文档摘要（100-200 字，必填）。简要概括文档主题、适用范围和主要内容。\n"
                        "用于 KES catalog 展示，帮助其他 Agent 判断是否需要检索此文档。"
                    ),
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "关键词列表（3-8 个，必填）。帮助精确分类和检索。",
                },
                "doc_type": {
                    "type": "string",
                    "enum": ["policy", "manual", "report", "guide", "specification"],
                    "description": "文档类型（必填）。影响后续分块和检索策略。",
                },
                "kb_id": {
                    "type": "string",
                    "description": (
                        "可选，指定目标知识库 ID。如果不指定，KES 内部 Agent 会自动选择最合适的 KB。\n"
                        "可先调用 doc://catalog Resource 获取可用的 KB 列表。"
                    ),
                },
            },
            "required": ["doc_title", "content", "summary", "keywords", "doc_type"],
        },
    }
