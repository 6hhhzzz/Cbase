"""布局识别器 — Phase 1b-full。

使用 ONNX YOLO 模型将页面区域分类为: title, text, table, figure, header, footer, equation。
参考 RAGFlow deepdoc/vision/layout_recognizer.py。

未安装 ONNX 模型时优雅降级为无操作（所有区域标记为 text）。
"""

import numpy as np

from common import get_logger
from .models import get_model_dir

logger = get_logger(__name__)

# 布局类别标签（InfiniFlow/deepdoc YOLOv10 模型）
_LAYOUT_LABELS = [
    "_background_", "Text", "Title", "Figure", "Figure caption",
    "Table", "Table caption", "Header", "Footer", "Reference", "Equation",
]

# 类别 → 内部标签映射
_LABEL_MAP = {
    0: None,            # _background_ — 忽略
    1: "text",
    2: "title",
    3: "image",         # Figure → image
    4: "image",         # Figure caption → image
    5: "table",         # Table → table
    6: "table",         # Table caption → table
    7: "header",
    8: "footer",
    9: "reference",
    10: "equation",
}


class LayoutAnalyzer:
    """布局分析器 — ONNX YOLOv10 模型。

    Usage::

        analyzer = LayoutAnalyzer()
        if analyzer.load():
            regions = analyzer.analyze(page_image)
            # regions: [{"bbox": (x0,y0,x1,y1), "type": "title", "score": 0.9}, ...]
    """

    def __init__(self):
        self._session = None
        self._loaded = False

    def load(self) -> bool:
        """加载布局模型。"""
        from .models import ensure_models

        model_path = get_model_dir() / "layout.onnx"
        if not model_path.exists():
            if not ensure_models():
                logger.debug("布局模型不可用，使用启发式规则")
                return False

        # 如果文件仍然不存在，使用启发式规则
        if not model_path.exists():
            return False

        try:
            import onnxruntime as ort
            self._session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
            self._loaded = True
            logger.info("布局识别模型加载成功")
            return True
        except Exception as e:
            logger.warning(f"布局模型加载失败: {e}")
            return False

    def analyze(self, image: np.ndarray) -> list[dict]:
        """分析页面布局，返回区域分类列表。

        Args:
            image: RGB 图片 (H, W, 3)

        Returns:
            [{"bbox": (x0,y0,x1,y1), "type": "title"|"text"|"table"|"image"|"header"|"footer", "score": float}, ...]
        """
        if not self._loaded or self._session is None:
            return []

        h, w = image.shape[:2]

        # 预处理: resize + normalize
        img = _preprocess_yolo(image)

        # 推理
        try:
            ort_inputs = {self._session.get_inputs()[0].name: img}
            outputs = self._session.run(None, ort_inputs)
        except Exception:
            return []

        # 后处理: 解析检测结果
        detections = _postprocess_yolo(outputs, h, w)

        return detections


def _preprocess_yolo(image: np.ndarray, target_size: int = 640) -> np.ndarray:
    """YOLO 预处理: resize + normalize + HWC→CHW + batch。"""
    import cv2

    h, w = image.shape[:2]
    scale = min(target_size / w, target_size / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (new_w, new_h))

    # 近似 letterbox padding
    canvas = np.zeros((target_size, target_size, 3), dtype=np.float32)
    canvas[:new_h, :new_w, :] = resized

    # 归一化
    canvas = canvas / 255.0

    # HWC → CHW
    canvas = np.transpose(canvas, (2, 0, 1))
    return np.expand_dims(canvas, axis=0).astype(np.float32)


def _postprocess_yolo(outputs: list, orig_h: int, orig_w: int) -> list[dict]:
    """YOLO 后处理: 解析 boxes + class + score。"""
    # outputs[0] shape: (1, N, 4 + num_classes) or similar
    # 简化实现: 取第一个输出，假设为 (N, 6) format: [x0,y0,x1,y1,score,class_id]
    if not outputs:
        return []

    det = outputs[0]
    if len(det.shape) > 2:
        det = det[0]  # remove batch dim

    results = []
    for row in det:
        if len(row) < 6:
            continue
        x0, y0, x1, y1, score, cls_id = row[:6]
        cls_id = int(cls_id)

        if score < 0.3:  # 置信度阈值
            continue

        label = _LABEL_MAP.get(cls_id)
        if label is None:
            continue

        # 还原坐标
        results.append({
            "bbox": (float(x0), float(y0), float(x1), float(y1)),
            "type": label,
            "score": float(score),
        })

    return results
