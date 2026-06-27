"""解析器注册表 — 按文件类型路由到对应的 Parser 实现。"""

from common import get_logger

from .base import BaseParser

logger = get_logger(__name__)


class ParserRegistry:
    """按文件类型管理解析器实例。

    新增文件格式支持只需注册新的 Parser，无需修改管道代码。

    用法::

        registry = ParserRegistry()
        parser = registry.get("pdf")
        doc = await parser.parse("/path/to/file.pdf")
    """

    def __init__(self):
        self._parsers: dict[str, BaseParser] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """注册内置解析器。延迟导入避免循环依赖。"""
        from .office.docx import DocxParser
        from .office.xlsx import XlsxParser
        from .web.html import HtmlParser
        from .web.markdown import MarkdownParser
        from .web.text import TextParser

        for parser in [
            TextParser(),
            MarkdownParser(),
            DocxParser(),
            XlsxParser(),
            HtmlParser(),
        ]:
            self.register(parser)

        # PPTX 解析器需要 python-pptx
        try:
            from .office.pptx import PptxParser
            self.register(PptxParser())
        except ImportError as e:
            logger.warning(f"PPTX 解析器未加载（python-pptx 未安装）: {e}")

        # PDF 解析器需要 ONNX 模型
        try:
            from .pdf.parser import PdfParser
            self.register(PdfParser())
        except ImportError as e:
            logger.warning(f"PDF 解析器未加载（ONNX/PaddleOCR 模型不可用）: {e}")

    def register(self, parser: BaseParser) -> None:
        """注册一个解析器。

        Args:
            parser: BaseParser 实例
        """
        supported = _ALL_FILE_TYPES()
        for ft in supported:
            try:
                if parser.supports(ft):
                    self._parsers[ft] = parser
                    logger.info(f"注册解析器: {ft} → {type(parser).__name__}")
            except Exception:
                pass

    def get(self, file_type: str) -> BaseParser | None:
        """根据文件类型获取解析器。

        Args:
            file_type: 小写文件类型标识

        Returns:
            BaseParser 实例，未找到返回 None
        """
        return self._parsers.get(file_type)

    @property
    def supported_types(self) -> list[str]:
        """返回所有已注册的文件类型。"""
        return list(self._parsers.keys())


def _ALL_FILE_TYPES() -> list[str]:
    """所有可能的文件类型标识。"""
    return ["pdf", "docx", "xlsx", "pptx", "html", "md", "txt"]
