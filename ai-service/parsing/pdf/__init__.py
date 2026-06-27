"""PDF 深度解析模块。

Phase 1b-minimal (已完成):
    - pdf/parser.py   — PdfParser（pdfplumber 提取文字+表格+乱码检测）

Phase 1b-full (已完成，需 ONNX 模型):
    - pdf/ocr.py      — OcrEngine, TextDetector, TextRecognizer
    - pdf/layout.py   — LayoutAnalyzer（YOLO ONNX 布局分类）
    - pdf/table.py    — TableStructureRecognizer（表格结构识别）
    - pdf/merger.py   — TextMerger（KMeans 列检测 + 阅读顺序重排）

模型下载：
    首次加载时自动从 HuggingFace InfiniFlow/deepdoc 下载（约 50MB）。
    手动下载: huggingface-cli download InfiniFlow/deepdoc --local-dir models/deepdoc
"""

from .parser import PdfParser

__all__ = ["PdfParser"]
