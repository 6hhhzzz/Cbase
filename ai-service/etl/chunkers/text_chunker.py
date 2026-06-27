"""文本分块器 — 将解析后的文本拆分为适合索引的 Chunk。

使用 langchain-text-splitters 的 RecursiveCharacterTextSplitter，
参数:
    chunk_size=512（每个块最多 512 字符）
    chunk_overlap=50（相邻块重叠 50 字符，避免语义断裂）
"""

from uuid import UUID

from common import get_logger
from models.document import DocumentChunk, DocumentMetadata, ParseResult
from .base import BaseChunker

logger = get_logger(__name__)


class TextChunker(BaseChunker):
    """文本分块器。对普通文本和 Markdown Table 均适用。"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def chunk(
        self,
        parse_result: ParseResult,
        metadata: DocumentMetadata,
        doc_id: UUID | None = None,
    ) -> list[DocumentChunk]:
        """将 ParseResult 拆分为 DocumentChunk 列表。

        Args:
            parse_result: 解析后的文件内容
            metadata: 文档权限元数据
            doc_id: 文档 UUID（必须传入，不再默认使用 owner_user_id）

        Returns:
            DocumentChunk 列表，每个 Chunk 携带权限元数据
        """
        text = parse_result.raw_text
        if not text.strip():
            return []

        # doc_id 必传，兜底为 nil UUID（外层应始终传入正确的 doc_id）
        if doc_id is None:
            doc_id = UUID("00000000-0000-0000-0000-000000000000")
            logger.warning("chunk() 未传入 doc_id，使用 nil UUID 兜底")

        # 尝试使用 langchain 的分块器，失败则使用简单按段落分块
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
                separators=["\n\n", "\n", "。", ".", "，", " ", ""],
            )
            splits = splitter.split_text(text)
        except ImportError:
            logger.warning("langchain_text_splitters 未安装，使用简单分块")
            splits = self._simple_split(text)

        chunks = []
        for i, split_text in enumerate(splits):
            if not split_text.strip():
                continue
            chunks.append(DocumentChunk(
                doc_id=doc_id,
                chunk_index=i,
                chunk_text=split_text.strip(),
                metadata={
                    "kb_id": metadata.kb_id,
                },
            ))

        logger.info(f"分块完成: doc_id={doc_id}, {len(splits)} 个 segments → {len(chunks)} 个 chunks")
        return chunks

    def _simple_split(self, text: str) -> list[str]:
        """简单分块策略：按段落 + 字符数限制。"""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) <= self._chunk_size:
                current += para + "\n\n"
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = para + "\n\n"
        if current.strip():
            chunks.append(current.strip())
        return chunks
