"""RetrievalOrchestrator — 检索全流程编排器。

流程：
    Query + History
      → [1] QueryRewriter（短路 → 改写 + 关键词）
      → [2] IntentRouter（规则 → LLM 分类）
      → [3] HybridSearch（Dense ∥ Sparse → RRF 融合）
      → [4] Reranker（Cross-Encoder → LLM 降级）
      → [5] 上下文组装
      → [6] LLM 生成
      → [7] CitationInserter（引用标注）
"""

from common import get_logger
from typing import Any
from llm.base import BaseLLM
from llm import BaseEmbedding
from .hybrid_search import HybridSearch
from .reranker import Reranker
from .query_rewriter import QueryRewriter
from .intent_router import IntentRouter
from .citation import CitationInserter
from .models import RetrievalContext, ScoredChunk, RewriteResult, IntentResult

logger = get_logger(__name__)

# Token 预算保护
PARENT_MAX_TOKENS = 1000
CHAPTER_BUDGET_TOKENS = 800

# ═══════════════════════════════════════════════════════════
# HyDE 触发判定 — 列举/抽象查询术语桥接
# ═══════════════════════════════════════════════════════════

_LIST_PATTERNS = ["包含哪些", "包含哪几", "有哪些", "有哪几", "列出", "列举",
                  "几个方面", "几个层次", "哪几个", "哪六", "哪三", "哪五",
                  "分别是", "分别是什么", "分别有"]

_ABSTRACT_MARKERS = ["价值观", "文化", "原则", "理念", "精神", "准则"]


def _should_use_hyde(query: str, keywords: list[str] | None) -> bool:
    """简单查询是否需要 HyDE 桥接术语差异。"""
    keywords = keywords or []
    if any(p in query for p in _LIST_PATTERNS):
        return True
    has_abstract = any(m in query for m in _ABSTRACT_MARKERS)
    weak_keywords = len(keywords) < 3 or all(len(kw) <= 2 for kw in keywords)
    if has_abstract and weak_keywords:
        return True
    return False


class RetrievalOrchestrator:
    """检索编排器 — 全流程入口。

    用法::

        orchestrator = RetrievalOrchestrator(
            hybrid_search=hybrid_search,
            reranker=reranker,
            rewriter=rewriter,
            intent_router=router,
            citation=citation,
            llm=llm,
        )
        response = await orchestrator.query(
            query="什么是xxx",
            kb_ids=["kb_1"],
            history_messages=[...],
        )
    """

    def __init__(
        self,
        hybrid_search: HybridSearch,
        reranker: Reranker,
        llm: BaseLLM,
        embedding: BaseEmbedding,
        rewriter: QueryRewriter | None = None,
        intent_router: IntentRouter | None = None,
        citation: CitationInserter | None = None,
        query_planner: Any = None,
        query_preprocessor: Any = None,
        critic: Any = None,
        tracer: Any = None,
        slm: Any = None,
    ):
        self._hybrid_search = hybrid_search
        self._reranker = reranker
        self._llm = llm
        self._rewriter = rewriter
        self._intent_router = intent_router
        self._citation = citation or CitationInserter(embedding)
        self._planner = query_planner
        self._preprocessor = query_preprocessor
        self._critic = critic
        self._tracer = tracer
        self._slm = slm or llm

    async def execute(
        self,
        query: str,
        kb_ids: list[str],
        keywords: list[str] | None = None,
        top_k: int = 10,
        sub_queries: list[str] | None = None,
    ) -> RetrievalContext:
        """纯检索执行层 — HybridSearch → Reranker（共享，两种场景通用）。

        不关心 query 怎么来的（是 QueryRewriter 改写的还是 Agent 构造的）。
        只做机械的检索执行。

        Args:
            query: 搜索查询
            kb_ids: 权限过滤 kb_id 列表
            keywords: BM25 稀疏检索用的关键词（可选，为空时仅 jieba 分词降级）
            top_k: 期望结果数
            sub_queries: 对比意图的子查询（可选）

        Returns:
            RetrievalContext（chunks + 元数据），不包含 intent 信息
        """
        _keywords = keywords or []

        # ---- HybridSearch ----
        all_chunks: list[ScoredChunk] = []

        if sub_queries:
            for sub_q in sub_queries:
                sub_chunks = await self._hybrid_search.search(
                    sub_q, kb_ids, top_k, _keywords
                )
                all_chunks.extend(sub_chunks)
            # 去重
            seen: set[str] = set()
            unique_chunks: list[ScoredChunk] = []
            for c in all_chunks:
                if c.chunk_id not in seen:
                    seen.add(c.chunk_id)
                    unique_chunks.append(c)
            all_chunks = unique_chunks
        else:
            # ★ HyDE 术语桥接：抽象/列举类查询先生成假答案再搜索
            _search_query = query
            if _should_use_hyde(query, _keywords):
                try:
                    from llm.prompts.hyde import HYDE_PROMPT
                    hyde_response = await self._llm.generate_content(
                        HYDE_PROMPT.render(query=query)
                    )
                    hyde_doc = (
                        hyde_response.content
                        if hasattr(hyde_response, "content")
                        else str(hyde_response)
                    )
                    if hyde_doc and len(hyde_doc.strip()) > 20:
                        _search_query = hyde_doc.strip()
                        logger.info(f"HyDE 桥接: '{query[:40]}' → 假答案搜索")
                except Exception as e:
                    logger.warning(f"HyDE 生成失败: {e}")

            all_chunks = await self._hybrid_search.search(
                _search_query, kb_ids, top_k * 2, _keywords
            )

        if not all_chunks:
            logger.warning(f"检索无结果: query='{query[:50]}'")
            return RetrievalContext(query=query, chunks=[], keywords=_keywords)

        # ---- Reranker ----
        reranked = await self._reranker.rerank(query, all_chunks, top_n=top_k)

        logger.info(
            f"检索执行完成: query='{query[:50]}', "
            f"candidates={len(all_chunks)}, returned={len(reranked)}"
        )

        return RetrievalContext(
            query=query,
            chunks=reranked,
            keywords=_keywords,
        )

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str],
        history_messages: list[dict] | None = None,
        top_k: int | None = None,
        trace_ctx: Any = None,
    ) -> RetrievalContext:
        """执行完整检索流程 — Web Chat 场景（含查询准备 + 检索执行）。

        查询准备: QueryRewriter（消解指代） → IntentRouter（意图路由）
        检索执行: 委托给 execute()

        Args:
            query: 用户查询（可能含指代词、省略，依赖历史补全）
            kb_ids: 权限过滤 kb_id 列表
            history_messages: 对话历史
            top_k: 期望结果数（None 时由 IntentRouter 决定）

        Returns:
            RetrievalContext（chunks + 元数据 + intent）
        """
        history = history_messages or []
        keywords: list[str] = []

        # ---- Web Chat 查询准备: [1] QueryRewriter ----
        rewritten_query = query
        if self._rewriter and self._rewriter.should_rewrite(query, len(history)):
            rewrite_result: RewriteResult = await self._rewriter.rewrite(query, history)
            if not rewrite_result.skipped:
                rewritten_query = rewrite_result.rewritten_query
                keywords = rewrite_result.keywords
                logger.info(f"Query 改写: '{query[:50]}' → '{rewritten_query[:50]}'")

        # ---- Web Chat 查询准备: [2] IntentRouter ----
        intent_result: IntentResult = IntentResult(intent="factoid")
        if self._intent_router:
            intent_result = await self._intent_router.route(rewritten_query)

        effective_top_k = top_k or intent_result.top_k

        # ---- 子查询 ----
        sub_queries = intent_result.sub_queries if intent_result.intent == "compare" else None

        # ---- 检索执行（委托给共享层） ----
        ctx = await self.execute(
            query=rewritten_query,
            kb_ids=kb_ids,
            keywords=keywords,
            top_k=effective_top_k,
            sub_queries=sub_queries,
        )

        # 附加 intent 信息
        ctx.intent = intent_result.intent

        return ctx

    async def query(
        self,
        query: str,
        kb_ids: list[str],
        history_messages: list[dict] | None = None,
        top_k: int | None = None,
        system_prompt: str | None = None,
    ) -> dict:
        """执行完整 RAG 问答流程。

        Args:
            query: 用户查询
            kb_ids: 权限过滤 kb_id 列表
            history_messages: 对话历史
            top_k: 期望结果数
            system_prompt: 自定义 system prompt

        Returns:
            {
                "answer": str,          # 带引用的答案
                "sources": list[dict],  # 引用来源
                "citations": list[dict],# 引用详情
                "intent": str,          # 意图
                "keywords": list[str],  # 关键词
            }
        """
        # 检索
        ctx = await self.retrieve(query, kb_ids, history_messages, top_k)

        if not ctx.chunks:
            return {
                "answer": "抱歉，在知识库中没有找到相关信息。",
                "sources": [],
                "citations": [],
                "intent": ctx.intent,
                "keywords": ctx.keywords,
            }

        # 组装检索文本
        from llm.prompts.rag import RAG_SYSTEM_PROMPT

        documents = [
            {
                "source_file": c.source_file,
                "score": c.score,
                "chunk_text": c.content,
            }
            for c in ctx.chunks
        ]

        prompt = RAG_SYSTEM_PROMPT.render(documents=documents, summary="")

        if system_prompt:
            prompt = system_prompt + "\n\n" + prompt

        # LLM 生成
        response_wrapper = await self._llm.generate_content(prompt)
        answer = (
            response_wrapper.content
            if hasattr(response_wrapper, "content")
            else str(response_wrapper)
        )

        # 引用标注
        cited_answer, citations = await self._citation.insert(answer, ctx.chunks)

        sources = [
            {
                "source_file": c.source_file,
                "score": round(c.score, 3),
                "snippet": c.content[:200],
            }
            for c in ctx.chunks
        ]

        logger.info(f"RAG 完成: query='{query[:50]}', chunks={len(ctx.chunks)}, "
                      f"citations={len(citations)}, intent={ctx.intent}")

        return {
            "answer": cited_answer,
            "sources": sources,
            "citations": citations,
            "intent": ctx.intent,
            "keywords": ctx.keywords,
        }
