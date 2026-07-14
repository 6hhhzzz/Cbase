"""OCR 引擎 — 云端 API（优先）+ 本地 ONNX PaddleOCR（降级）。

数据流:
    图片 (np.ndarray)
      → APIOCR (DashScope OCR) — 优先
      → TextDetector(det.onnx) → TextRecognizer(rec.onnx) — 降级
"""

import base64
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from common import get_logger
from .models import get_model_dir, ensure_models

logger = get_logger(__name__)

# 全局线程池用于 CPU ONNX 推理
_EXECUTOR = ThreadPoolExecutor(max_workers=2)

# 检测模型参数
_DET_IMG_SHAPE = (960, 960)
_DET_THRESH = 0.3
_DET_BOX_THRESH = 0.5
_UNCLIP_RATIO = 2.0

# 识别模型参数
_REC_IMG_SHAPE = (48, 320)


class APIOCR:
    """云端 OCR API 封装（DashScope OCR 等）。

    与 OcrEngine 同接口，可作为 drop-in replacement。

    用法::

        ocr = APIOCR(api_key="sk-xxx", api_path="/api/v1/services/ocr/ocr-recognition",
                     base_url="https://dashscope.aliyuncs.com")
        if ocr.load():
            boxes = ocr.detect_and_recognize(page_image)
    """

    def __init__(self, api_key: str, base_url: str = "",
                 api_path: str = "", model_name: str = "ocr-recognition"):
        self._api_key = api_key
        self._model_name = model_name
        self._url = f"{base_url.rstrip('/')}{api_path}" if (base_url and api_path) else ""
        self._loaded = bool(self._api_key and self._url)

    def load(self) -> bool:
        return self._loaded

    def detect_and_recognize(self, image: np.ndarray) -> list[dict]:
        """对单页图片执行云端 OCR。

        Args:
            image: RGB 图片 (H, W, 3)

        Returns:
            [{"text": str, "bbox": (x0,y0,x1,y1), "score": float}, ...]
        """
        if not self._loaded:
            return []

        try:
            # 编码为 JPEG base64
            _, buf = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
            img_b64 = base64.b64encode(buf).decode("utf-8")

            # DashScope OCR API 格式
            payload = {
                "model": self._model_name,
                "input": {"image": f"data:image/jpeg;base64,{img_b64}"},
            }

            # 同步 HTTP 调用（ETL 管道中 OCR 在 executor 线程中运行）
            import requests
            resp = requests.post(
                self._url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code != 200:
                logger.warning(f"OCR API 返回 {resp.status_code}: {resp.text[:200]}")
                return []

            data = resp.json()
            return self._parse_response(data)

        except Exception as e:
            logger.warning(f"OCR API 调用失败: {e}")
            return []

    @staticmethod
    def _parse_response(data: dict) -> list[dict]:
        """解析 DashScope OCR 响应为标准格式。

        DashScope OCR 返回格式:
          {"output": {"texts": [
            {"content": "识别文本", "pos": {"x": ..., "y": ..., "width": ..., "height": ...}, "confidence": 0.98},
            ...
          ]}}
        """
        results = []
        texts = data.get("output", {}).get("texts", [])
        for t in texts:
            content = t.get("content", "")
            if not content:
                continue
            # pos 可能是 list 坐标或 x/y/width/height
            pos = t.get("pos", {})
            if pos:
                x0 = float(pos.get("x", 0)) if isinstance(pos, dict) else float(pos[0])
                y0 = float(pos.get("y", 0)) if isinstance(pos, dict) else float(pos[1])
                x1 = x0 + float(pos.get("width", 0)) if isinstance(pos, dict) else float(pos[2]) - x0
                y1 = y0 + float(pos.get("height", 0)) if isinstance(pos, dict) else float(pos[3]) - y0
            else:
                x0, y0, x1, y1 = 0, 0, 0, 0

            results.append({
                "text": content,
                "bbox": (x0, y0, x1, y1),
                "score": float(t.get("confidence", 0.95)),
            })

        return results


class OcrEngine:
    """OCR 引擎 — 文本检测 + 识别。

    用法::

        engine = OcrEngine()
        if engine.load():
            boxes = engine.detect_and_recognize(page_image)
            # boxes: [{"text": "...", "bbox": (x0,y0,x1,y1), "score": 0.95}, ...]
    """

    def __init__(self):
        self._detector: TextDetector | None = None
        self._recognizer: TextRecognizer | None = None
        self._loaded = False

    def load(self) -> bool:
        """加载 ONNX 模型。首次调用会自动下载。"""
        if self._loaded:
            return True

        if not ensure_models():
            logger.warning("OCR 模型下载失败，OCR 功能不可用")
            return False

        model_dir = get_model_dir()

        det_path = model_dir / "det.onnx"
        rec_path = model_dir / "rec.onnx"
        char_dict = model_dir / "ocr.res"

        if not det_path.exists() or not rec_path.exists():
            logger.warning("OCR 模型文件缺失")
            return False

        try:
            self._detector = TextDetector(str(det_path))
            self._recognizer = TextRecognizer(str(rec_path), str(char_dict))
            self._loaded = True
            logger.info("OCR 引擎加载成功")
            return True
        except Exception as e:
            logger.error(f"OCR 引擎加载失败: {e}")
            return False

    def detect_and_recognize(self, image: np.ndarray) -> list[dict]:
        """对单页图片执行文本检测+识别。

        Args:
            image: RGB 图片 (H, W, 3)

        Returns:
            [{"text": str, "bbox": (x0,y0,x1,y1), "score": float}, ...]
        """
        if not self._loaded or not self._detector or not self._recognizer:
            return []

        # 1. 检测文本区域
        boxes = self._detector.detect(image)
        if not boxes:
            return []

        # 2. 识别每个区域的文本
        results = []
        for box in boxes:
            # box: [[x0,y0], [x1,y1], [x2,y2], [x3,y3]] — 四个角点
            cropped = _crop_image(image, box)
            if cropped is None or cropped.size == 0:
                continue

            text, score = self._recognizer.recognize(cropped)
            if text:
                x0 = min(p[0] for p in box)
                y0 = min(p[1] for p in box)
                x1 = max(p[0] for p in box)
                y1 = max(p[1] for p in box)
                results.append({
                    "text": text,
                    "bbox": (float(x0), float(y0), float(x1), float(y1)),
                    "score": float(score),
                })

        return results


class TextDetector:
    """DBNet 文本检测器 (det.onnx)。

    输入: 预处理后的图片 (1, 3, H, W)
    输出: 概率图 → 二值化 → 轮廓 → 文本框坐标
    """

    def __init__(self, model_path: str):
        import onnxruntime as ort
        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )

    def detect(self, image: np.ndarray) -> list[list[list[float]]]:
        """检测图片中的文本区域。

        Returns:
            list of boxes, each box = [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
        """
        # 确保输入是 3 通道 RGB
        if len(image.shape) == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
        elif image.shape[2] == 1:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)

        h, w = image.shape[:2]

        # 预处理
        img, ratio_w, ratio_h = _preprocess_det(image, _DET_IMG_SHAPE)

        # 推理
        ort_inputs = {self._session.get_inputs()[0].name: img}
        outputs = self._session.run(None, ort_inputs)
        pred = outputs[0]  # (1, 1, H, W) probability map

        # 后处理: 概率图 → 二值化 → 轮廓 → 文本框
        boxes = _postprocess_det(
            pred[0, 0],
            ratio_w=ratio_w,
            ratio_h=ratio_h,
            thresh=_DET_THRESH,
            box_thresh=_DET_BOX_THRESH,
            unclip_ratio=_UNCLIP_RATIO,
            max_size=max(h, w),
        )

        return boxes


class TextRecognizer:
    """CRNN 文本识别器 (rec.onnx)。

    输入: 裁剪后的文字图片 (经预处理)
    输出: 识别的文本序列
    """

    def __init__(self, model_path: str, char_dict_path: str | None = None):
        import onnxruntime as ort
        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )
        self._char_dict = _load_char_dict(char_dict_path)

    def recognize(self, image: np.ndarray) -> tuple[str, float]:
        """识别裁剪图片中的文本。

        Returns:
            (text, confidence_score)
        """
        if image is None or image.size == 0:
            return "", 0.0

        # 预处理
        img = _preprocess_rec(image, _REC_IMG_SHAPE)

        # 推理
        ort_inputs = {self._session.get_inputs()[0].name: img}
        outputs = self._session.run(None, ort_inputs)
        pred = outputs[0]  # (1, seq_len, num_classes)

        # CTC 解码
        text, score = _ctc_decode(pred[0], self._char_dict)

        return text, score


# ---- 预处理 ----

def _preprocess_det(
    image: np.ndarray, target_shape: tuple[int, int]
) -> tuple[np.ndarray, float, float]:
    """检测模型预处理: resize + normalize + BGR→RGB + HWC→CHW。

    Returns:
        (processed_img, ratio_w, ratio_h) — 含缩放比用于坐标还原
    """
    h, w = image.shape[:2]
    target_h, target_w = target_shape

    ratio_w = w / target_w
    ratio_h = h / target_h

    # 等比例缩放 + padding
    scale = min(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(image, (new_w, new_h))

    # 创建目标尺寸的画布并居中
    canvas = np.zeros((target_h, target_w, 3), dtype=np.float32)
    canvas[:new_h, :new_w, :] = resized

    # 归一化: [0,255] → [0,1]
    canvas = canvas / 255.0

    # 标准化: mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    canvas = (canvas - mean) / std

    # HWC → CHW + batch
    canvas = np.transpose(canvas, (2, 0, 1))
    canvas = np.expand_dims(canvas, axis=0).astype(np.float32)

    return canvas, ratio_w, ratio_h


def _preprocess_rec(
    image: np.ndarray, target_shape: tuple[int, int]
) -> np.ndarray:
    """识别模型预处理: resize → transpose → normalize → pad。与 RAGFlow 一致。

    Returns:
        (1, 3, H, W) tensor
    """
    img_h, img_w_max = target_shape  # (48, 320)

    # 确保 3 通道 RGB
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)

    h, w = image.shape[:2]
    ratio = w / h
    if ratio > img_w_max / img_h:
        resized_w = img_w_max
    else:
        resized_w = int(math.ceil(img_h * ratio))
    resized_w = max(resized_w, 4)

    resized = cv2.resize(image, (resized_w, img_h))

    # RAGFlow 方式：transpose → /255 → normalize → pad (CHW)
    resized = resized.astype(np.float32).transpose((2, 0, 1))  # HWC → CHW
    resized /= 255.0
    resized -= 0.5
    resized /= 0.5  # 映射 [0,255] → [-1,1]

    # 填充到固定宽度 (C, H, maxW)
    c, _, _ = resized.shape
    padding = np.zeros((c, img_h, img_w_max), dtype=np.float32)
    padding[:, :, :resized_w] = resized

    return np.expand_dims(padding, axis=0).astype(np.float32)


# ---- 后处理 ----

def _postprocess_det(
    pred: np.ndarray,
    ratio_w: float,
    ratio_h: float,
    thresh: float,
    box_thresh: float,
    unclip_ratio: float,
    max_size: int,
) -> list[list[list[float]]]:
    """检测后处理: 概率图 → 二值化 → 轮廓 → 文本框。

    Returns:
        list of boxes, each box = [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
    """
    # 二值化
    mask = (pred > thresh).astype(np.uint8) * 255

    # 找轮廓
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for contour in contours:
        # 最小外接矩形 → 四点坐标
        rect = cv2.minAreaRect(contour)
        points = cv2.boxPoints(rect)
        points = _order_points(points)

        # 过滤太小或太大的框
        side_len = max(
            np.linalg.norm(points[0] - points[1]),
            np.linalg.norm(points[1] - points[2]),
        )
        if side_len < 3 or side_len > max_size * 0.8:
            continue

        # 还原缩放
        scaled_points = [[
            float(p[0] * ratio_w),
            float(p[1] * ratio_h),
        ] for p in points]

        boxes.append(scaled_points)

    return boxes


def _ctc_decode(pred: np.ndarray, char_dict: list[str]) -> tuple[str, float]:
    """CTC 贪心解码。

    Args:
        pred: (seq_len, num_classes) log probabilities
        char_dict: 字符字典列表

    Returns:
        (decoded_text, confidence)
    """
    if char_dict is None or len(char_dict) == 0:
        return "", 0.0

    # argmax per timestep
    indices = np.argmax(pred, axis=1)
    probs = np.max(pred, axis=1)

    # 合并连续重复 + 去除 blank (index 0)
    # 模型输出: idx 0 = blank, idx 1+ = ocr_chars[idx-1]
    last_idx = 0
    decoded = []
    confidences = []

    for idx, prob in zip(indices, probs):
        cidx = idx - 1  # idx 1 → chars[0]
        if idx != last_idx and idx > 0 and cidx < len(char_dict):
            decoded.append(char_dict[cidx])
            confidences.append(prob)
        last_idx = idx

    text = "".join(decoded)
    score = float(np.mean(confidences)) if confidences else 0.0

    return text, score


# ---- 工具函数 ----

def _order_points(points: np.ndarray) -> np.ndarray:
    """将四点按逆时针排列: 左上→右上→右下→左下。"""
    # 按和排序（左上最小）
    s = points.sum(axis=1)
    tl = points[np.argmin(s)]
    br = points[np.argmax(s)]

    # 按差排序（右上最小）
    diff = np.diff(points, axis=1)
    tr = points[np.argmin(diff)]
    bl = points[np.argmax(diff)]

    return np.array([tl, tr, br, bl], dtype=np.float32)


def _crop_image(image: np.ndarray, box: list[list[float]]) -> np.ndarray | None:
    """从图片中裁剪文本区域。"""
    h, w = image.shape[:2]

    # 计算裁剪区域
    x0 = max(0, int(min(p[0] for p in box)))
    y0 = max(0, int(min(p[1] for p in box)))
    x1 = min(w, int(max(p[0] for p in box)))
    y1 = min(h, int(max(p[1] for p in box)))

    if x0 >= x1 or y0 >= y1:
        return None

    return image[y0:y1, x0:x1]


def _load_char_dict(path: str | None) -> list[str]:
    """加载字符字典文件。

    PaddleOCR CTC 模型输出: index 0 = blank, index 1+ = ocr.res 字符。
    模型输出 6625 类 = 1(blank) + 6622(ocr.res) + 2(extra tokens)。
    """
    if path is None or not Path(path).exists():
        return [chr(i) for i in range(0x4E00, 0x9FA0)] + list("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")

    try:
        with open(path, encoding="utf-8") as f:
            chars = [line.rstrip("\n") for line in f if line.strip()]
        return chars
    except Exception:
        return []
    except Exception:
        return []
