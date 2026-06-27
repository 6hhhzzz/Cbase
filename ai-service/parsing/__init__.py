"""文档解析引擎 — 借鉴 RAGFlow deepdoc 设计思路。

将原始文件 bytes 解析为结构化 ParsedDocument（含文本块、表格块、图片块及位置元数据）。
"""

from .models import ParsedDocument, TextBlock, TableBlock, ImageBlock, DocumentMetadata as ParsedDocMetadata
from .base import BaseParser
from .registry import ParserRegistry
from .orchestrator import ParseOrchestrator

__all__ = [
    "BaseParser",
    "ParserRegistry",
    "ParseOrchestrator",
    "ParsedDocument",
    "TextBlock",
    "TableBlock",
    "ImageBlock",
    "ParsedDocMetadata",
]
