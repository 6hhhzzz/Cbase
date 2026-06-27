"""Office 文档解析器集合。"""

from .docx import DocxParser
from .xlsx import XlsxParser
from .pptx import PptxParser

__all__ = ["DocxParser", "XlsxParser", "PptxParser"]
