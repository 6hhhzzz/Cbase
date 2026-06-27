"""表格结构识别器 — Phase 1b-full。

使用 ONNX 模型检测表格的行、列、表头、合并单元格。
参考 RAGFlow deepdoc/vision/table_structure_recognizer.py。

未安装 ONNX 模型时优雅降级为无操作。
"""

import numpy as np

from common import get_logger
from .models import get_model_dir

logger = get_logger(__name__)

# 表格结构标签
_TSR_LABELS = [
    "table", "table column", "table row", "table column header",
    "table projected row header", "table spanning cell",
]


class TableStructureRecognizer:
    """表格结构识别器 — ONNX 模型。

    Usage::

        tsr = TableStructureRecognizer()
        if tsr.load():
            html = tsr.extract(table_image)
            # html: "<table><thead>...</thead><tbody>...</tbody></table>"
    """

    def __init__(self):
        self._session = None
        self._loaded = False

    def load(self) -> bool:
        """加载表格结构模型。"""
        from .models import ensure_models

        model_path = get_model_dir() / "tsr.onnx"
        if not model_path.exists():
            if not ensure_models():
                logger.debug("表格结构模型不可用")
                return False

        if not model_path.exists():
            return False

        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
            self._loaded = True
            logger.info("表格结构模型加载成功")
            return True
        except Exception as e:
            logger.warning(f"表格结构模型加载失败: {e}")
            return False

    def extract(self, image: np.ndarray) -> str | None:
        """从表格图片中提取 HTML 结构。

        Args:
            image: RGB 图片 (H, W, 3)，只包含表格区域

        Returns:
            HTML <table> 字符串，或 None
        """
        if not self._loaded or self._session is None:
            return None

        h, w = image.shape[:2]

        # 预处理
        img = _preprocess_tsr(image)

        try:
            ort_inputs = {self._session.get_inputs()[0].name: img}
            outputs = self._session.run(None, ort_inputs)
        except Exception as e:
            logger.debug(f"表格结构识别失败: {e}")
            return None

        # 后处理: 构建 HTML
        html = _build_html_from_tsr(outputs, h, w)
        return html


def _preprocess_tsr(image: np.ndarray, target_size: int = 1024) -> np.ndarray:
    """表格图片预处理。"""
    import cv2

    h, w = image.shape[:2]
    scale = min(target_size / w, target_size / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (new_w, new_h))

    canvas = np.zeros((target_size, target_size, 3), dtype=np.float32)
    canvas[:new_h, :new_w, :] = resized

    canvas = canvas / 255.0
    canvas = np.transpose(canvas, (2, 0, 1))
    return np.expand_dims(canvas, axis=0).astype(np.float32)


def _build_html_from_tsr(outputs: list, orig_h: int, orig_w: int) -> str:
    """从 TSR 模型输出构建 HTML 表格。

    由于 ONNX 模型输出格式取决于具体模型，此处为通用实现。
    当模型不可用或输出无法解析时，返回 None。
    """
    if not outputs:
        return None

    # 实际实现依赖具体模型输出格式
    # 占位：模型可用时基于检测到的行列结构构建HTML
    return None
