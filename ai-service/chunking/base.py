"""分块器抽象基类。"""

from abc import ABC, abstractmethod

from parsing.models import ParsedDocument
from .models import Chunk, ChunkRelation


class BaseChunker(ABC):
    """文本分块器抽象。所有分块策略必须继承此类。

    输入 ParsedDocument（结构化 blocks），输出 Chunk[] + ChunkRelation[]。
    与旧版 BaseChunker（输入 ParseResult）不同，新版本可以：
        - 按 block 类型（title/text/table/image）差异化处理
        - 保留标题层级信息用于 TitleChunker
        - 保留位置元数据用于引用标注
    """

    @abstractmethod
    async def chunk(self, doc: ParsedDocument) -> tuple[list[Chunk], list[ChunkRelation]]:
        """将 ParsedDocument 拆分为 Chunk 列表。

        Args:
            doc: 解析后的结构化文档

        Returns:
            (chunks, relations) — Chunk 列表和关系列表
        """
        ...
