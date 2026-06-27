"""Markdown 解析器 — 支持 .md 文件。"""

import re
from pathlib import Path

from models.document import ParseResult

from .base import BaseParser


class MarkdownParser(BaseParser):
    """Markdown 文件解析器。去除 Markdown 语法标记，保留纯文本。"""

    # 需要移除或简化的 Markdown 语法
    _CLEANUP_PATTERNS = [
        (re.compile(r"^#{1,6}\s+", re.MULTILINE), ""),   # 标题标记
        (re.compile(r"\*\*(.+?)\*\*"), r"\1"),             # 粗体
        (re.compile(r"__(.+?)__"), r"\1"),                 # 粗体
        (re.compile(r"\*(.+?)\*"), r"\1"),                 # 斜体
        (re.compile(r"_(.+?)_"), r"\1"),                   # 斜体
        (re.compile(r"`{1,3}[^`]*`{1,3}"), ""),           # 行内代码/代码块
        (re.compile(r"\[(.+?)\]\(.+?\)"), r"\1"),          # 链接 [text](url)
        (re.compile(r"!\[.*?\]\(.+?\)"), ""),              # 图片
        (re.compile(r"^>\s+", re.MULTILINE), ""),          # 引用
        (re.compile(r"^[-*+]\s+", re.MULTILINE), ""),      # 无序列表
        (re.compile(r"^\d+\.\s+", re.MULTILINE), ""),      # 有序列表
        (re.compile(r"\|.*?\|"), ""),                      # 表格行（保留在 tables 中）
        (re.compile(r"^---+$", re.MULTILINE), ""),         # 水平线
        (re.compile(r"\n{3,}"), "\n\n"),                    # 多余空行
    ]

    async def _do_parse(self, file_path: str) -> ParseResult:
        """解析 Markdown 文件，去除语法标记。

        Args:
            file_path: Markdown 文件路径

        Returns:
            ParseResult，其中 raw_text 为清理后的纯文本
        """
        raw = Path(file_path).read_text(encoding="utf-8")

        # 提取表格数据
        tables = self._extract_tables(raw)

        # 清理 Markdown 标记
        text = raw
        for pattern, replacement in self._CLEANUP_PATTERNS:
            text = pattern.sub(replacement, text)

        # 去除首尾空白
        text = text.strip()

        return ParseResult(
            file_type="md",
            raw_text=text,
            page_count=1,
            tables=tables,
            metadata={"original_size": len(raw)},
        )

    def supports(self, file_type: str) -> bool:
        return file_type == "md"

    def _extract_tables(self, text: str) -> list[dict]:
        """从 Markdown 中提取表格数据。"""
        tables = []
        lines = text.split("\n")
        in_table = False
        current_table: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                if not stripped.count("---"):  # 跳过分隔行
                    current_table.append(stripped)
                in_table = True
            else:
                if in_table and current_table:
                    tables.append({"raw": "\n".join(current_table)})
                    current_table = []
                in_table = False

        if current_table:
            tables.append({"raw": "\n".join(current_table)})

        return tables
