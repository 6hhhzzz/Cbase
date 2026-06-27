"""语义分块引擎 — 将 ParsedDocument 拆分为适合索引的 Chunk。

借鉴 RAGFlow 的分块策略：
    - TokenChunker：token 感知切分 + 分隔符优先级 + 重叠
    - TitleChunker：标题层级切分
    - merge_chunks：短 chunk 贪婪合并（naive_merge 移植）
    - ContextEnricher：表格/图片上下文注入
"""

from .models import Chunk, ChunkRelation
from .base import BaseChunker
from .token_chunker import TokenChunker
from .title_chunker import TitleChunker
from .merge import merge_chunks
from .enrich import ContextEnricher
from .orchestrator import ChunkOrchestrator

__all__ = [
    "Chunk",
    "ChunkRelation",
    "BaseChunker",
    "TokenChunker",
    "TitleChunker",
    "merge_chunks",
    "ContextEnricher",
    "ChunkOrchestrator",
]
