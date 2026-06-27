"""文档解析数据模型 — 结构化文档表示。

借鉴 RAGFlow deepdoc 的 block 概念，将文档分解为类型化块。
每个块携带位置信息（bbox, page_num），供后续 chunking 和检索使用。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    """文本块 — 文档中的一段文本，带有布局分类和位置信息。"""

    text: str
    bbox: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1)
    page_num: int = 0
    layout_type: str = "text"   # title | text | header | footer | reference | equation
    level: int | None = None    # 标题级别 1-6，非标题为 None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TableBlock:
    """表格块 — 结构化表格数据，含 HTML 和语义描述。"""

    html: str                   # HTML <table> 结构
    description: str = ""       # 语义描述："该表展示了2024年各部门预算..."
    bbox: tuple[float, float, float, float] | None = None
    page_num: int = 0
    caption: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageBlock:
    """图片块 — 文档中的图片，可附带 VLM 生成的描述。"""

    image_bytes: bytes | None = None
    description: str | None = None  # VLM 生成的图片描述
    bbox: tuple[float, float, float, float] | None = None
    page_num: int = 0
    caption: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentMetadata:
    """文档级元数据。"""

    file_type: str = ""
    file_name: str = ""
    page_count: int = 0
    title: str | None = None
    author: str | None = None
    has_ocr: bool = False       # 是否经过了 OCR
    outline: list[dict] = field(default_factory=list)  # PDF 目录/书签
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """解析后的结构化文档 — parsing/ 模块的统一产出。

    文档被分解为有序的 blocks 列表，每个块携带类型和位置信息。
    下游 chunking/ 模块读取 blocks 进行语义分块。
    """

    blocks: list[TextBlock | TableBlock | ImageBlock] = field(default_factory=list)
    metadata: DocumentMetadata = field(default_factory=DocumentMetadata)

    @property
    def text_blocks(self) -> list[TextBlock]:
        """返回所有文本块（按原始顺序）。"""
        return [b for b in self.blocks if isinstance(b, TextBlock)]

    @property
    def table_blocks(self) -> list[TableBlock]:
        """返回所有表格块。"""
        return [b for b in self.blocks if isinstance(b, TableBlock)]

    @property
    def image_blocks(self) -> list[ImageBlock]:
        """返回所有图片块。"""
        return [b for b in self.blocks if isinstance(b, ImageBlock)]

    @property
    def plain_text(self) -> str:
        """将所有文本块拼接为纯文本（保留表格 HTML + 图片描述）。

        用于全文检索（BM25 tsvector）和快速预览。
        """
        parts: list[str] = []
        for b in self.blocks:
            if isinstance(b, TextBlock):
                parts.append(b.text)
            elif isinstance(b, TableBlock):
                parts.append(b.description)
                parts.append(b.html)
            elif isinstance(b, ImageBlock):
                if b.description:
                    parts.append(b.description)
                if b.caption:
                    parts.append(b.caption)
        return "\n\n".join(parts)
