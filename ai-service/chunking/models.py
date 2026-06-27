"""分块数据模型 — Chunk 和 ChunkRelation。

Chunk 是 retrieval/ 模块的核心索引单位，携带：
    - 主文本 (content) 和加权文本 (content_with_weight)
    - 标题信息 (title) 和类型 (chunk_type)
    - 位置元数据 (page_range)
    - 权限/Business 元数据 (metadata)
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """文档分块 — ETL 和检索的基本单位。

    每个 Chunk 有确定性 ID（SHA256 of doc_id + chunk_index），
    支持幂等插入和去重。
    """

    id: str                          # SHA256 确定性 ID
    content: str                     # 主文本
    content_with_weight: str = ""    # 关键词加权重复（用于 BM25 增强）
    title: str | None = None         # 所属章节/文档标题
    chunk_type: str = "text"         # text | table | image | title
    page_range: tuple[int, int] | None = None  # (start_page, end_page)
    tokens: int = 0                  # 估算 token 数
    metadata: dict[str, Any] = field(default_factory=dict)  # kb_id, doc_id, 时效...


@dataclass
class ChunkRelation:
    """Chunk 间关系 — 支持父子层级和兄弟顺序。

    用于检索时的父子扩展：
        - 命中子 chunk → 拉入父 chunk 上下文
        - 命中父 chunk → 可选合并子 chunk
    """

    parent_id: str | None = None     # 父 chunk ID（如章节标题 chunk）
    children_ids: list[str] = field(default_factory=list)  # 子 chunk IDs
    prev_id: str | None = None       # 前一个兄弟 chunk
    next_id: str | None = None       # 后一个兄弟 chunk
