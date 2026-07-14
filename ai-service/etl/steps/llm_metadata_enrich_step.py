"""LlmMetadataEnrichStep — LLM 增强的元数据提取。

在 ChunkStepV5 之后、EmbedStep 之前执行。
对 title chunk 调用 LLM 提取 level/heading/entities，
非 title chunk 和 LLM 故障时降级到规则逻辑。

设计原则：
    1. 只对 title chunk 调用 LLM（成本可控）
    2. 整文档 title chunks 批量发送（一次 API 调用）
    3. 异步并发控制（Semaphore，默认最多 3 并发）
    4. 结构化输出（JSON Schema + Pydantic 校验）
    5. 静默降级：LLM 失败 → 规则兜底，不影响管道
"""

import asyncio
import json

from pydantic import BaseModel, Field

from common import get_logger
from llm.base import BaseLLM
from llm.prompts.metadata import METADATA_EXTRACT_PROMPT
from models.document import DocumentChunk

from .base import PipelineStep

logger = get_logger(__name__)

# 全局并发限制：所有文档实例共享，防止突发 LLM 请求压垮 API
_metadata_semaphore = asyncio.Semaphore(3)

# 为 title chunk 提供上下文的前导文本最大字符数
_CONTEXT_ABOVE_MAX_CHARS = 300


class TitleMetadataItem(BaseModel):
    """单个标题 chunk 的 LLM 提取结果。"""
    index: int = Field(..., description="标题块在输入列表中的序号")
    level: int = Field(..., ge=1, le=6, description="标题层级 1-6")
    heading: str = Field(..., min_length=1, max_length=100, description="清洗后的标题文本")
    chunk_type: str = Field(default="title", pattern=r"^(title|text|table)$")
    entities: list[str] = Field(default_factory=list, max_length=5)


class TitleMetadataBatch(BaseModel):
    """一批标题块的 LLM 提取结果。"""
    chunks: list[TitleMetadataItem]


class LlmMetadataEnrichStep(PipelineStep):
    """LLM 增强的元数据提取步骤。

    用法:
        step = LlmMetadataEnrichStep(llm)
        ctx = await step.execute(ctx)

    与现有 MetadataEnrichStep 接口兼容，可直接替换。
    当 llm=None 或 LLM 调用失败时自动降级为规则逻辑。
    """

    def __init__(self, llm: BaseLLM | None = None):
        self._llm = llm

    async def execute(self, ctx: dict) -> dict:
        chunks: list[DocumentChunk] = ctx.get("chunks", [])
        if not chunks:
            logger.info("LlmMetadataEnrichStep: 无 chunk，跳过")
            return ctx

        # 收集 title chunks 的索引
        title_indices = [
            i for i, c in enumerate(chunks)
            if c.metadata.get("chunk_type") == "title"
        ]

        if not title_indices:
            logger.info("LlmMetadataEnrichStep: 无 title chunk，执行规则降级")
            self._apply_rules(chunks)
            return ctx

        if self._llm is not None:
            try:
                await self._llm_extract(ctx, chunks, title_indices)
            except Exception:
                logger.warning(
                    "LLM 元数据提取异常，使用规则降级: doc_id=%s",
                    ctx.get("msg", None) and ctx["msg"].doc_id,
                )
                self._apply_rules(chunks, title_indices)
        else:
            logger.info(
                "LlmMetadataEnrichStep: LLM 未配置，使用规则降级: doc_id=%s",
                ctx.get("msg", None) and ctx["msg"].doc_id,
            )
            self._apply_rules(chunks, title_indices)

        return ctx

    # ---- LLM 提取 ----

    async def _llm_extract(
        self,
        ctx: dict,
        chunks: list[DocumentChunk],
        title_indices: list[int],
    ) -> None:
        """使用 LLM 批量提取 title chunk 元数据。"""
        msg = ctx["msg"]
        doc_id = msg.doc_id
        file_name = (
            msg.file_path.rsplit("/", 1)[-1]
            if "/" in msg.file_path
            else msg.file_path
        )

        # 构建每个 title chunk 的输入（含前导上下文）
        title_inputs = []
        for idx in title_indices:
            chunk = chunks[idx]
            # 收集前导非 title chunk 文本作为上下文
            context_parts = []
            for j in range(idx - 1, max(idx - 3, -1), -1):
                if j < 0:
                    break
                if chunks[j].metadata.get("chunk_type") != "title":
                    text = chunks[j].chunk_text[:_CONTEXT_ABOVE_MAX_CHARS]
                    context_parts.insert(0, text)
            context_above = "\n".join(context_parts)[:_CONTEXT_ABOVE_MAX_CHARS]

            title_inputs.append({
                "text": chunk.chunk_text,
                "context_above": context_above,
            })

        prompt = METADATA_EXTRACT_PROMPT.render(
            file_name=file_name,
            file_type=msg.file_type,
            title_chunks=title_inputs,
        )

        async with _metadata_semaphore:
            response = await self._llm.generate_content(
                prompt,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            raw = response.content.strip()
            validated = self._parse_and_validate(raw, title_indices)

            if validated is not None:
                self._apply_llm_results(chunks, validated, title_indices)
                logger.info(
                    "LLM 元数据提取成功: doc_id=%s, title_chunks=%d, "
                    "model=%s, usage=%s",
                    doc_id, len(title_indices),
                    response.model,
                    response.usage,
                )
                return

        # LLM 输出无法解析 → 降级
        logger.warning(
            "LLM 输出解析失败，使用规则降级: doc_id=%s", doc_id
        )
        self._apply_rules(chunks, title_indices)

    def _parse_and_validate(
        self, raw: str, expected_indices: list[int]
    ) -> TitleMetadataBatch | None:
        """解析并校验 LLM 输出的 JSON。"""
        # 如果 LLM 包裹在 ``` 代码块中，提取 JSON
        if raw.startswith("```"):
            start = raw.find("\n") + 1
            end = raw.rfind("```")
            if end > start:
                raw = raw[start:end]
            else:
                raw = raw[start:]

        try:
            data = json.loads(raw)
            batch = TitleMetadataBatch(**data)

            # 校验：返回的 index 必须在输入范围内
            valid_indices = set(expected_indices)
            for item in batch.chunks:
                if item.index not in valid_indices:
                    logger.warning(
                        "LLM 返回了意外的 index=%d，丢弃整个 batch", item.index
                    )
                    return None

            return batch
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("LLM 输出 JSON 解析失败: %s", e)
            return None

    def _apply_llm_results(
        self,
        chunks: list[DocumentChunk],
        batch: TitleMetadataBatch,
        title_indices: list[int],
    ) -> None:
        """将 LLM 提取结果写入 chunk metadata。"""
        result_map = {item.index: item for item in batch.chunks}

        applied = 0
        for idx in title_indices:
            chunk = chunks[idx]
            item = result_map.get(idx)

            if item is None:
                # LLM 遗漏了这个 chunk，规则兜底
                self._apply_rules_to_one(chunk)
                continue

            meta = chunk.metadata
            meta["level"] = item.level
            meta["heading"] = item.heading
            meta["chunk_type"] = item.chunk_type
            if item.entities:
                meta["entities"] = item.entities
            applied += 1

        logger.info(
            "LLM 结果已应用: %d/%d title chunks",
            applied, len(title_indices),
        )

    # ---- 规则降级 ----

    def _apply_rules(
        self,
        chunks: list[DocumentChunk],
        title_indices: list[int] | None = None,
    ) -> None:
        """对所有 chunk（或指定索引）应用规则降级。"""
        indices = title_indices if title_indices is not None else range(len(chunks))
        for idx in indices:
            self._apply_rules_to_one(chunks[idx])

    @staticmethod
    def _apply_rules_to_one(chunk: DocumentChunk) -> None:
        """对单个 chunk 应用规则降级（与原 MetadataEnrichStep 逻辑兼容）。"""
        meta = chunk.metadata

        # chunk_type 回退
        if "chunk_type" not in meta and "type" in meta:
            meta["chunk_type"] = meta["type"]

        # heading 回退
        if meta.get("chunk_type") == "title" and "heading" not in meta:
            meta["heading"] = chunk.chunk_text[:80].strip()

        # level 回退
        if "level" not in meta and meta.get("chunk_type") == "title":
            # 尝试从 Markdown # 前缀推断
            text = chunk.chunk_text.strip()
            if text.startswith("######"):
                meta["level"] = 6
            elif text.startswith("#####"):
                meta["level"] = 5
            elif text.startswith("####"):
                meta["level"] = 4
            elif text.startswith("###"):
                meta["level"] = 3
            elif text.startswith("##"):
                meta["level"] = 2
            elif text.startswith("#"):
                meta["level"] = 1
            else:
                # ChunkStepV5 修复后 level 应由 TitleChunker 传入
                # 若仍然没有，默认 1
                meta["level"] = 1

        # page_range 回退
        if "page_range" not in meta and "page_num" in meta:
            pn = meta["page_num"]
            meta["page_range"] = [pn, pn]
