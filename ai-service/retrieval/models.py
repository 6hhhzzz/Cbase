"""检索扩展数据模型 — 混合检索、意图路由、Query 改写、引用标注。

与 models/retrieval.py（SearchRequest/SearchResult/FilterParams）互补，
新增混合检索流程中的中间数据结构。

v11: IntentResult → QueryPlan（DAG 拆解 + HyDE 标记），SubQuery 新增。
v12: SubQuery 升级 — 三维提取（实体+推理+约束），UpstreamContext 新增。
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


# ---- v12: 上游上下文传递 ----

@dataclass
class UpstreamContext:
    """从上游检索结果中提取的三维上下文，传递给下游子查询。

    维度一（entities）：结构化实体 → 填入 query_template 做精准检索
    维度二（reasoning_state）：推理中间态 → 注入下游检索/生成做逻辑上下文
    维度三（filters）：元数据约束 → 转化为下游检索的 SQL WHERE 条件
    """

    entities: dict[str, str] = field(default_factory=dict)
    #   {"product_name": "Gateway-X", "version": "v2.3.1"}

    reasoning_state: str = ""
    #   "Gateway-X 采用异步非阻塞架构，并发上限受限于底层线程池大小"

    filters: dict[str, Any] = field(default_factory=dict)
    #   {"valid_after": "2024-07-01", "doc_type": "技术规范"}


# ---- v12: DAG 查询计划 ----

@dataclass
class SubQuery:
    """DAG 子查询节点 — QueryPlanner 输出。

    每个 SubQuery 是一个独立可检索的原子查询，
    通过 depends_on 表达与其他子查询的依赖关系。
    """

    id: str                                    # 唯一标识，如 "q1"
    query: str = ""                            # 最终执行时的查询（模板填充后）
    query_template: str = ""                   # 模板（含 {{extracted.xxx}} 占位符，串行依赖时由 LLM 生成）
    depends_on: list[str] = field(default_factory=list)  # 依赖的 sub_query id
    purpose: str = ""                          # 目的说明（供 LLM 生成时理解上下文）
    hyde: bool = False                         # 是否需要 HyDE 桥接 Dense 检索
    needs_context: bool = False                # 串行依赖时是否需要前一步检索结果

    # ---- 上游上下文三维提取指令 ----
    extract_entities: list[dict] | None = None      # 实体提取列表
    #   [{"key": "product_name", "description": "产品/组件名称"}]
    extract_reasoning: str | None = None             # 推理中间态提取指令
    #   "从上游结果总结当前的技术架构决策和约束条件"
    extract_filters: list[str] | None = None         # 元数据约束字段列表
    #   ["valid_after", "doc_type"]


@dataclass
class QueryPlan:
    """查询计划 — QueryPlanner 的输出，替代旧 IntentResult。

    complexity=simple: rewritten_query 单次检索（向后兼容旧路径）
    complexity=complex: sub_queries DAG 多路检索
    """

    complexity: str = "simple"                 # simple | complex
    rewritten_query: str = ""                  # 消解指代后的查询（两种 complexity 都用）
    keywords: list[str] = field(default_factory=list)  # BM25 关键词
    sub_queries: list[SubQuery] = field(default_factory=list)
    method: str = "llm"                        # llm | fallback
    top_k: int = 5
    intent: str = "factoid"                    # 向后兼容旧 IntentResult


# ---- 向后兼容别名 ----

# IntentResult 保留为 QueryPlan 的别名，不破坏现有引用
IntentResult = QueryPlan


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
    reranked_count: int = 0     # reranker 输出的候选总数（过滤前）
    filtered_count: int = 0     # 因置信度不足被过滤的数量
    recall_stats: dict = field(default_factory=dict)  # {dense_hits, bm25_hits, splade_hits}
    timings: dict = field(default_factory=dict)  # {dense_ms, bm25_ms, splade_ms, rerank_ms, ...}
    # v11: 子查询分组信息
    sub_query_groups: dict[str, list[str]] = field(default_factory=dict)  # sub_query.id → chunk_ids
    # v12: 上游上下文（推理链中间结果）
    upstream_contexts: dict[str, UpstreamContext] = field(default_factory=dict)  # sub_query.id → UpstreamContext
    # v12: 链路追踪详情 — 各阶段按 key 填充，由 feedback.py 序列化入库
    trace_detail: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        """粗略估算上下文总 token 数。"""
        from common.utils import estimate_tokens
        texts = [c.content for c in self.chunks]
        texts.extend(c.content for c in self.parent_chunks)
        texts.extend(self.toc_sections)
        texts.append(self.query)
        return estimate_tokens("\n".join(texts))
