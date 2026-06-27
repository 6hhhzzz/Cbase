"""TokenChunker — token 感知分块，默认策略。

借鉴 RAGFlow 的 naive_merge 思路：
    1. 按 layout_type 过滤（丢弃 header/footer/reference）
    2. 分隔符优先级切分：\\n\\n → \\n → 。→ . → 空格
    3. token 估算替代字符计数
    4. 短 chunk 合并直到接近 chunk_token_size
    5. overlap_percent 重叠
"""

from common import get_logger
from common.utils import estimate_tokens, generate_chunk_id
from parsing.models import ParsedDocument, TextBlock, TableBlock, ImageBlock

from .base import BaseChunker
from .models import Chunk, ChunkRelation

logger = get_logger(__name__)

# 分隔符优先级：从粗到细
SEPARATORS = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", "，", ",", " ", ""]

# 需要保留的 layout_type（丢弃 header/footer/reference 噪声）
_KEEP_LAYOUTS = {"title", "text", "equation"}


class TokenChunker(BaseChunker):
    """Token 感知分块器。

    按 token 数（而非字符数）估算 chunk 大小，适合中英文混合文本。
    对表格和图片，保留为独立 chunk 并保持结构。
    """

    def __init__(
        self,
        chunk_token_size: int = 512,
        overlap_percent: float = 0.1,
        min_chunk_tokens: int = 50,
    ):
        """
        Args:
            chunk_token_size: 目标 chunk token 数
            overlap_percent: 重叠比例 (0.0 ~ 1.0)
            min_chunk_tokens: 最小 chunk token 数，低于此值的 chunk 合并
        """
        self._chunk_tokens = chunk_token_size
        self._overlap = overlap_percent
        self._min_tokens = min_chunk_tokens

    async def chunk(self, doc: ParsedDocument) -> tuple[list[Chunk], list[ChunkRelation]]:
        chunks: list[Chunk] = []
        chunk_index = 0

        for block in doc.blocks:
            if isinstance(block, TextBlock):
                if block.layout_type not in _KEEP_LAYOUTS:
                    continue

                text = block.text
                tokens = estimate_tokens(text)

                if tokens <= self._chunk_tokens:
                    # 足够短，直接作为一个 chunk
                    chunk = self._make_text_chunk(
                        text=text,
                        chunk_index=chunk_index,
                        block=block,
                        doc=doc,
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                else:
                    # 需要切分
                    splits = self._split_by_separators(text)
                    merged = self._merge_short(splits)
                    for split_text in merged:
                        chunk = self._make_text_chunk(
                            text=split_text,
                            chunk_index=chunk_index,
                            block=block,
                            doc=doc,
                        )
                        chunks.append(chunk)
                        chunk_index += 1

            elif isinstance(block, TableBlock):
                chunks.append(self._make_table_chunk(block, chunk_index, doc))
                chunk_index += 1

            elif isinstance(block, ImageBlock):
                chunks.append(self._make_image_chunk(block, chunk_index, doc))
                chunk_index += 1

        # 为重叠生成 content_with_weight
        for i, chunk in enumerate(chunks):
            chunk.content_with_weight = self._build_weighted_content(
                chunk.content,
                prev_text=chunks[i - 1].content if i > 0 and chunks[i - 1].chunk_type == "text" else None,
                next_text=chunks[i + 1].content if i < len(chunks) - 1 and chunks[i + 1].chunk_type == "text" else None,
            )
            # 重新计算 token 数
            chunk.tokens = estimate_tokens(chunk.content_with_weight)

        # 生成关系
        relations = self._build_relations(chunks)

        logger.info(
            f"TokenChunker: {len(doc.blocks)} blocks → {len(chunks)} chunks"
        )
        return chunks, relations

    def _make_text_chunk(
        self, text: str, chunk_index: int, block: TextBlock, doc: ParsedDocument
    ) -> Chunk:
        """创建文本 Chunk。"""
        chunk_id = generate_chunk_id(doc.metadata.file_name, chunk_index)
        return Chunk(
            id=chunk_id,
            content=text,
            chunk_type="title" if block.layout_type == "title" else "text",
            title=text[:100] if block.layout_type == "title" else None,
            page_range=(block.page_num, block.page_num) if block.page_num > 0 else None,
            tokens=estimate_tokens(text),
            metadata={
                "file_name": doc.metadata.file_name,
                "layout_type": block.layout_type,
                "level": block.level,
            },
        )

    def _make_table_chunk(
        self, block: TableBlock, chunk_index: int, doc: ParsedDocument
    ) -> Chunk:
        """创建表格 Chunk。"""
        chunk_id = generate_chunk_id(doc.metadata.file_name, chunk_index)
        # 表格 content = HTML（结构） + 描述
        content = f"{block.description}\n{block.html}"
        return Chunk(
            id=chunk_id,
            content=content,
            chunk_type="table",
            title=block.caption,
            page_range=(block.page_num, block.page_num) if block.page_num > 0 else None,
            tokens=estimate_tokens(content),
            metadata={
                "file_name": doc.metadata.file_name,
                "caption": block.caption,
            },
        )

    def _make_image_chunk(
        self, block: ImageBlock, chunk_index: int, doc: ParsedDocument
    ) -> Chunk:
        """创建图片 Chunk。"""
        chunk_id = generate_chunk_id(doc.metadata.file_name, chunk_index)
        content_parts = []
        if block.description:
            content_parts.append(block.description)
        if block.caption:
            content_parts.append(f"[图片说明: {block.caption}]")
        content = "\n".join(content_parts) if content_parts else "[图片]"
        return Chunk(
            id=chunk_id,
            content=content,
            chunk_type="image",
            title=block.caption,
            page_range=(block.page_num, block.page_num) if block.page_num > 0 else None,
            tokens=estimate_tokens(content),
            metadata={
                "file_name": doc.metadata.file_name,
                "has_description": block.description is not None,
            },
        )

    def _split_by_separators(self, text: str) -> list[str]:
        """按分隔符优先级切分文本。"""
        # 使用 langchain 的分块器（如果可用），否则递归分隔符切分
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self._chunk_tokens * 2,  # 字符估算，token 会再合并
                chunk_overlap=int(self._chunk_tokens * self._overlap),
                separators=list(SEPARATORS),
            )
            return splitter.split_text(text)
        except ImportError:
            return self._simple_token_split(text)

    def _simple_token_split(self, text: str) -> list[str]:
        """简单 token 感知切分（降级方案）。"""
        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if estimate_tokens(current + "\n\n" + para) <= self._chunk_tokens:
                current += "\n\n" + para if current else para
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = para
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _merge_short(self, splits: list[str]) -> list[str]:
        """合并过短的 chunk 直到接近 chunk_token_size。"""
        if not splits:
            return []

        merged = []
        current = splits[0]

        for split in splits[1:]:
            combined_tokens = estimate_tokens(current + "\n\n" + split)
            if combined_tokens <= self._chunk_tokens:
                current += "\n\n" + split
            else:
                if estimate_tokens(current) >= self._min_tokens:
                    merged.append(current)
                else:
                    # 强制合并，即使超出
                    merged.append(current + "\n\n" + split)
                current = split if estimate_tokens(current) >= self._min_tokens else ""

        if current.strip() and estimate_tokens(current) >= self._min_tokens:
            merged.append(current)
        elif current.strip() and merged:
            merged[-1] += "\n\n" + current

        return merged

    def _build_weighted_content(
        self, content: str, prev_text: str | None, next_text: str | None
    ) -> str:
        """构建加权 content（关键词重复增强 BM25 命中）。

        借鉴 RAGFlow content_with_weight 思路：
            核心名词/专有名词重复一次以增加 BM25 权重。
        对中文：简单地加入重叠文本片段。
        """
        parts = [content]
        # 前重叠
        if prev_text and self._overlap > 0:
            overlap_chars = min(int(len(prev_text) * self._overlap), 200)
            if overlap_chars > 0:
                parts.append(prev_text[-overlap_chars:])
        # 后重叠
        if next_text and self._overlap > 0:
            overlap_chars = min(int(len(next_text) * self._overlap), 200)
            if overlap_chars > 0:
                parts.append(next_text[:overlap_chars])
        return "\n".join(parts)

    def _build_relations(self, chunks: list[Chunk]) -> list[ChunkRelation]:
        """构建相邻 chunk 间的兄弟关系。"""
        relations = []
        for i in range(len(chunks)):
            rel = ChunkRelation(
                prev_id=chunks[i - 1].id if i > 0 else None,
                next_id=chunks[i + 1].id if i < len(chunks) - 1 else None,
            )
            relations.append(rel)
        return relations
