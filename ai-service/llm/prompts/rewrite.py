"""Query 改写 Prompt — 多轮对话指代消解 + 关键词提取。

架构师建议：
    - 改写时顺便提取"核心关键词（Keywords）"，直接传给 BM25
    - 引入缓存与短路机制减少不必要的 LLM 调用
"""

from .base import PromptTemplate

REWRITE_PROMPT = PromptTemplate("""你是一个查询改写助手。根据对话历史，将用户的查询改写为完整、明确的检索查询。

要求：
1. 消解指代：将"它"、"这个"、"上一个"等替换为具体实体
2. 补全上下文：将对话中的前置信息融入查询
3. 保持原意：不要添加用户未提及的信息

同时提取 2-5 个核心关键词，用于精确匹配检索。

返回 JSON 格式：
{
    "rewritten_query": "改写后的完整查询",
    "keywords": ["关键词1", "关键词2", "关键词3"]
}

对话历史：
{% for msg in history %}
[{{ msg.role }}]: {{ msg.content }}
{% endfor %}

当前用户查询：{{ query }}

请输出 JSON：""")
