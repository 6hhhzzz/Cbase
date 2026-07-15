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
                    "Cbase 企业知识库检索最佳实践 — 教授外部 Agent 如何从用户问题构造高质量查询、"
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
                    "用于 Cbase 内部的 LLM 生成阶段，或供外部 Agent 直接使用。"
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
                    "适合对检索到的文档块或完整文档内容做结构化分析。"
                ),
                "arguments": [
                    {"name": "document_content", "description": "待分析的文档文本内容（可从 search_chunks 的 content 字段获取）", "required": True},
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
                "你正在使用一个企业知识库检索系统（Cbase）。用户的问题是：\n\n"
                f'"{user_question}"{ctx_block}\n\n'
                "在调用 KES 的 search_chunks 工具之前，请先读取 Resource 了解知识库概况，"
                "再构造精确的查询。\n\n"
                "## 推荐工作流\n"
                "1. 先读 doc://catalog → 了解有哪些 KB、各有什么内容\n"
                "2. 对目标 KB 读 doc://kb/{kb_id}/entities → 获取精确的实体术语（产品名、版本号、技术名词）\n"
                "3. 可选：读 doc://kb/{kb_id}/structure → 了解文档章节结构，判断信息可能在哪个文档\n"
                "4. 可选：读 doc://kb/{kb_id}/time_range → 判断 KB 是否活跃、有无过期风险\n"
                "5. 带着精确术语调 search_chunks → 高质量检索\n\n"
                "## 1. 提取关键实体\n"
                "- 从用户问题中识别：产品名、系统名、版本号、模块名、错误码、文件名\n"
                "- 从已知背景中提取：运行环境、已尝试步骤、相关配置\n"
                "- 对比 doc://kb/{kb_id}/entities 中的实体清单——优先使用知识库中实际存在的术语\n\n"
                "## 2. 构造高质量查询\n"
                "- 将松散的口语表达转化为精确的技术术语\n"
                "- 融入 doc://kb/{kb_id}/entities 中获取到的精确术语\n"
                "- 将关键词按照重要性排序\n\n"
                "## 3. 选择 top_k（最大返回 chunk 数）\n"
                "- top_k 是最大返回数而非保证数——低置信度 chunk 会被自动过滤，实际返回可能更少\n"
                "- 简单事实查找（查配置项、错误码含义）：top_k=5~8\n"
                "- 一般技术问题（默认场景）：top_k=10~15\n"
                "- 探索性搜索（需要更多候选综合分析）：top_k=15~20\n"
                "- 全面调研（覆盖多个方面）：top_k=20~30\n"
                "- 策略：先用较小 top_k 试探，如果返回数量不足或过滤率高，再加大 top_k 或重构 query\n"
                "- 如果已限定 focus_aspects 或 doc_type，可适当增大 top_k 以在限定范围内获取更多结果\n\n"
                "## 4. 选择策略\n"
                "- 如果已知目标知识库 → 传入 kb_ids 参数\n"
                "- 如果不确定 → 先读 doc://catalog 了解可用 KB\n"
                "- 如果问题涉及特定方面 → 传入 focus_aspects 参数\n"
                "- 如果已有用户背景 → 传入 context_hint 参数\n\n"
                "## 5. 评估信息时效性\n"
                "- 每条检索结果的 source 字段包含 doc_effective_date（文档生效日期）、"
                "doc_expiry_date（文档失效日期）、doc_version（版本号）和 is_expired（是否已过期）\n"
                "- is_expired=true 的 chunk 表示文档已过有效期，不应作为当前操作的权威依据\n"
                "- 默认排除过期文档；如需查看已被新版本替代的历史规定，可传 time_range.expired='only'\n"
                "- 用户问'之前的规定/旧版本'等历史问题时，应传入 time_range.expired='include' 或 'only'\n"
                "- 对比分析时优先采用 doc_version 更高、doc_effective_date 更新的 chunk\n"
                "- 如果所有检索结果的 is_expired 都=true，应提示用户\n\n"
                "请根据以上分析，确定应使用的参数，然后执行 search_chunks。"
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
