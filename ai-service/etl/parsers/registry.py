"""解析器注册表 — 按文件类型路由到对应的 Parser 实现。"""

from common import get_logger

from .base import BaseParser
from .docx import DocxParser
from .html import HtmlParser
from .markdown import MarkdownParser
from .pdf import PDFParser
from .text import TextParser
from .xlsx import XlsxParser

logger = get_logger(__name__)


class ParserRegistry:
    """按文件类型管理解析器实例。

    新增文件格式支持只需注册新的 Parser，无需修改管道代码。
    """

    def __init__(self):
        self._parsers: dict[str, BaseParser] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """注册内置解析器。"""
        self.register(TextParser())
        self.register(MarkdownParser())
        self.register(PDFParser())
        self.register(DocxParser())
        self.register(XlsxParser())
        self.register(HtmlParser())

    def register(self, parser: BaseParser) -> None:
        """注册一个解析器。"""
        for ft in ["pdf", "docx", "xlsx", "html", "md", "txt"]:
            if parser.supports(ft):
                self._parsers[ft] = parser
                logger.info(f"注册解析器: {ft} → {type(parser).__name__}")

    def get(self, file_type: str) -> BaseParser | None:
        """根据文件类型获取解析器。"""
        return self._parsers.get(file_type)
