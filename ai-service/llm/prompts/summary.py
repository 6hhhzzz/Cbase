"""摘要生成和二次压缩 Prompt 模板。

对应 proposal 5.4（摘要生成）和 5.5（二次压缩策略 A）。
"""

from .base import PromptTemplate

# 首次摘要生成（proposal 5.4）
SUMMARY_PROMPT = PromptTemplate("""将以下对话历史压缩为简洁摘要。保留关键实体、决策和结论，丢弃冗余描述和客套话。
限制在 {{ max_tokens }} Tokens 以内。

对话历史:
---
{% for msg in messages %}
[{{ msg.role }}]: {{ msg.content }}
{% endfor %}
---
""")

# 二次压缩（proposal 5.5 方案 A — 摘要的摘要）
COMPRESS_PROMPT = PromptTemplate("""将以下对话摘要压缩至 {{ target_tokens }} Tokens 以内。
保留关键实体、决策和结论，丢弃冗余描述。

当前摘要:
{{ summary }}
""")
