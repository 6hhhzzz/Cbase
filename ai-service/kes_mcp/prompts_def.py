"""MCP Prompt 定义与生成 — 使用指导 + 结果模板。

由 server.py 调用 register_prompts() 注册到 MCP Server 实例。
"""

from common import get_logger

logger = get_logger(__name__)


def register_prompts(server, components):
    """向 MCP Server 注册 Prompt 的 schema 和内容生成。"""

    @server.list_prompts()
    async def handle_list_prompts():
        return [
            {
                "name": "kb_search_strategy",
                "description": (
                    "KES 企业知识库检索最佳实践 — 教授外部 Agent 如何从用户问题构造高质量查询、"
                    "如何选择合适的 Tool，以及在多 KB 场景下的检索策略。"
                ),
                "arguments": [
                    {"name": "user_question", "description": "用户向你提出的原始问题", "required": True},
                    {"name": "known_context", "description": "你已知的背景信息（如用户使用的系统、版本、环境等）", "required": False},
                ],
            },
            {
                "name": "qa_template",
                "description": (
                    "标准 RAG 问答模板 — 基于检索到的文档片段回答问题并标注引用。"
                    "用于 KES 内部的 LLM 生成阶段，或供外部 Agent 直接使用。"
                ),
                "arguments": [
                    {"name": "chunks", "description": "search_chunks 返回的检索文档块", "required": True},
                    {"name": "query", "description": "用户问题", "required": True},
                ],
            },
            {
                "name": "document_analysis",
                "description": (
                    "文档分析模板 — 提取核心要点、风险项和行动建议。"
                    "适合对 read_document 获取的完整文档内容做结构化分析。"
                ),
                "arguments": [
                    {"name": "document_content", "description": "read_document 返回的文档完整内容", "required": True},
                ],
            },
        ]

    @server.get_prompt()
    async def handle_get_prompt(name: str, arguments: dict | None):
        if name == "kb_search_strategy":
            return _generate_search_strategy(arguments)
        if name == "qa_template":
            return _generate_qa_template(arguments)
        if name == "document_analysis":
            return _generate_document_analysis(arguments)
        raise ValueError(f"未知 Prompt: {name}")


def _generate_search_strategy(arguments: dict | None):
    user_question = (arguments or {}).get("user_question", "{{user_question}}")
    known_context = (arguments or {}).get("known_context", "")
    ctx_block = f"\n\n已知背景信息: {known_context}" if known_context else ""
    return [{
        "role": "user",
        "content": {
            "type": "text",
            "text": (
                "你正在使用一个企业知识库检索系统（KES）。用户的问题是：\n\n"
                f'"{user_question}"{ctx_block}\n\n'
                "在调用 KES 的 search_chunks 或 ask_expert 工具之前，请按以下步骤分析：\n\n"
                "## 1. 提取关键实体\n"
                "- 从用户问题中识别：产品名、系统名、版本号、模块名、错误码、文件名\n"
                "- 从已知背景中提取：运行环境、已尝试步骤、相关配置\n\n"
                "## 2. 判断信息需求类型\n"
                "- 事实查询（某参数的值、某错误的含义）→ 用 search_chunks，获取精确片段\n"
                "- 操作步骤（怎么安装、如何配置）→ 用 ask_expert，获取完整流程\n"
                "- 对比分析（A 和 B 的区别）→ 用 search_chunks，自己综合判断\n"
                "- 概念了解（什么是 XX）→ 用 ask_expert，获取解释\n"
                "- 来源确认（这个信息来自哪个文档）→ 用 read_document\n\n"
                "## 3. 构造高质量查询\n"
                "- 将松散的口语表达转化为精确的技术术语\n"
                "- 融入已知背景中的环境/版本信息\n"
                "- 将关键词按照重要性排序\n\n"
                "## 4. 选择策略\n"
                "- 如果已知目标知识库 → 传入 kb_ids 参数\n"
                "- 如果不确定 → 先读 doc://catalog 了解可用 KB\n"
                "- 如果问题涉及特定方面 → 传入 focus_aspects 参数\n"
                "- 如果已有用户背景 → 传入 context_hint 参数\n\n"
                "请根据以上分析，确定应使用的工具和参数，然后执行调用。"
            ),
        },
    }]


def _generate_qa_template(arguments: dict | None):
    chunks = (arguments or {}).get("chunks", "{{chunks}}")
    query = (arguments or {}).get("query", "{{query}}")
    return [{
        "role": "user",
        "content": {
            "type": "text",
            "text": (
                "你是一个企业知识助手。仅根据以下检索到的文档片段回答用户问题。"
                "如果文档片段中不包含相关信息，请明确告知，不要编造。\n\n"
                f"文档片段:\n{chunks}\n\n"
                f"问题: {query}\n\n"
                "请标注每个事实对应的文档来源。"
            ),
        },
    }]


def _generate_document_analysis(arguments: dict | None):
    content = (arguments or {}).get("document_content", "{{document_content}}")
    return [{
        "role": "user",
        "content": {
            "type": "text",
            "text": (
                f"请分析以下文档的关键信息：\n\n{content}\n\n"
                "请输出：\n"
                "1. 核心要点（3-5 条，每条一句话）\n"
                "2. 风险项（如有，标注严重程度）\n"
                "3. 建议行动（具体可执行的步骤）"
            ),
        },
    }]
