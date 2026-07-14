"""DocUnderstandStep — LLM 通读文档，产出结构化元数据。

在 ChunkStepV5 之后运行，读前 5000 字 → SLM 一次调用 → 产出：
  - summary: 100-200 字文档摘要
  - doc_type: policy | manual | report | guide | specification
  - topics: 主题关键词列表
  - key_entities: 专有名词列表
  - not_covered: 文档明显不包含的内容

产出写入 ctx["doc_metadata"]，供后续 DocClassifyStep 和 IndexStep 使用。
"""

from common import get_logger
from llm.base import BaseLLM
from .base import PipelineStep

logger = get_logger(__name__)

_DOC_UNDERSTAND_PROMPT = """你是企业文档分析专家。通读以下文档内容，完成分析。

## 文档内容（前 5000 字）
{doc_text}

## 任务
1. 用 100-200 字概括文档主题、适用范围和主要内容
2. 判断文档类型（policy=制度规范, manual=员工手册, report=报告, guide=指南, specification=技术规格）
3. 提取 3-8 个主题关键词
4. 提取文档中出现的专有名词/关键实体（人名、系统名、术语、阈值数字）
5. 指出本文档**明显不包含**的内容（防止 Agent 误搜）

## 输出 JSON
{{
  "summary": "...",
  "doc_type": "policy|manual|report|guide|specification",
  "topics": ["主题1", "主题2"],
  "key_entities": ["实体1", "实体2"],
  "not_covered": ["不包含的内容1"]
}}

只返回 JSON。"""


class DocUnderstandStep(PipelineStep):
    """LLM 文档理解步骤。

    输入: ctx["chunks"]（已分块的 DocumentChunk 列表）
    产出: ctx["doc_metadata"]（dict）
    """

    def __init__(self, slm: BaseLLM):
        self._slm = slm

    async def execute(self, ctx: dict) -> dict:
        chunks = ctx.get("chunks", [])
        if not chunks:
            ctx["doc_metadata"] = {}
            return ctx

        # 取前 5000 字作为样本
        sample_parts = []
        total_chars = 0
        for c in chunks[:30]:
            text = c.chunk_text if hasattr(c, "chunk_text") else str(c)[:300]
            sample_parts.append(text[:300])
            total_chars += len(text)
            if total_chars > 5000:
                break

        doc_text = "\n\n".join(sample_parts)

        try:
            prompt = _DOC_UNDERSTAND_PROMPT.format(doc_text=doc_text)
            response = await self._slm.generate_content(prompt)
            text = response.content if hasattr(response, "content") else str(response)

            # 解析 JSON
            import json
            import re
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            data = json.loads(text)
            doc_metadata = {
                "summary": data.get("summary", ""),
                "doc_type": data.get("doc_type", "manual"),
                "topics": data.get("topics", []),
                "key_entities": data.get("key_entities", []),
                "not_covered": data.get("not_covered", []),
            }

            ctx["doc_metadata"] = doc_metadata

            # 注入到每个 chunk 的 metadata 中（供 Resource 查询）
            for chunk in chunks:
                if hasattr(chunk, "metadata"):
                    for key in ("summary", "doc_type", "topics", "key_entities", "not_covered"):
                        val = doc_metadata.get(key)
                        if val is not None:
                            chunk.metadata[f"doc_{key}"] = val

            logger.info(
                f"DocUnderstand: type={doc_metadata['doc_type']}, "
                f"topics={doc_metadata['topics'][:3]}, "
                f"summary_len={len(doc_metadata['summary'])}"
            )

        except Exception as e:
            logger.warning(f"DocUnderstand 失败，降级为空元数据: {e}")
            ctx["doc_metadata"] = {
                "summary": "",
                "doc_type": "manual",
                "topics": [],
                "key_entities": [],
                "not_covered": [],
            }

        return ctx
