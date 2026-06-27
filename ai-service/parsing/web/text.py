"""纯文本解析器 — 支持 .txt 文件（UTF-8 / GBK 自动检测）。"""

from pathlib import Path

from common import get_logger
from parsing.base import BaseParser
from parsing.models import ParsedDocument, DocumentMetadata, TextBlock

logger = get_logger(__name__)


class TextParser(BaseParser):
    """纯文本文件解析器。直接读取文件内容，不分块。

    支持 UTF-8 和 GBK 编码自动回退。
    """

    async def _do_parse(self, file_path: str) -> ParsedDocument:
        encoding = "utf-8"
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = Path(file_path).read_text(encoding="gbk")
            encoding = "gbk"

        blocks = [TextBlock(text=content.strip(), layout_type="text")]
        logger.info(f"TXT 解析完成: {file_path}, chars={len(content)}, encoding={encoding}")
        return ParsedDocument(
            blocks=blocks,
            metadata=DocumentMetadata(
                file_type="txt",
                file_name=file_path,
                page_count=1,
                extra={"encoding": encoding, "chars": len(content)},
            ),
        )

    def supports(self, file_type: str) -> bool:
        return file_type == "txt"
