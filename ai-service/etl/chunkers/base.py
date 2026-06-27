"""分块器抽象基类。"""

from abc import ABC, abstractmethod
from uuid import UUID

from models.document import DocumentChunk, DocumentMetadata, ParseResult


class BaseChunker(ABC):
    """文本分块器抽象。所有分块实现必须继承此类。"""

    @abstractmethod
    async def chunk(self, parse_result: ParseResult, metadata: DocumentMetadata,
                    doc_id: UUID | None = None) -> list[DocumentChunk]:
        """将解析结果拆分为文档块。

        Args:
            parse_result: 解析器返回的结果
            metadata: 文档权限/业务元数据
            doc_id: 文档 ID

        Returns:
            文档块列表
        """
        ...
