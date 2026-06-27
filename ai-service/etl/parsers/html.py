"""HTML 解析器 — 支持 .html 文件，使用 BeautifulSoup 提取纯文本。"""

from pathlib import Path

from common import get_logger
from models.document import ParseResult

from .base import BaseParser

logger = get_logger(__name__)

# 需要完全移除的标签及其内容
_REMOVE_TAGS = {"script", "style", "nav", "footer", "noscript", "iframe"}


class HtmlParser(BaseParser):
    """HTML 文件解析器。提取 body 中的可见文本，剥离标签。"""

    async def _do_parse(self, file_path: str) -> ParseResult:
        from bs4 import BeautifulSoup
        import re

        raw = Path(file_path).read_text(encoding="utf-8")
        soup = BeautifulSoup(raw, "html.parser")

        for tag in soup.find_all(_REMOVE_TAGS):
            tag.decompose()

        tables: list[dict] = []
        for i, table in enumerate(soup.find_all("table")):
            table_data = _extract_html_table(table)
            if table_data:
                tables.append({
                    "index": i,
                    "headers": table_data[0] if table_data else [],
                    "rows": table_data[1:] if len(table_data) > 1 else [],
                })

        body = soup.find("body")
        if body is None:
            body = soup

        text = body.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        logger.info(f"HTML 解析完成: {file_path}, chars={len(text)}, tables={len(tables)}")
        return ParseResult(
            file_type="html", raw_text=text, page_count=1, tables=tables,
            metadata={"title": soup.title.string if soup.title else None, "table_count": len(tables)},
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
