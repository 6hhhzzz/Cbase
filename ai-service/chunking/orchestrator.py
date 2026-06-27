"""ChunkOrchestrator — 分块编排器。

根据文档类型选择分块策略：
    - 结构化文档（有标题层级）→ TitleChunker
    - 非结构化文档 → TokenChunker
    - 所有文档 → ContextEnricher（表格/图片上下文注入）

用法:
    orchestrator = ChunkOrchestrator()
    chunks, relations = await orchestrator.chunk(parsed_doc, strategy="auto")
"""

from common import get_logger
from parsing.models import ParsedDocument

from .base import BaseChunker
from .models import Chunk, ChunkRelation
from .token_chunker import TokenChunker
from .title_chunker import TitleChunker
from .merge import merge_chunks
from .enrich import ContextEnricher

logger = get_logger(__name__)


class ChunkOrchestrator:
    """分块编排器。选择策略、执行分块、注入上下文。"""

    def __init__(
        self,
        token_chunker: TokenChunker | None = None,
        title_chunker: TitleChunker | None = None,
        enricher: ContextEnricher | None = None,
    ):
        self._token_chunker = token_chunker or TokenChunker()
        self._title_chunker = title_chunker or TitleChunker()
        self._enricher = enricher or ContextEnricher()

    async def chunk(
        self,
        doc: ParsedDocument,
        strategy: str = "auto",
    ) -> tuple[list[Chunk], list[ChunkRelation]]:
        """将 ParsedDocument 拆分为 Chunks。

        Args:
            doc: 解析后的结构化文档
            strategy: 分块策略
                - "auto": 根据文档标题数量自动选择
                - "token": 强制 TokenChunker
                - "title": 强制 TitleChunker

        Returns:
            (chunks, relations)
        """
        # 选择策略
        chunker = self._select_chunker(doc, strategy)

        # 执行分块
        chunks, relations = await chunker.chunk(doc)

        # 注入表格/图片上下文
        chunks = self._enricher.enrich(chunks, relations)

        # 合并过短 chunk（naive_merge）
        chunks, relations = merge_chunks(chunks, relations)

        # 为每个 chunk 标记 doc_id（用于数据库索引）
        doc_id = doc.metadata.extra.get("doc_id", doc.metadata.file_name)
        for chunk in chunks:
            chunk.metadata["doc_id"] = str(doc_id)
            chunk.metadata["file_type"] = doc.metadata.file_type
            if not chunk.content_with_weight:
                chunk.content_with_weight = chunk.content

        logger.info(
            f"ChunkOrchestrator: strategy={strategy}, "
            f"blocks={len(doc.blocks)}, chunks={len(chunks)}"
        )
        return chunks, relations

    def _select_chunker(self, doc: ParsedDocument, strategy: str) -> BaseChunker:
        """根据策略和文档特征选择分块器。"""
        if strategy == "token":
            return self._token_chunker
        if strategy == "title":
            return self._title_chunker

        # auto: 根据标题数量决定
        title_count = sum(
            1 for b in doc.text_blocks
            if b.layout_type == "title" and b.level is not None
        )
        if title_count >= 3:
            logger.info(f"检测到 {title_count} 个标题，使用 TitleChunker")
            return self._title_chunker
        else:
            logger.info(f"标题数 {title_count} < 3，使用 TokenChunker")
            return self._token_chunker
