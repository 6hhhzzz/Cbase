"""ContextEnricher — 表格/图片 Chunk 上下文注入。

借鉴 RAGFlow 的 _attach_context_to_media_chunks 思路：
    - 表格 chunk 自动附带前后 N 个文本 chunk 的内容
    - 图片 chunk 附带 VLM 描述 + caption
    - 控制注入量避免上下文膨胀

用法:
    enricher = ContextEnricher(table_context_size=2, image_context_size=1)
    enriched = enricher.enrich(chunks, relations)
"""

from common import get_logger
from common.utils import estimate_tokens, truncate_text

from .models import Chunk, ChunkRelation

logger = get_logger(__name__)

# 最大注入 token 数
_MAX_CONTEXT_TOKENS = 300


class ContextEnricher:
    """为表格和图片 Chunk 注入周围文本上下文。

    这样检索到表格 chunk 时，LLM 也能看到表格前后的说明文字，
    提高对表格数据的理解准确度。
    """

    def __init__(
        self,
        table_context_size: int = 2,
        image_context_size: int = 1,
    ):
        """
        Args:
            table_context_size: 表格前后各取 N 个文本 chunk
            image_context_size: 图片前后各取 N 个文本 chunk
        """
        self._table_ctx = table_context_size
        self._image_ctx = image_context_size

    def enrich(
        self, chunks: list[Chunk], relations: list[ChunkRelation]
    ) -> list[Chunk]:
        """为表格和图片 chunk 注入上下文。

        注意：直接修改原 Chunk 对象，不产生新列表。

        Args:
            chunks: Chunk 列表
            relations: 对应的关系列表

        Returns:
            修改后的 chunks（原地修改）
        """
        if len(chunks) != len(relations):
            logger.warning(f"chunks({len(chunks)}) 和 relations({len(relations)}) 数量不匹配，跳过 enrichment")
            return chunks

        for i, (chunk, _rel) in enumerate(zip(chunks, relations)):
            ctx_size = 0
            if chunk.chunk_type == "table":
                ctx_size = self._table_ctx
            elif chunk.chunk_type == "image":
                ctx_size = self._image_ctx

            if ctx_size == 0:
                continue

            above = self._collect_above(chunks, i, ctx_size, chunk)
            below = self._collect_below(chunks, i, ctx_size, chunk)

            if above or below:
                parts = []
                if above:
                    parts.append(f"[上文上下文]\n{above}")
                parts.append(chunk.content)
                if below:
                    parts.append(f"[下文上下文]\n{below}")
                chunk.content = "\n\n".join(parts)
                chunk.tokens = estimate_tokens(chunk.content)

        return chunks

    def _collect_above(
        self, chunks: list[Chunk], idx: int, count: int, _target: Chunk
    ) -> str:
        """收集目标 chunk 之前的文本上下文。"""
        texts = []
        tokens_so_far = 0
        for i in range(idx - 1, max(idx - count - 1, -1), -1):
            if chunks[i].chunk_type != "text":
                continue
            snippet = truncate_text(chunks[i].content, 200)
            t = estimate_tokens(snippet)
            if tokens_so_far + t > _MAX_CONTEXT_TOKENS:
                break
            texts.insert(0, snippet)
            tokens_so_far += t
        return "\n".join(texts)

    def _collect_below(
        self, chunks: list[Chunk], idx: int, count: int, _target: Chunk
    ) -> str:
        """收集目标 chunk 之后的文本上下文。"""
        texts = []
        tokens_so_far = 0
        for i in range(idx + 1, min(idx + count + 1, len(chunks))):
            if chunks[i].chunk_type != "text":
                continue
            snippet = truncate_text(chunks[i].content, 200)
            t = estimate_tokens(snippet)
            if tokens_so_far + t > _MAX_CONTEXT_TOKENS:
                break
            texts.append(snippet)
            tokens_so_far += t
        return "\n".join(texts)
