"""HTML 解析器 — 使用 BeautifulSoup 提取结构化内容。

与旧版相比：
    - 保留标题层级信息（h1-h6 → level 1-6）
    - 表格提取为 TableBlock（含 HTML + 描述）
"""

from pathlib import Path

from common import get_logger
from parsing.base import BaseParser
from parsing.models import ParsedDocument, DocumentMetadata, TextBlock, TableBlock

logger = get_logger(__name__)

# 需要完全移除的标签及其内容
_REMOVE_TAGS = {"script", "style", "nav", "footer", "noscript", "iframe"}
# 标题标签 → 级别映射
_HEADING_LEVEL = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class HtmlParser(BaseParser):
    """HTML 文件解析器。提取结构化内容，保留标题层级。"""

    async def _do_parse(self, file_path: str) -> ParsedDocument:
        from bs4 import BeautifulSoup

        raw = Path(file_path).read_text(encoding="utf-8")
        soup = BeautifulSoup(raw, "html.parser")

        # 移除无关标签
        for tag in soup.find_all(_REMOVE_TAGS):
            tag.decompose()

        blocks: list[TextBlock | TableBlock] = []

        # 提取文档标题
        doc_title = None
        if soup.title and soup.title.string:
            doc_title = soup.title.string.strip()

        body = soup.find("body") or soup

        # 按文档顺序遍历顶级元素和表格
        for element in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "ul", "ol", "blockquote", "pre"], recursive=True):
            # 跳过嵌套在其他遍历元素内的元素
            parent_name = element.parent.name if element.parent else ""
            if parent_name in {"li", "td", "th", "thead", "tbody", "tfoot", "tr"}:
                continue

            tag = element.name

            # ---- 标题 ----
            if tag in _HEADING_LEVEL:
                text = element.get_text(strip=True)
                if text:
                    blocks.append(TextBlock(
                        text=text,
                        layout_type="title",
                        level=_HEADING_LEVEL[tag],
                    ))

            # ---- 段落 ----
            elif tag == "p":
                text = element.get_text(strip=True)
                if text:
                    blocks.append(TextBlock(
                        text=text,
                        layout_type="text",
                    ))

            # ---- 引用/代码块 ----
            elif tag in {"blockquote", "pre"}:
                text = element.get_text(strip=True)
                if text:
                    blocks.append(TextBlock(
                        text=text,
                        layout_type="reference" if tag == "blockquote" else "text",
                    ))

            # ---- 列表 ----
            elif tag in {"ul", "ol"}:
                items = []
                for li in element.find_all("li", recursive=False):
                    items.append(li.get_text(strip=True))
                if items:
                    text = "\n".join(f"• {item}" for item in items)
                    blocks.append(TextBlock(text=text, layout_type="text"))

            # ---- 表格 ----
            elif tag == "table":
                table_data = _extract_html_table(element)
                if table_data:
                    html_table = _to_html_table(table_data)
                    description = _describe_table(table_data, None)
                    blocks.append(TableBlock(
                        html=html_table,
                        description=description,
                        caption=None,
                        metadata={"table_index": len([b for b in blocks if isinstance(b, TableBlock)]) + 1},
                    ))

        logger.info(f"HTML 解析完成: {file_path}, blocks={len(blocks)}, "
                    f"titles={len([b for b in blocks if isinstance(b, TextBlock) and b.layout_type == 'title'])}")
        return ParsedDocument(
            blocks=blocks,
            metadata=DocumentMetadata(
                file_type="html",
                file_name=file_path,
                page_count=1,
                title=doc_title,
            ),
        )

    def supports(self, file_type: str) -> bool:
        return file_type == "html"


def _extract_html_table(table) -> list[list[str]]:
    """从 BeautifulSoup Table 元素提取二维数组。"""
    data = []
    for tr in table.find_all("tr"):
        cells = []
        for cell in tr.find_all(["td", "th"]):
            cells.append(cell.get_text(strip=True))
        if any(c for c in cells):
            data.append(cells)
    return data


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


def _describe_table(data: list[list[str]], table_name: str | None) -> str:
    """生成表格语义描述。"""
    if not data:
        return ""
    headers = data[0] if data else []
    row_count = len(data) - 1
    col_count = len(headers)
    label = f"表格'{table_name}'" if table_name else "表格"
    return f"{label}：{row_count} 行 × {col_count} 列，表头 [{', '.join(headers[:6])}]"
