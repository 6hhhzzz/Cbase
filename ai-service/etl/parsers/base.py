"""文件解析器抽象基类。"""

from abc import ABC, abstractmethod

from common import get_logger
from models.document import ParseResult

logger = get_logger(__name__)


class BaseParser(ABC):
    """文件解析器抽象。所有格式解析器必须继承此类。

    子类只需实现 ``_do_parse`` 和 ``supports``，错误处理由 ``parse`` 模板方法统一管理。
    """

    @abstractmethod
    async def _do_parse(self, file_path: str) -> ParseResult:
        """实际解析逻辑。子类实现此方法，无需自行处理异常。"""
        ...

    @abstractmethod
    def supports(self, file_type: str) -> bool:
        """返回此解析器是否支持该文件类型。"""
        ...

    async def parse(self, file_path: str) -> ParseResult:
        """模板方法：调用 ``_do_parse`` 并统一处理异常。

        如果解析失败（任何异常或 ImportError），返回空的 ParseResult。
        """
        file_type = self._file_type()
        try:
            return await self._do_parse(file_path)
        except ImportError:
            logger.warning(f"{file_type.upper()} 解析库未安装，返回空结果: {file_path}")
            return ParseResult(file_type=file_type, raw_text="", page_count=0)
        except Exception as e:
            logger.error(f"{file_type.upper()} 解析失败: {file_path}, error={e}")
            return ParseResult(file_type=file_type, raw_text="", page_count=0)

    def _file_type(self) -> str:
        """从类名推断文件类型（如 PdfParser → pdf）。"""
        name = type(self).__name__
        if name.endswith("Parser"):
            return name[:-6].lower()
        return "unknown"
