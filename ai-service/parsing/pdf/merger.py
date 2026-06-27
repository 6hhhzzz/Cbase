"""文本合并器 — 多列检测 + 阅读顺序重排。

Phase 1b-full: KMeans 列检测 + 水平合并 + 垂直合并 → 正确阅读顺序。
Phase 1b-minimal 已有简单按 y 坐标排序的版本，本模块提供增强版。

参考 RAGFlow deepdoc 的列检测（KMeans + Silhouette）和文本合并思路。
"""

import numpy as np

from common import get_logger

logger = get_logger(__name__)


class TextMerger:
    """文本合并器 — 将页面中分散的文字块合并为正确阅读顺序的段落。

    借鉴 RAGFlow 的 KMeans 列检测 + 启发式合并：
        1. KMeans 聚类 x0 坐标 → 列数 + 列边界
        2. 水平合并：同一行内相邻文字块合并
        3. 垂直合并：同一列内上下文字块（基于重叠判断）
        4. 按 (page, col, y) 重排阅读顺序
    """

    def __init__(self, max_columns: int = 4):
        self._max_columns = max_columns

    def merge(
        self,
        text_boxes: list[dict],
        page_num: int = 0,
    ) -> list[dict]:
        """合并文字块并确定阅读顺序。

        Args:
            text_boxes: [{"text": str, "bbox": (x0,y0,x1,y1), "type": str}, ...]
                        bbox 格式: (left, top, right, bottom)
            page_num: 页码（用于多页排序）

        Returns:
            合并后的文字块列表，按阅读顺序排列
        """
        if not text_boxes:
            return []

        if len(text_boxes) <= 1:
            return text_boxes

        # 1. 提取 x0 坐标用于列检测
        x0_coords = np.array([b["bbox"][0] for b in text_boxes]).reshape(-1, 1)

        # 2. KMeans 列检测 → 返回列数 + labels + centroids
        n_cols, labels, centroids = _detect_columns(x0_coords, self._max_columns)

        # 3. 按列分组（优先使用 labels，其次 centroids，降级等距分箱）
        col_groups = _group_by_columns(text_boxes, n_cols, labels, centroids)

        # 4. 每列内按 y 排序
        for col_id in col_groups:
            col_groups[col_id].sort(key=lambda b: b["bbox"][1])

        # 5. 构建阅读顺序：(page, col, y)
        result = []
        for col_id in sorted(col_groups.keys()):
            for box in col_groups[col_id]:
                box["page_num"] = page_num
                result.append(box)

        return result

    def merge_lines(
        self,
        words: list[dict],
        page_height: float = 0,
    ) -> list[dict]:
        """将单词级别的 boxes 合并为行。

        水平合并：同一行内 x 坐标相邻的 box 合并为一行。

        Args:
            words: [{"text": str, "x0": float, "top": float, "bottom": float}, ...]
            page_height: 页面高度

        Returns:
            合并后的行列表
        """
        if not words:
            return []

        # 按 y 坐标分组为行
        sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
        lines = []
        current_line = [sorted_words[0]]

        for w in sorted_words[1:]:
            prev = current_line[-1]
            # 判断是否属于同一行（y 坐标重叠）
            if abs(w["top"] - prev["top"]) < 5:  # 5pt 容差
                current_line.append(w)
            else:
                lines.append(current_line)
                current_line = [w]

        lines.append(current_line)

        # 每行从左到右排列并合并文本
        merged = []
        for line_words in lines:
            sorted_line = sorted(line_words, key=lambda w: w["x0"])
            text = " ".join(w["text"] for w in sorted_line)
            merged.append({
                "text": text,
                "x0": min(w["x0"] for w in sorted_line),
                "top": sorted_line[0]["top"],
                "bottom": sorted_line[-1]["bottom"],
            })

        return merged


def _detect_columns(x0_coords: np.ndarray, max_cols: int = 4) -> tuple[int, np.ndarray | None, np.ndarray | None]:
    """使用 KMeans + Silhouette Score 检测最佳列数。

    Returns:
        (n_cols, labels, centroids_sorted)
        - n_cols: 检测到的列数 (1 ~ max_cols)
        - labels: KMeans 聚类标签 (n_samples,)，单列时为 None
        - centroids_sorted: 聚类中心 x 坐标，按升序排列，单列时为 None
    """
    n = len(x0_coords)
    if n < 4:
        return 1, None, None

    max_k = min(max_cols, n - 1)
    if max_k <= 1:
        return 1, None, None

    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score

        best_k = 1
        best_score = -1
        best_labels = None
        best_centroids = None

        for k in range(2, max_k + 1):
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(x0_coords)

            if len(set(labels)) < 2:
                continue

            score = silhouette_score(x0_coords, labels)
            if score > best_score:
                best_score = score
                best_k = k
                best_labels = labels
                best_centroids = kmeans.cluster_centers_.flatten()

        # 降低阈值从 0.5 → 0.35，避免密集排版被误判为单列
        if best_score > 0.35 and best_labels is not None and best_centroids is not None:
            # 按聚类中心 x 坐标排序，将 labels 重新映射为从左到右的列号
            centroids = np.asarray(best_centroids)
            centroids_sorted_idx = np.argsort(centroids)
            centroids_sorted = centroids[centroids_sorted_idx]
            # 重映射 labels: 原 label → 从左到右的列号 0,1,2...
            label_map = {old: new for new, old in enumerate(centroids_sorted_idx)}
            remapped_labels = np.array([label_map[l] for l in best_labels])
            return best_k, remapped_labels, centroids_sorted

        return 1, None, None

    except ImportError:
        # sklearn 不可用 → 简单启发式（无 labels）
        x0_range = np.max(x0_coords) - np.min(x0_coords)
        if x0_range > 200:  # 页面宽度跨度 > 200pt
            q1, q2, _ = np.percentile(x0_coords.flatten(), [25, 50, 75])
            if (q2 - q1) > 50:  # 明显分离
                return 2, None, None
        return 1, None, None


def _group_by_columns(
    boxes: list[dict],
    n_cols: int,
    labels: np.ndarray | None = None,
    centroids: np.ndarray | None = None,
) -> dict[int, list[dict]]:
    """将文字块按列分组。

    优先使用 KMeans labels 精确分组；无 labels 时用 centroids
    做最近邻分配；均不可用时降级为等距分箱。

    Args:
        boxes: 文字块列表
        n_cols: 检测到的列数
        labels: KMeans 聚类标签（与 boxes 一一对应），可为 None
        centroids: 聚类中心 x 坐标（按列号升序），可为 None

    Returns:
        {col_id: [box, ...]}
    """
    if n_cols <= 1:
        return {0: boxes}

    # 方案 A: 有 labels → 直接按 label 分组（最精确）
    if labels is not None and len(labels) == len(boxes):
        groups = {}
        for box, label in zip(boxes, labels):
            col = int(label)
            groups.setdefault(col, []).append(box)
        return groups

    # 方案 B: 有 centroids → 最近邻分配（Voronoi 划分）
    if centroids is not None and len(centroids) == n_cols:
        groups = {}
        for box in boxes:
            x0 = box["bbox"][0]
            col = int(np.argmin(np.abs(centroids - x0)))
            groups.setdefault(col, []).append(box)
        return groups

    # 方案 C: 降级 → 等距分箱
    sorted_boxes = sorted(boxes, key=lambda b: b["bbox"][0])
    x0s = [b["bbox"][0] for b in sorted_boxes]
    x_min, x_max = min(x0s), max(x0s)
    bin_width = (x_max - x_min) / n_cols

    groups = {}
    for box in sorted_boxes:
        x0 = box["bbox"][0]
        col = int((x0 - x_min) / bin_width)
        col = min(col, n_cols - 1)
        groups.setdefault(col, []).append(box)

    return groups
