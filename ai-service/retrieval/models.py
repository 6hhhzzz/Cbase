"""检索扩展数据模型 — 混合检索、意图路由、Query 改写、引用标注。

与 models/retrieval.py（SearchRequest/SearchResult/FilterParams）互补，
新增混合检索流程中的中间数据结构。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScoredChunk:
    """带分数的检索结果 chunk — 混合检索的中间数据。"""

    chunk_id: str
    content: str
    score: float = 0.0
    chunk_type: str = "text"           # text | table | image | title
    title: str | None = None
    source_file: str = ""
    page_range: tuple[int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentResult:
    """意图路由结果。"""

    intent: str                        # factoid | summary | compare | howto
    method: str = "rule"               # rule | llm
    top_k: int = 5
    sub_queries: list[str] = field(default_factory=list)  # compare 意图拆解


@dataclass
class RewriteResult:
    """Query 改写结果。"""

    rewritten_query: str               # 改写后的查询
    keywords: list[str] = field(default_factory=list)  # 核心关键词
    skipped: bool = False              # 是否跳过了改写


@dataclass
class RetrievalContext:
    """组装后的检索上下文 — 传给 LLM 的最终输入。"""

    query: str
    chunks: list[ScoredChunk]
    parent_chunks: list[ScoredChunk] = field(default_factory=list)
    toc_sections: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)  # [{chunk_id, sentence_idx, score}]
    intent: str = "factoid"
    keywords: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        """粗略估算上下文总 token 数。"""
        from common.utils import estimate_tokens
        texts = [c.content for c in self.chunks]
        texts.extend(c.content for c in self.parent_chunks)
        texts.extend(self.toc_sections)
        texts.append(self.query)
        return estimate_tokens("\n".join(texts))
