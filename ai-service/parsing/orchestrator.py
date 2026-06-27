"""解析编排器 — 根据 MIME 类型路由到对应解析器。"""

from common import get_logger

from .base import BaseParser
from .models import ParsedDocument
from .registry import ParserRegistry

logger = get_logger(__name__)

# 文件扩展名 → MIME 类型映射
_EXT_TO_FILE_TYPE: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".pptx": "pptx",
    ".ppt": "pptx",
    ".html": "html",
    ".htm": "html",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
    ".text": "txt",
}

# MIME 类型 → 文件类型映射
_MIME_TO_FILE_TYPE: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.ms-powerpoint": "pptx",
    "text/html": "html",
    "text/markdown": "md",
    "text/plain": "txt",
}


class ParseOrchestrator:
    """解析编排器。

    职责：
        - 根据文件扩展名或 MIME 类型选择解析器
        - 调用解析器的 parse() 方法
        - 统一错误处理

    用法::

        orchestrator = ParseOrchestrator(registry)
        doc = await orchestrator.parse("/tmp/doc.pdf")
        # 或指定 file_type
        doc = await orchestrator.parse("/tmp/doc", file_type="pdf")
    """

    def __init__(self, registry: ParserRegistry):
        self._registry = registry

    async def parse(
        self,
        file_path: str,
        file_type: str | None = None,
    ) -> ParsedDocument:
        """解析文件为结构化 ParsedDocument。

        Args:
            file_path: 本地文件路径
            file_type: 文件类型（如 "pdf"），为 None 时从扩展名推断

        Returns:
            结构化的 ParsedDocument

        Raises:
            ValueError: 不支持的文件类型
        """
        if file_type is None:
            file_type = self._infer_type(file_path)

        parser = self._registry.get(file_type)
        if parser is None:
            raise ValueError(f"不支持的文件类型: {file_type}")

        logger.info(f"开始解析: {file_path}, type={file_type}, parser={type(parser).__name__}")
        doc = await parser.parse(file_path)
        doc.metadata.file_type = file_type
        doc.metadata.file_name = file_path
        logger.info(
            f"解析完成: {file_path}, blocks={len(doc.blocks)}, "
            f"text_blocks={len(doc.text_blocks)}, tables={len(doc.table_blocks)}, "
            f"images={len(doc.image_blocks)}"
        )
        return doc

    def _infer_type(self, file_path: str) -> str:
        """从文件扩展名推断文件类型。"""
        import os
        ext = os.path.splitext(file_path)[1].lower()
        if ft := _EXT_TO_FILE_TYPE.get(ext):
            return ft
        raise ValueError(f"无法从扩展名推断文件类型: {ext}")

    @staticmethod
    def from_mime(mime_type: str) -> str | None:
        """从 MIME 类型获取文件类型标识。"""
        return _MIME_TO_FILE_TYPE.get(mime_type)
