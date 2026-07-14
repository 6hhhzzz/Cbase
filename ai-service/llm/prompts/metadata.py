"""Metadata 提取 Prompt — 从文档标题 chunk 提取结构化元数据。

仅在 ETL 管道的 LlmMetadataEnrichStep 中使用。
对 title chunk 批量调用，非 title chunk 使用规则降级。

设计原则：
    - 一次 API 调用处理一个文档的所有标题块
    - 输出结构化 JSON，由 Pydantic 校验
    - temperature=0.1 保证输出稳定性
"""

from .base import PromptTemplate

METADATA_EXTRACT_PROMPT = PromptTemplate("""你是一个文档结构化分析专家。分析以下文档的标题块，为每个标题提取元数据。

你需要完成：
1. **标题层级判定**：根据标题文本的语义和表述风格，判断它在文档中的层级 (1-6)
2. **标题清洗**：去除编号前缀（如"第X章"、"一、"、"1.1"等），保留核心标题文本
3. **类型确认**：判断这个 chunk 是否真的是标题，还是被误分类的正文/表格
4. **实体提取**：从标题文本中提取关键实体（产品名、版本号、技术术语、专有名词）

上下文：
- 文档文件名：{{ file_name }}
- 文档类型：{{ file_type }}

标题块列表：
{% for chunk in title_chunks %}
[Chunk {{ loop.index0 }}]
文本: {{ chunk.text }}
{% if chunk.context_above %}
上文: {{ chunk.context_above }}
{% endif %}
---
{% endfor %}

严格按以下 JSON 格式输出，只输出 JSON，不要任何解释或 Markdown 标记：

{
  "chunks": [
    {
      "index": 0,
      "level": 2,
      "heading": "清洗后的标题文本",
      "chunk_type": "title",
      "entities": ["产品名", "版本号"]
    }
  ]
}

字段约束：
- index: 标题块序号（整数，对应输入的 [Chunk N]）
- level: 1-6 整数。1=文档主标题，2=大章节，3=小节，4-6=更深子节
- heading: 清洗后的标题文本，去除编号前缀和多余空格，长度 ≤ 100 字符
- chunk_type: "title"（确认是标题）| "text"（误分类，实际是正文）| "table"（误分类，实际是表格）
- entities: 从标题中提取的 ≤ 5 个关键实体，字符串列表。无实体时返回空列表 []

注意：
- 必须为每个输入的标题块返回一条记录，不能遗漏或增加
- index 必须与输入 [Chunk N] 的序号一致
- 仅输出 JSON，不要包裹在 ```json 代码块中
""")
