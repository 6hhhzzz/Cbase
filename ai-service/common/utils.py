"""通用工具函数。"""

import hashlib
import time
from uuid import uuid4


def generate_doc_id() -> str:
    """生成文档 ID（UUID v4）。"""
    return str(uuid4())


def generate_chunk_id(doc_id: str, chunk_index: int) -> str:
    """生成 Chunk ID（确定性，便于去重）。

    Args:
        doc_id: 文档 ID
        chunk_index: Chunk 序号

    Returns:
        64 字符的 Hex 字符串，适合作为 PostgreSQL VARCHAR 主键
    """
    raw = f"{doc_id}:{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()


def estimate_tokens(text: str) -> int:
    """粗略估算文本的 token 数量。

    适用于中英文混合文本的近似估算：中文字符约 1.5 tokens/字，英文单词约 1.3 tokens/词。
    这里使用简化公式：字符数 / 2，适合中英文混合场景。

    Args:
        text: 任意文本

    Returns:
        估算的 token 数（最小值 1）
    """
    return max(1, len(text) // 2)


def current_timestamp_ms() -> int:
    """返回当前 Unix 毫秒时间戳。"""
    return int(time.time() * 1000)


def truncate_text(text: str, max_chars: int = 200) -> str:
    """截断文本到指定字符数，超出部分用 ... 表示。

    Args:
        text: 原始文本
        max_chars: 最大字符数

    Returns:
        截断后的文本
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def tokenize_chinese(text: str) -> str:
    """中文分词，返回空格分隔的词串，用于 PostgreSQL tsvector。

    jieba 可用时使用 jieba 分词；否则降级逐字拆分（字符间插空格）。

    Args:
        text: 待分词文本

    Returns:
        空格分隔的词串，如 "项目 背景 介绍 2024 年度 报告"
    """
    try:
        import jieba
        words = jieba.cut(text)
        return " ".join(w.strip() for w in words if w.strip())
    except ImportError:
        import re
        return re.sub(r'([一-鿿])', r' \1 ', text).strip()
