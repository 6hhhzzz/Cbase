"""Markdown 解析器 — 增强版：保留标题层级，表格提取为 TableBlock。

相比旧版（去除所有 Markdown 语法）的改进：
    - 保留了标题层级（# → level 1, ## → level 2, ...）
    - 表格提取为 TableBlock，不再混入纯文本流
    - 代码块保留语言标注
    - 链接保留文字丢弃 URL
"""

import re
from pathlib import Path

from common import get_logger
from parsing.base import BaseParser
from parsing.models import ParsedDocument, DocumentMetadata, TextBlock, TableBlock

logger = get_logger(__name__)


class MarkdownParser(BaseParser):
    """Markdown 文件解析器。保留标题层级，表格独立为 TableBlock。"""

    # 内联格式清理（保留文字，去标记）
    _INLINE_CLEANUP: list[tuple[re.Pattern, str]] = [
        (re.compile(r"\*\*(.+?)\*\*"), r"\1"),        # 粗体
        (re.compile(r"__(.+?)__"), r"\1"),              # 粗体
        (re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*"), r"\1"),  # 斜体
        (re.compile(r"`{1,3}([^`]+)`{1,3}"), r"\1"),   # 行内代码
        (re.compile(r"\[(.+?)\]\(.+?\)"), r"\1"),       # 链接
        (re.compile(r"!\[.*?\]\(.+?\)"), ""),            # 图片
    ]

    async def _do_parse(self, file_path: str) -> ParsedDocument:
        raw = Path(file_path).read_text(encoding="utf-8")
        lines = raw.split("\n")
        blocks: list[TextBlock | TableBlock] = []
        current_text: list[str] = []
        in_code_block = False

        i = 0
        while i < len(lines):
            line = lines[i]

            # ---- 代码块 ----
            if line.strip().startswith("```"):
                if current_text:
                    blocks.append(TextBlock(text="\n".join(current_text), layout_type="text"))
                    current_text = []
                in_code_block = not in_code_block
                if in_code_block:
                    lang = line.strip()[3:].strip()
                    blocks.append(TextBlock(
                        text=f"[代码块: {lang}]" if lang else "[代码块]",
                        layout_type="text",
                    ))
                i += 1
                if in_code_block:
                    code_lines = []
                    i, code_lines = _collect_code_block(lines, i)
                    blocks.append(TextBlock(
                        text="\n".join(code_lines),
                        layout_type="reference",
                    ))
                continue

            if in_code_block:
                i += 1
                continue

            # ---- 标题 ----
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                if current_text:
                    blocks.append(TextBlock(text="\n".join(current_text), layout_type="text"))
                    current_text = []
                level = len(heading_match.group(1))
                text = self._clean_inline(heading_match.group(2))
                blocks.append(TextBlock(text=text, layout_type="title", level=level))
                i += 1
                continue

            # ---- 表格 ----
            if line.strip().startswith("|") and line.strip().endswith("|"):
                i, table_block = _extract_markdown_table(lines, i)
                if table_block:
                    if current_text:
                        blocks.append(TextBlock(text="\n".join(current_text), layout_type="text"))
                        current_text = []
                    blocks.append(table_block)
                continue

            # ---- 水平线 ----
            if re.match(r"^[-*_]{3,}\s*$", line.strip()):
                i += 1
                continue

            # ---- 引用 ----
            if line.startswith(">"):
                text = self._clean_inline(line[1:].strip())
                if text:
                    blocks.append(TextBlock(text=text, layout_type="reference"))
                i += 1
                continue

            # ---- 列表项 ----
            list_match = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.+)$", line)
            if list_match:
                text = self._clean_inline(list_match.group(3))
                # 收集连续列表项
                list_items = [text]
                i += 1
                while i < len(lines):
                    sub = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.+)$", lines[i])
                    if sub:
                        list_items.append(self._clean_inline(sub.group(3)))
                        i += 1
                    else:
                        break
                list_text = "\n".join(f"• {item}" for item in list_items)
                blocks.append(TextBlock(text=list_text, layout_type="text"))
                continue

            # ---- 普通文本 ----
            cleaned = self._clean_inline(line)
            if cleaned.strip():
                current_text.append(cleaned)
            else:
                # 空行 = 段落分隔
                if current_text:
                    blocks.append(TextBlock(text="\n".join(current_text), layout_type="text"))
                    current_text = []
            i += 1

        # 最后一个文本块
        if current_text:
            blocks.append(TextBlock(text="\n".join(current_text), layout_type="text"))

        # 提取文档标题（第一个 h1）
        title = None
        for b in blocks:
            if isinstance(b, TextBlock) and b.layout_type == "title" and b.level == 1:
                title = b.text
                break

        logger.info(f"Markdown 解析完成: {file_path}, blocks={len(blocks)}, "
                    f"titles={len([b for b in blocks if isinstance(b, TextBlock) and b.layout_type == 'title'])}")
        return ParsedDocument(
            blocks=blocks,
            metadata=DocumentMetadata(
                file_type="md",
                file_name=file_path,
                page_count=1,
                title=title,
            ),
        )

    def supports(self, file_type: str) -> bool:
        return file_type == "md"

    def _clean_inline(self, text: str) -> str:
        """清理内联 Markdown 标记。"""
        for pattern, replacement in self._INLINE_CLEANUP:
            text = pattern.sub(replacement, text)
        return text


def _collect_code_block(lines: list[str], start: int) -> tuple[int, list[str]]:
    """收集代码块内容直到 ```。"""
    code_lines = []
    i = start
    while i < len(lines):
        if lines[i].strip().startswith("```"):
            return i + 1, code_lines
        code_lines.append(lines[i])
        i += 1
    return i, code_lines


def _extract_markdown_table(lines: list[str], start: int) -> tuple[int, TableBlock | None]:
    """从 Markdown 提取表格为 TableBlock。"""
    table_lines = []
    i = start
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
            i += 1
        else:
            break

    if len(table_lines) < 2:
        return i, None  # 至少需要表头 + 分隔行

    # 解析表格行
    data = []
    for tl in table_lines:
        cells = [c.strip() for c in tl[1:-1].split("|")]
        if all(c == "" for c in cells):
            continue
        # 跳过分隔行
        if all(re.match(r"^[-:]+$", c) for c in cells if c):
            continue
        data.append(cells)

    if len(data) < 1:
        return i, None

    html = _to_html_table(data)
    description = _describe_table(data)
    return i, TableBlock(
        html=html,
        description=description,
        metadata={"table_type": "markdown"},
    )


def _to_html_table(data: list[list[str]]) -> str:
    """二维数组 → HTML <table>。"""
    if not data:
        return ""
    rows = ["<table>"]
    rows.append("<thead><tr>")
    for cell in data[0]:
        rows.append(f"<th>{cell}</th>")
    rows.append("</tr></thead>")
    if len(data) > 1:
        rows.append("<tbody>")
        for row in data[1:]:
            rows.append("<tr>")
            for cell in row:
                rows.append(f"<td>{cell}</td>")
            rows.append("</tr>")
        rows.append("</tbody>")
    rows.append("</table>")
    return "\n".join(rows)


def _describe_table(data: list[list[str]]) -> str:
    """生成表格语义描述。"""
    headers = data[0] if data else []
    row_count = len(data) - 1
    col_count = len(headers)
    return f"Markdown 表格：{row_count} 行 × {col_count} 列，表头 [{', '.join(headers[:6])}]"
