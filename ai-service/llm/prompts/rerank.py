"""LLM Rerank Prompt — 无 GPU 时的降级重排序方案。

当 BGE-Reranker 等交叉编码器不可用时，用 LLM 对候选文档进行精排。
只对 Top-M 候选（通常 ≤ 20）进行重排，成本可控。
"""

from .base import PromptTemplate

RERANK_PROMPT = PromptTemplate("""你是一个文档相关性评分助手。根据用户查询，为每个候选文档片段打分（0-100）。

评分标准：
- 90-100: 直接回答查询，包含关键信息
- 70-89: 部分相关，涉及查询的主题
- 50-69: 弱相关，仅有部分交集
- 0-49: 不相关

只返回 JSON 数组，不要解释。

用户查询：{{ query }}

候选文档片段：
{% for doc in candidates %}
---
ID: {{ doc.id }}
内容: {{ doc.content[:500] }}
---
{% endfor %}

请按以下格式返回评分（JSON 数组）：
[{"id": "doc_id", "score": 85}, ...]""")
