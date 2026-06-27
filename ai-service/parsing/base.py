"""文件解析器抽象基类 — 增强版。

与旧版 BaseParser（返回 ParseResult）的区别：
    - 返回 ParsedDocument（结构化 blocks）而非纯文本字符串
    - 仍然使用模板方法模式，子类只需实现 _do_parse 和 supports
"""

from abc import ABC, abstractmethod

from common import get_logger
from .models import ParsedDocument

logger = get_logger(__name__)


class BaseParser(ABC):
    """文件解析器抽象基类。

    所有格式解析器必须继承此类，实现 ``_do_parse`` 和 ``supports``。
    ``parse`` 模板方法统一处理异常。
    """

    @abstractmethod
    async def _do_parse(self, file_path: str) -> ParsedDocument:
        """实际解析逻辑。子类实现此方法，无需自行处理异常。

        Args:
            file_path: 要解析的本地文件路径

        Returns:
            结构化的 ParsedDocument
        """
        ...

    @abstractmethod
    def supports(self, file_type: str) -> bool:
        """返回此解析器是否支持该文件类型。

        Args:
            file_type: 小写文件类型标识（如 "pdf", "docx", "pptx"）

        Returns:
            True 表示支持
        """
        ...

    async def parse(self, file_path: str) -> ParsedDocument:
        """模板方法：调用 ``_do_parse`` 并统一处理异常。

        如果解析失败，返回空的 ParsedDocument。

        Args:
            file_path: 要解析的本地文件路径

        Returns:
            ParsedDocument（失败时 blocks 为空列表）
        """
        file_type = self._file_type()
        try:
            return await self._do_parse(file_path)
        except ImportError:
            logger.warning(f"{file_type.upper()} 解析库未安装，返回空结果: {file_path}")
            return ParsedDocument()
        except Exception as e:
            logger.error(f"{file_type.upper()} 解析失败: {file_path}, error={e}")
            return ParsedDocument()

    def _file_type(self) -> str:
        """从类名推断文件类型（如 PdfParser → pdf）。"""
        name = type(self).__name__
        if name.endswith("Parser"):
            return name[:-6].lower()
        return "unknown"
