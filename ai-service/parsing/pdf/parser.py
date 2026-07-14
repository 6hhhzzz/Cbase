"""PDF 解析器 — 逐页智能路由。

每页独立决策：
    - 文本层充足 + 无乱码 → 文本流 (pdfplumber 提取文字/表格/坐标)
    - 文本层缺失/乱码/低密度 → 视觉流 (渲染图片 → OCR → 布局分析)

参考 RAGFlow deepdoc 的逐页乱码检测 + 文本密度判定策略。
"""

import re

from common import get_logger
from parsing.base import BaseParser
from parsing.models import ParsedDocument, DocumentMetadata, TextBlock, TableBlock, ImageBlock
from parsing.pdf.merger import TextMerger

logger = get_logger(__name__)

# 文本流最低要求
_MIN_TEXT_CHARS = 50       # 每页最少字符数
_MIN_TEXT_WORDS = 10       # 每页最少单词数

# 乱码判定
_GARBLED_RATIO_THRESHOLD = 0.05  # PUA/CID 字符占比超过 5% → 乱码
_GARBLED_EMPTY_THRESHOLD = 0.80  # 连续空白占比超过 80% → 疑似扫描件

# 表格提取
_MIN_TABLE_ROWS = 2


class PdfParser(BaseParser):
    """PDF 解析器 — 逐页智能路由。

    每页处理流程::

        page → _analyze_page() → text_ok?
                ├── Yes → _parse_page_text(page)  [文本流: pdfplumber]
                └── No  → _parse_page_visual(page) [视觉流: OCR + Layout]
    """

    def __init__(self):
        self._ocr = None
        self._layout = None
        self._table_tsr = None
        self._visual_available = None  # True/False/None

    # ============================================================
    # 主入口
    # ============================================================

    async def _do_parse(self, file_path: str) -> ParsedDocument:
        import pdfplumber

        blocks: list[TextBlock | TableBlock | ImageBlock] = []
        pages_text = 0
        pages_visual = 0
        title = None

        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            if pdf.metadata and pdf.metadata.get("title"):
                title = pdf.metadata["title"]

            for page_num, page in enumerate(pdf.pages):
                use_visual = self._should_use_visual(page)

                if use_visual:
                    page_blocks = await self._parse_page_visual(page, page_num)
                    pages_visual += 1
                else:
                    page_blocks = self._parse_page_text(page, page_num)
                    pages_text += 1

                # 列检测 + 阅读顺序重排
                page_blocks = self._merge_page_blocks(page_blocks, page_num)
                blocks.extend(page_blocks)

        logger.info(
            f"PDF 解析完成: {file_path}, pages={total_pages}, "
            f"text_flow={pages_text}, visual_flow={pages_visual}, "
            f"blocks={len(blocks)}"
        )

        return ParsedDocument(
            blocks=blocks,
            metadata=DocumentMetadata(
                file_type="pdf", file_name=file_path,
                page_count=total_pages, title=title,
                has_ocr=(pages_visual > 0),
            ),
        )

    def supports(self, file_type: str) -> bool:
        return file_type == "pdf"

    # ============================================================
    # 智能路由
    # ============================================================

    def _should_use_visual(self, page) -> bool:
        """逐页判定：文本层是否足够。

        Returns:
            True  → 走视觉流 (OCR + Layout)
            False → 走文本流 (pdfplumber 提取)
        """
        # 1. 尝试提取文本
        try:
            text = page.extract_text() or ""
        except Exception:
            return True

        chars = len(text.strip())
        if chars < _MIN_TEXT_CHARS:
            return True

        # 2. 乱码检测
        if _detect_garbled(text):
            return True

        # 3. 文本密度检测
        try:
            words = page.extract_words()
        except Exception:
            words = []

        if len(words) < _MIN_TEXT_WORDS:
            return True

        # 4. 空白页检测（全是图表/扫描件）
        if _is_sparse(text):
            return True

        return False

    # ============================================================
    # 文本流 (pdfplumber)
    # ============================================================

    def _parse_page_text(self, page, page_num: int) -> list[TextBlock | TableBlock]:
        """文本流：pdfplumber 提取文字 + 表格 + 标题检测。"""
        blocks: list[TextBlock | TableBlock] = []

        # 表格提取
        for ti, table in enumerate(page.find_tables()):
            data = table.extract()
            if not data or len(data) < _MIN_TABLE_ROWS:
                continue
            max_cols = max(len(row) for row in data if row)
            data = [row + [""] * (max_cols - len(row)) for row in data]

            blocks.append(TableBlock(
                html=_rows_to_html(data),
                description=_describe_table(data, ti + 1),
                page_num=page_num,
                metadata={"table_index": ti + 1},
            ))

        # 文字提取 + 按行分组
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False)

        if not words:
            text = page.extract_text()
            if text and text.strip():
                blocks.append(TextBlock(
                    text=text.strip(), page_num=page_num, layout_type="text"
                ))
            return blocks

        for line_info in _words_to_lines(words):
            line_text = line_info["text"].strip()
            if not line_text:
                continue
            layout_type = "title" if _is_title(line_text) else "text"
            blocks.append(TextBlock(
                text=line_text, bbox=line_info["bbox"], page_num=page_num,
                layout_type=layout_type,
                level=1 if layout_type == "title" else None,
            ))

        return blocks

    # ============================================================
    # 视觉流 (Render + OCR + Layout)
    # ============================================================

    async def _parse_page_visual(
        self, page, page_num: int
    ) -> list[TextBlock | TableBlock | ImageBlock]:
        """视觉流：渲染页面为图片 → OCR → 布局分析。"""
        if not self._ensure_visual():
            # 视觉流不可用，降级到文本流
            return self._parse_page_text(page, page_num)

        blocks: list[TextBlock | TableBlock | ImageBlock] = []

        # 1. 渲染为图片
        try:
            page_img = page.to_image(resolution=200)
            import numpy as np
            img_array = np.array(page_img.original.convert("RGB"))
        except Exception:
            return self._parse_page_text(page, page_num)

        # 2. OCR 识别
        ocr_boxes = self._ocr.detect_and_recognize(img_array)
        if not ocr_boxes:
            return blocks

        # 3. 布局分类
        layout_regions = []
        if self._layout and self._layout._loaded:
            layout_regions = self._layout.analyze(img_array)

        # 4. OCR 结果 → TextBlock
        for box in ocr_boxes:
            bbox = box["bbox"]
            layout_type = _best_layout_type(bbox, layout_regions)
            blocks.append(TextBlock(
                text=box["text"], bbox=bbox, page_num=page_num,
                layout_type=layout_type,
                level=1 if layout_type == "title" else None,
            ))

        # 5. 表格结构识别
        if self._table_tsr and self._table_tsr._loaded and layout_regions:
            for tr in layout_regions:
                if tr.get("type") != "table":
                    continue
                bbox = tr.get("bbox")
                if bbox:
                    x0, y0, x1, y1 = map(int, bbox)
                    if 0 <= y0 < y1 and 0 <= x0 < x1:
                        crop = img_array[y0:y1, x0:x1]
                        html = self._table_tsr.extract(crop)
                        if html:
                            blocks.append(TableBlock(
                                html=html, description="表格",
                                bbox=bbox, page_num=page_num,
                            ))

        return blocks

    def _ensure_visual(self) -> bool:
        """确保视觉流组件已加载（只加载一次）。"""
        if self._visual_available is not None:
            return self._visual_available

        try:
            from .ocr import OcrEngine
            self._ocr = OcrEngine()
            if not self._ocr.load():
                self._visual_available = False
                return False

            from .layout import LayoutAnalyzer
            self._layout = LayoutAnalyzer()
            self._layout.load()

            from .table import TableStructureRecognizer
            self._table_tsr = TableStructureRecognizer()
            self._table_tsr.load()

            self._visual_available = True
            logger.info("视觉流组件就绪 (OCR + Layout + Table)")
            return True
        except ImportError:
            self._visual_available = False
            return False

    def _merge_page_blocks(
        self, page_blocks: list, page_num: int
    ) -> list:
        """对单页 blocks 执行列检测 + 阅读顺序重排。

        TextBlocks（有 bbox）按列分组、按阅读顺序重排；
        TableBlocks 和 ImageBlocks 保持原位，按 y 坐标插入。
        """
        # 分离有 bbox 的文本块和无 bbox 的块
        text_boxes = []
        other_blocks = []
        for b in page_blocks:
            if isinstance(b, TextBlock) and b.bbox:
                text_boxes.append({
                    "text": b.text,
                    "bbox": b.bbox,
                    "type": b.layout_type or "text",
                    "level": b.level if b.layout_type == "title" else None,
                })
            else:
                other_blocks.append(b)

        if len(text_boxes) <= 1:
            return page_blocks

        try:
            merger = TextMerger(max_columns=4)
            merged = merger.merge(text_boxes, page_num)
        except Exception:
            logger.warning(f"TextMerger 合并失败 (page {page_num})，保持原始顺序")
            return page_blocks

        # 转换回 TextBlock
        result = []
        for item in merged:
            result.append(TextBlock(
                text=item["text"],
                bbox=item.get("bbox"),
                page_num=item.get("page_num", page_num),
                layout_type=item.get("type", "text"),
                level=item.get("level"),
            ))

        # 非文本块按 y 坐标插入
        for other in other_blocks:
            other_y = other.bbox[1] if other.bbox else 0
            inserted = False
            for i, r in enumerate(result):
                r_y = r.bbox[1] if r.bbox else 0
                if other_y < r_y:
                    result.insert(i, other)
                    inserted = True
                    break
            if not inserted:
                result.append(other)

        return result


# ================================================================
# 辅助函数
# ================================================================

def _detect_garbled(text: str) -> bool:
    """检测文本是否乱码。

    检查 PUA 字符 (U+E000-U+F8FF) 和 CID 模式 (cid:NNN)。
    乱码占比 > 阈值 → 需要 OCR。
    """
    if not text:
        return False
    count = sum(1 for ch in text if 0xE000 <= ord(ch) <= 0xF8FF)
    if re.search(r"\(cid:\d+\)", text):
        count += text.count("(cid:") * 5
    return count / max(len(text), 1) > _GARBLED_RATIO_THRESHOLD


def _is_sparse(text: str) -> bool:
    """检测文本是否过于稀疏（疑似全是图表/白页）。"""
    if not text:
        return True
    whitespace = sum(1 for ch in text if ch in " \t\n\r\f\v")
    return whitespace / max(len(text), 1) > _GARBLED_EMPTY_THRESHOLD


def _words_to_lines(words: list[dict]) -> list[dict]:
    """单词列表按 y 坐标分组为文本行，保留 bbox 信息。

    Returns:
        [{"text": str, "bbox": (x0, y0, x1, y1)}, ...]
    """
    if not words:
        return []
    words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines, current, current_top = [], [words[0]], words[0]["top"]
    for w in words[1:]:
        if abs(w["top"] - current_top) < 3:
            current.append(w)
        else:
            sorted_current = sorted(current, key=lambda x: x["x0"])
            lines.append({
                "text": " ".join(w["text"] for w in sorted_current),
                "bbox": (
                    min(w["x0"] for w in sorted_current),
                    sorted_current[0]["top"],
                    max(w["x1"] for w in sorted_current),
                    sorted_current[-1]["bottom"],
                ),
            })
            current, current_top = [w], w["top"]
    sorted_current = sorted(current, key=lambda x: x["x0"])
    lines.append({
        "text": " ".join(w["text"] for w in sorted_current),
        "bbox": (
            min(w["x0"] for w in sorted_current),
            sorted_current[0]["top"],
            max(w["x1"] for w in sorted_current),
            sorted_current[-1]["bottom"],
        ),
    })
    return lines


def _is_title(text: str) -> bool:
    """启发式标题检测。"""
    if len(text) > 100:
        return False
    if re.match(r"^(第[一二三四五六七八九十]+[章节部分]|[一二三四五六七八九十]+[、.）\)]|\d+[\.、)）])", text):
        return True
    if len(text) < 60 and text.endswith(("、", "：", ":")):
        return True
    return False


def _rows_to_html(data: list[list[str]]) -> str:
    if not data:
        return ""
    parts = ["<table><thead><tr>"]
    parts.extend(f"<th>{c or ''}</th>" for c in data[0])
    parts.append("</tr></thead><tbody>")
    for row in data[1:]:
        parts.append("<tr>")
        parts.extend(f"<td>{c or ''}</td>" for c in row)
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


def _describe_table(data: list[list[str]], idx: int) -> str:
    headers = data[0] if data else []
    return f"表格 {idx}：{len(data)-1}行×{len(headers)}列，表头[{', '.join(h[:20] for h in headers[:6])}]"


def _best_layout_type(bbox: tuple, regions: list[dict]) -> str:
    """找重叠最大的布局区域类型。"""
    if not regions:
        return "text"
    bx0, by0, bx1, by1 = bbox
    best_type, best_overlap = "text", 0
    for r in regions:
        rx0, ry0, rx1, ry1 = r["bbox"]
        ox0, oy0 = max(bx0, rx0), max(by0, ry0)
        ox1, oy1 = min(bx1, rx1), min(by1, ry1)
        if ox0 < ox1 and oy0 < oy1:
            overlap = (ox1 - ox0) * (oy1 - oy0)
            if overlap > best_overlap:
                best_overlap = overlap
                best_type = r.get("type", "text")
    return best_type
