"""纯文本解析器 — 支持 .txt 文件。"""

from pathlib import Path

from models.document import ParseResult

from .base import BaseParser


class TextParser(BaseParser):
    """纯文本文件解析器。直接读取文件内容。"""

    async def _do_parse(self, file_path: str) -> ParseResult:
        """读取纯文本文件内容，UTF-8 → GBK 回退。"""
        try:
            content = Path(file_path).read_text(encoding="utf-8")
            return ParseResult(file_type="txt", raw_text=content,
                page_count=1, metadata={"encoding": "utf-8"})
        except UnicodeDecodeError:
            content = Path(file_path).read_text(encoding="gbk")
            return ParseResult(file_type="txt", raw_text=content,
                page_count=1, metadata={"encoding": "gbk"})

    def supports(self, file_type: str) -> bool:
        return file_type == "txt"
