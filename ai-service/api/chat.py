"""POST /v1/chat — RAG 问答接口（SSE 流式响应）。

处理链路 (v5):
    1. 校验 filter_params（安全红线：缺失返回 400）
    2. RetrievalOrchestrator.retrieve() — 混合检索 + 意图路由 + Query 改写 + Reranker
    3. 上下文组装（system_prompt + summary + Java 转发的 history + 检索结果）
    4. LLM 流式生成 → SSE 逐 token 返回
    5. CitationInserter 引用标注（在 orchestrator 内部完成）
    6. 异步触发摘要更新

降级: 当 RetrievalOrchestrator 不可用时，回退到旧版纯向量检索。
"""

import asyncio
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from common import get_logger
from common.exceptions import MissingFiltersError
from llm.base import BaseLLM
from llm.prompts.rag import RAG_SYSTEM_PROMPT
from models.chat import ChatRequest, ChatTokenChunk, ChatMessage
from models.retrieval import SearchRequest
from retrieval.embedding import EmbeddingWrapper
from retrieval.vector_store import PGVectorClient
from retrieval.orchestrator import RetrievalOrchestrator
from core.context.history_manager import HistoryManager
from core.context.context_assembler import ContextAssembler
from core.context.summary_engine import SummaryEngine
from .dependencies import (
    get_llm, get_embedding_wrapper, get_pgvector_client,
    get_history_manager, get_context_assembler, get_summary_engine,
)

logger = get_logger(__name__)

router = APIRouter()


@router.post("/v1/chat")
async def chat(
    request: ChatRequest,
    fastapi_request: Request,
    llm: BaseLLM = Depends(get_llm),
    embedding_wrapper: EmbeddingWrapper = Depends(get_embedding_wrapper),
    pgvector_client: PGVectorClient = Depends(get_pgvector_client),
    history_manager: HistoryManager = Depends(get_history_manager),
    context_assembler: ContextAssembler = Depends(get_context_assembler),
    summary_engine: SummaryEngine = Depends(get_summary_engine),
):
    """RAG 问答接口，SSE 流式响应。

    Java 调用方必须传入 filters，否则返回 400（安全红线）。
    消息历史由 Java 通过 history_messages 字段转发，Python 直接使用。
    消息持久化由 Java 独占负责，Python 不写业务数据库。
    """

    # ---- 安全红线：filter_params 强制校验 ----
    if not request.filter_params:
        raise MissingFiltersError()

    conversation_id = request.conversation_id
    logger.info(f"收到问答请求: conv={conversation_id}, query={request.query[:50]}..., "
                f"history_size={len(request.history_messages)}")

    # ---- 1. 检索（v5 混合检索 或 旧版纯向量检索降级） ----
    retrieval_orch: RetrievalOrchestrator | None = getattr(
        fastapi_request.app.state, "retrieval_orchestrator", None
    )

    # 保存 ScoredChunk 列表用于引用标注
    scored_chunks = []

    if retrieval_orch is not None:
        # v5 混合检索链路：QueryRewriter → IntentRouter → HybridSearch → Reranker
        from retrieval.models import RetrievalContext
        ctx: RetrievalContext = await retrieval_orch.retrieve(
            query=request.query,
            kb_ids=request.filter_params.kb_ids,
            history_messages=[m.model_dump() for m in request.history_messages],
            top_k=request.top_k,
        )
        scored_chunks = ctx.chunks  # 保留 ScoredChunk 引用（含 _embedding）
        search_results = [
            {
                "source_file": c.source_file,
                "score": c.score,
                "chunk_text": c.content,
            }
            for c in scored_chunks
        ]
        logger.info(
            f"v5 混合检索完成: intent={ctx.intent}, chunks={len(scored_chunks)}, "
            f"keywords={ctx.keywords}"
        )
    else:
        # 降级: 旧版纯向量检索
        query_vector = await embedding_wrapper.embed_query(request.query)
        pg_results = await pgvector_client.search(SearchRequest(
            query_vector=query_vector,
            filter_params=request.filter_params,
            top_k=request.top_k,
        ))
        search_results = [
            {
                "source_file": r.source_file,
                "score": r.score,
                "chunk_text": r.chunk_text,
            }
            for r in pg_results
        ]

    # ---- 2. 构建检索上下文 + 组装完整上下文 ----
    system_prompt = RAG_SYSTEM_PROMPT.render(
        documents=search_results,
        summary="",
    )

    messages, _ = await context_assembler.assemble(
        conversation_id=conversation_id,
        query=request.query,
        search_results=search_results,
        system_prompt=system_prompt,
        history_messages=request.history_messages,  # Java 转发的历史消息
    )

    # ---- 3. 分离 context 消息和 history 消息 ----
    context_msgs = [ChatMessage(role=m["role"], content=m["content"])
                    for m in messages if m["role"] in ("system", "context")]
    history_msgs = [ChatMessage(role=m["role"], content=m["content"])
                    for m in messages if m["role"] in ("user", "assistant")]

    # ---- 4. 流式生成 + SSE 返回 ----
    # 总超时 110 秒（略小于前端 / 后端的 120 秒，给透传留缓冲）
    STREAM_TOTAL_TIMEOUT = 110.0

    async def event_stream():
        full_response = ""
        final_sources = []
        start_time = time.time()

        try:
            # asyncio.timeout 保护：避免 LLM 流式调用无限挂起
            async with asyncio.timeout(STREAM_TOTAL_TIMEOUT):
                async for token in llm.stream_content(
                    prompt=request.query,
                    context=context_msgs,
                    history=history_msgs,
                ):
                    full_response += token
                    chunk = ChatTokenChunk(token=token, done=False)
                    yield f"data: {chunk.model_dump_json()}\n\n"

            # ★ v5: 引用标注 — 答案 vs 检索 chunks 相似度匹配
            cited_text = full_response
            citations = []
            if scored_chunks and retrieval_orch is not None and retrieval_orch._citation is not None:
                try:
                    cited_text, citations = await retrieval_orch._citation.insert(
                        full_response, scored_chunks
                    )
                    if citations:
                        logger.info(f"引用标注完成: {len(citations)} 处引用")
                except Exception as e:
                    logger.warning(f"引用标注失败: {e}")

            # 末尾事件：done=true，附带 sources + citations
            final_sources = [
                {
                    "filename": r.get("source_file", "") if isinstance(r, dict) else r.source_file,
                    "chunk_text": (r.get("chunk_text", "") if isinstance(r, dict) else r.chunk_text)[:200],
                    "score": r.get("score", 0) if isinstance(r, dict) else r.score,
                }
                for r in search_results
            ]
            final_chunk = ChatTokenChunk(token="", done=True, sources=final_sources, citations=citations if citations else None)
            yield f"data: {final_chunk.model_dump_json()}\n\n"

            elapsed = time.time() - start_time
            logger.info(f"问答完成: conv={conversation_id}, tokens={len(full_response)}, 耗时={elapsed:.2f}s")

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error(
                f"LLM 流式生成超时: conv={conversation_id}, "
                f"已生成 tokens={len(full_response)}, 耗时={elapsed:.2f}s"
            )
            error_chunk = ChatTokenChunk(token="", done=True, sources=[])
            yield f"data: {error_chunk.model_dump_json()}\n\n"

        except Exception as e:
            logger.error(f"LLM 流式生成失败: {e}")
            error_chunk = ChatTokenChunk(token="", done=True, sources=[])
            yield f"data: {error_chunk.model_dump_json()}\n\n"

        finally:
            # 缓存消息到 Redis（可选优化）并异步触发摘要更新
            try:
                await history_manager.cache_message(conversation_id, "user", request.query)
                if full_response:
                    await history_manager.cache_message(conversation_id, "assistant", full_response)
            except Exception as e:
                logger.warning(f"Redis 消息缓存失败（非致命）: {e}")

            # 异步触发摘要更新
            asyncio.create_task(
                summary_engine.maybe_update_summary(conversation_id)
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
