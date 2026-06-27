"""PDF 解析器 — 使用 pypdf 提取文本。"""

from pypdf import PdfReader

from common import get_logger
from models.document import ParseResult
from .base import BaseParser

logger = get_logger(__name__)


class PDFParser(BaseParser):
    """PDF 文件解析器。逐页提取文本，保留页码元数据。"""

    async def _do_parse(self, file_path: str) -> ParseResult:
        reader = PdfReader(file_path)
        pages: list[str] = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)

        raw_text = "\n\n".join(pages)
        logger.info(
            f"PDF 解析完成: {file_path}, pages={len(reader.pages)}, chars={len(raw_text)}"
        )
        return ParseResult(
            file_type="pdf",
            raw_text=raw_text,
            page_count=len(reader.pages),
            tables=[],
            metadata={
                "total_pages": len(reader.pages),
                "pages_with_text": len(pages),
            },
        )

    def supports(self, file_type: str) -> bool:
        return file_type == "pdf"
