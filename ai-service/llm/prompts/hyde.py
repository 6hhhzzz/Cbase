"""HyDE (Hypothetical Document Embeddings) Prompt。

原理: 让 LLM 生成一段"假答案"（技术文档风格），用假答案的 embedding
替代原始 query 做 Dense 向量检索。假答案的词汇分布更接近真实文档，
从而桥接用户口语和文档术语之间的语义鸿沟。

参考: Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels", 2022
"""

from .base import PromptTemplate

HYDE_PROMPT = PromptTemplate("""你是一个技术文档撰写助手。用户想问一个问题。请以技术文档的口吻写一段可能包含答案的段落（100-200字）。

要求：
- 模仿企业内部技术文档/运维手册/技术规范的语言风格
- 使用专业术语和标准表达方式
- **仅使用用户问题中已出现的概念和术语**，不编造新信息
- **严禁编造以下内容**：
  - 版本号（v3.2、4.0 等）
  - 表单编号/文档编号（Form-ICD-01、Cbase-2023 等）
  - 条款编号（第4.1条、第7.3条 等）
  - 系统名称/产品名（HRIS、ISMS 等——除非用户问题中已明确提及）
- 用中文写，技术术语保留英文
- 输出纯段落，不要 markdown 标记

用户问题：{{ query }}

技术文档段落：""")
