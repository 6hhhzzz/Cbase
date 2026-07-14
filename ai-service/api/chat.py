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
import json
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
from retrieval.trace_context import TraceContext
from core.context.history_manager import HistoryManager
from core.context.context_assembler import ContextAssembler
from core.context.summary_engine import SummaryEngine
from .chat_errors import get_error_message
from .dependencies import (
    get_llm, get_embedding_wrapper, get_pgvector_client,
    get_history_manager, get_context_assembler, get_summary_engine,
)

logger = get_logger(__name__)

router = APIRouter()


async def _save_trace_and_judge(tracer, trace_data: dict, query: str,
                                 answer: str, chunks: list,
                                 do_judge: bool = False) -> None:
    """异步保存 trace，可选触发 Judge 评估（不阻塞主流程）。"""
    try:
        await tracer.save_trace(trace_data)
        if do_judge:
            # 延迟导入避免循环依赖
            # Judge 通过 app.state 获取，这里简单跳过（采样时记录日志）
            logger.debug(f"采样 trace 已落库: {trace_data['trace_id']}，Judge 评估待触发")
    except Exception as e:
        logger.warning(f"异步保存 trace 失败: {e}")


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

    # ── TraceContext: 统一追踪（替代旧的 _tracer 猴子补丁）──
    trace_ctx = TraceContext(
        query=request.query,
        source="web_chat",
        metadata={
            "kb_ids": request.filter_params.kb_ids,
            "top_k": request.top_k,
            "history_len": len(request.history_messages),
            "conversation_id": str(conversation_id) if conversation_id else "",
        },
    )

    # ── Langfuse: 初始化 tracer + 创建 trace（保留向后兼容）──
    _langfuse = None
    _langfuse_trace = None
    try:
        from observability.langfuse_tracer import LangfuseTracer
        _langfuse = LangfuseTracer()
        if _langfuse._enabled:
            _langfuse_trace = _langfuse.trace(
                name=request.query[:200],
                input_data=request.query,
                user_id=(str(request.filter_params.kb_ids[0]) if request.filter_params.kb_ids else ""),
                session_id=str(conversation_id) if conversation_id else "",
                metadata={
                    "kb_ids": request.filter_params.kb_ids,
                    "top_k": request.top_k,
                    "history_len": len(request.history_messages),
                },
            )
    except Exception:
        pass

    # ---- 0. 闲聊/寒暄短路 — 不检索文档 ----
    from retrieval.orchestrator import _is_chitchat
    is_chitchat = _is_chitchat(request.query)

    # ---- 1. 检索（v5 混合检索 或 旧版纯向量检索降级） ----
    retrieval_orch: RetrievalOrchestrator | None = getattr(
        fastapi_request.app.state, "retrieval_orchestrator", None
    )

    # 保存 ScoredChunk 列表用于引用标注
    scored_chunks = []
    ctx = None  # type: ignore  # 闲聊时保持 None

    if is_chitchat:
        logger.info(f"闲聊检测: '{request.query}' → 跳过检索，直接 LLM 回复")  # type: ignore
        search_results = []
    elif retrieval_orch is not None:
        # v5 混合检索链路：QueryRewriter → IntentRouter → HybridSearch → Reranker
        ctx = await retrieval_orch.retrieve(  # type: ignore
            query=request.query,
            kb_ids=request.filter_params.kb_ids,
            history_messages=[m.model_dump() for m in request.history_messages],
            top_k=request.top_k,
            trace_ctx=trace_ctx,
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

    _t_assembly_start = time.monotonic()
    messages, _ = await context_assembler.assemble(
        conversation_id=conversation_id,
        query=request.query,
        search_results=search_results,
        system_prompt=system_prompt,
        history_messages=request.history_messages,
    )
    _t_assembly_ms = int((time.monotonic() - _t_assembly_start) * 1000)

    # trace: 上下文组装
    assembly_detail = {
        "chunks_available": len(search_results),
        "chunks_displayed": len(search_results),
        "context_snippet": system_prompt[:500] if system_prompt else "",
        "total_tokens": sum(len(m.get("content", "")) for m in messages) // 4,  # 粗略估算
        "assembly_ms": _t_assembly_ms,
    }

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
        citations = []
        start_time = time.time()
        error_occurred = False
        _gen_first_token = False
        _gen_first_token_ms = 0
        _gen_error_type = None

        try:
            # asyncio.timeout 保护：避免 LLM 流式调用无限挂起
            _gen_start = time.monotonic()
            async with asyncio.timeout(STREAM_TOTAL_TIMEOUT):
                async for token in llm.stream_content(
                    prompt=request.query,
                    context=context_msgs,
                    history=history_msgs,
                ):
                    if not _gen_first_token:
                        _gen_first_token_ms = int((time.monotonic() - _gen_start) * 1000)
                        _gen_first_token = True
                    full_response += token
                    chunk = ChatTokenChunk(token=token, done=False)
                    yield f"data: {chunk.model_dump_json()}\n\n"
            _gen_ms = int((time.monotonic() - _gen_start) * 1000)

            # ★ v5: 引用标注 — 答案 vs 检索 chunks 相似度匹配
            cited_text = full_response
            citations = []
            _t_citation_start = time.monotonic()
            if scored_chunks and retrieval_orch is not None and retrieval_orch._citation is not None:
                try:
                    cited_text, citations = await retrieval_orch._citation.insert(
                        full_response, scored_chunks
                    )
                    if citations:
                        logger.info(f"引用标注完成: {len(citations)} 处引用")
                except Exception as e:
                    logger.warning(f"引用标注失败: {e}")
            _citation_ms = int((time.monotonic() - _t_citation_start) * 1000)

            # ---- TraceContext: 记录生成 + 引用 + 组装节点 ----
            trace_ctx.span("context_assembly", input={
                "chunks_available": len(search_results),
                "history_len": len(request.history_messages),
            }).finish(output={
                "context_tokens": sum(len(m.get("content", "")) for m in messages) // 4,
                "assembly_ms": _t_assembly_ms,
            })

            trace_ctx.span("llm_generation", input={
                "model": getattr(llm, 'get_model_name', lambda: 'unknown')(),
                "messages_count": len(messages),
            }).finish(output={
                "first_token_ms": _gen_first_token_ms,
                "generation_ms": _gen_ms,
                "response_length": len(full_response),
                "error_type": None,
            })

            trace_ctx.span("citation", input={
                "response_length": len(full_response),
                "chunks_count": len(scored_chunks),
            }).finish(output={
                "citations_count": len(citations) if citations else 0,
                "unique_chunks_cited": len(set(c.get("chunk_id", "") for c in (citations or []))),
                "citation_ms": _citation_ms,
            })

            # Judge span 预创建（确保出现在 Langfuse 树中）
            judge_h = trace_ctx.span("judge", input={
                "query": request.query,
                "answer_length": len(full_response),
                "chunks_count": len(scored_chunks),
            })
            judge_h.finish(output={"status": "pending"})

            # ---- 合并 trace_detail: orchestrator 阶段 + chat 阶段（向后兼容）----
            td = getattr(ctx, 'trace_detail', {}) if ctx else {}
            td["assembly"] = assembly_detail
            td["generation"] = {
                "model": getattr(llm, 'get_model_name', lambda: 'unknown')(),
                "generation_ms": _gen_ms,
                "first_token_ms": _gen_first_token_ms,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "response_snippet": full_response[:500],
                "error_type": None,
            }
            td["citation"] = {
                "total_sentences": len(full_response.split("。")) if full_response else 0,
                "sentences_cited": len(citations) if citations else 0,
                "citations_count": len(citations) if citations else 0,
                "unique_chunks_cited": len(set(c.get("chunk_id", "") for c in (citations or []))),
                "citation_ms": _citation_ms,
            }
            td["critic"] = {"invoked": False, "action": "", "note": "", "critic_ms": 0}

            # ---- 检索质量 Trace 构建 ----
            trace_data = None
            tracer = getattr(fastapi_request.app.state, "tracer", None)
            if tracer is not None and retrieval_orch is not None and ctx is not None:
                try:
                    trace_data = tracer.build_trace(
                        query=request.query,
                        rewritten_query=getattr(ctx, 'query', request.query),
                        kb_ids=request.filter_params.kb_ids,
                        keywords=ctx.keywords if hasattr(ctx, 'keywords') else [],
                        ctx=ctx,
                        recall_stats=getattr(ctx, 'recall_stats', {}),
                        timings={
                            **getattr(ctx, 'timings', {}),
                            "total_ms": int((time.time() - start_time) * 1000),
                        },
                        generated_response=full_response,
                        source="web_chat",
                        session_id=conversation_id,
                        trace_ctx=trace_ctx,
                    )
                    # 始终异步落库（反馈 UPDATE 依赖已存在的 trace 行）
                    # 仅采样时额外触发 Judge 评估（控制成本）
                    _do_judge = tracer.should_sample()
                    if _do_judge:
                        logger.info(f"Trace 采样命中: {trace_data['trace_id']}")
                    asyncio.create_task(_save_trace_and_judge(
                        tracer, trace_data, request.query, full_response,
                        scored_chunks, _do_judge
                    ))
                except Exception as e:
                    logger.warning(f"构建 Trace 失败: {e}")

            # ── TraceContext → Langfuse span 树生成 ──
            if _langfuse is not None and _langfuse._enabled and _langfuse_trace is not None:
                trace_ctx.to_langfuse(_langfuse, _langfuse_trace)

            # ── Langfuse: answer generation + Judge 评分 + flush（保留向后兼容）──
            if _langfuse is not None and _langfuse._enabled and _langfuse_trace is not None:
                # ★ 回填检索路径元数据
                _retrieval_path = "chitchat" if is_chitchat else (
                    "dag" if (ctx and ctx.intent == "complex") else "simple"
                )
                try:
                    _langfuse.update_span(_langfuse_trace, metadata={
                        "retrieval_path": _retrieval_path,
                    })
                except Exception:
                    pass

                try:
                    model_name = getattr(llm, 'get_model_name', lambda: 'unknown')()
                    gen = _langfuse.generation(
                        parent=_langfuse_trace,
                        name="answer",
                        model=model_name,
                        input_data=messages if messages else request.query,
                        metadata={"generation_ms": _gen_ms if '_gen_ms' in dir() else 0},
                    )
                    _langfuse.update_span(gen, output=full_response[:500] if full_response else "")
                    # 回填 trace 的 output（Langfuse UI 的 Output 显示区域）
                    _langfuse.update_span(_langfuse_trace,
                        output=full_response[:500] if full_response else "")
                except Exception:
                    pass
                # ★ Latency 细分指标
                try:
                    _langfuse.score(name="first_token_ms", value=float(_gen_first_token_ms))
                    _langfuse.score(name="generation_ms", value=float(_gen_ms))
                    _langfuse.score(name="total_ms", value=float(int((time.time() - start_time) * 1000)))
                except Exception:
                    pass
                # ★ DAG 额外指标
                if _retrieval_path == "dag":
                    try:
                        dag_info = (ctx.trace_detail or {}).get("retrieval", {}).get("dag", {})
                        if dag_info:
                            _langfuse.score(name="planner_ms",
                                value=float((ctx.trace_detail or {}).get("planner", {}).get("planner_ms", 0)))
                            _langfuse.score(name="wave_count",
                                value=float(dag_info.get("wave_count", 0)))
                            _langfuse.score(name="sub_query_count",
                                value=float(dag_info.get("total_sub_queries", 0)))
                            cb = dag_info.get("circuit_breaker", {})
                            if cb.get("tripped"):
                                _langfuse.score(name="circuit_breaker_tripped", value=1.0,
                                    comment=cb.get("reason", ""))
                    except Exception:
                        pass
                # ★ 先 flush 一波（answer span），控制 trace latency
                try:
                    _langfuse.flush()
                except Exception:
                    pass

                # ★ Judge 评分异步执行：不延长 trace latency
                _lf_trace_id = getattr(_langfuse_trace, 'id', None)
                if _lf_trace_id:
                    async def _judge_and_score():
                        """后台 Judge 评估 + Langfuse 评分。"""
                        try:
                            judge = getattr(fastapi_request.app.state, "judge", None)
                            if judge is None:
                                from retrieval.judge import JudgeEvaluator
                                slm = llm
                                if retrieval_orch is not None and hasattr(retrieval_orch, '_slm'):
                                    slm = retrieval_orch._slm or llm
                                judge = JudgeEvaluator(slm)
                            scores = await judge.evaluate(
                                query=request.query,
                                answer=full_response,
                                chunks=scored_chunks,
                            )
                            # ── TraceContext: 回填预创建的 judge span ──
                            try:
                                judge_h.finish(output={
                                    "faithfulness": scores.get("faithfulness"),
                                    "answer_relevance": scores.get("answer_relevance"),
                                    "context_relevance": scores.get("context_relevance"),
                                    "answer_correctness": scores.get("answer_correctness"),
                                    "judge_model": scores.get("model", ""),
                                    "judge_latency_ms": scores.get("latency_ms", 0),
                                })
                            except Exception:
                                pass
                            if _langfuse._client:
                                for key in ("faithfulness", "answer_relevance", "context_relevance", "answer_correctness"):
                                    val = scores.get(key)
                                    if val is not None:
                                        _langfuse._client.score(
                                            trace_id=_lf_trace_id,
                                            name=key,
                                            value=float(val),
                                        )
                            _langfuse.flush()
                        except Exception:
                            pass
                    asyncio.create_task(_judge_and_score())

            # 末尾事件：done=true，附带 sources + citations + trace
            final_sources = [
                {
                    "filename": r.get("source_file", "") if isinstance(r, dict) else r.source_file,
                    "chunk_text": (r.get("chunk_text", "") if isinstance(r, dict) else r.chunk_text)[:200],
                    "score": r.get("score", 0) if isinstance(r, dict) else r.score,
                }
                for r in search_results
            ]
            final_chunk = ChatTokenChunk(
                token="", done=True,
                sources=final_sources,
                citations=citations if citations else None,
            )
            final_data = json.loads(final_chunk.model_dump_json())
            if trace_data:
                final_data["trace"] = trace_data
            # 暴露 Langfuse trace ID 给外部评估器（RAGAS）
            if _langfuse_trace is not None and getattr(_langfuse_trace, 'id', None):
                final_data["langfuse_trace_id"] = _langfuse_trace.id
            yield f"data: {json.dumps(final_data, ensure_ascii=False)}\n\n"

            elapsed = time.time() - start_time
            logger.info(f"问答完成: conv={conversation_id}, tokens={len(full_response)}, 耗时={elapsed:.2f}s")

        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error(
                f"LLM 流式生成超时: conv={conversation_id}, "
                f"已生成 tokens={len(full_response)}, 耗时={elapsed:.2f}s"
            )
            error_occurred = True
            td.get("generation", {})["error_type"] = "timeout"
            if not full_response:
                full_response = get_error_message("timeout")

        except Exception as e:
            logger.error(f"LLM 流式生成失败: {e}")
            error_occurred = True
            err_msg = str(e)
            if "401" in err_msg or "Unauthorized" in err_msg:
                td.get("generation", {})["error_type"] = "auth"
            elif "timeout" in err_msg.lower():
                td.get("generation", {})["error_type"] = "timeout"
            else:
                td.get("generation", {})["error_type"] = str(e)[:50]
            if not full_response:
                full_response = get_error_message(err_msg)

        finally:
            # ★ 即使 LLM 失败，也尝试发送 sources（检索可能已经完成）
            if not final_sources:
                final_sources = [
                    {
                        "filename": r.get("source_file", "") if isinstance(r, dict) else r.source_file,
                        "chunk_text": (r.get("chunk_text", "") if isinstance(r, dict) else r.chunk_text)[:200],
                        "score": r.get("score", 0) if isinstance(r, dict) else r.score,
                    }
                    for r in search_results
                ]

            # 发送末尾事件（含可能的错误信息或正常完成）
            final_chunk = ChatTokenChunk(
                token="", done=True,
                sources=final_sources,
                citations=citations if not error_occurred and citations else None,
            )
            yield f"data: {final_chunk.model_dump_json()}\n\n"

            elapsed = time.time() - start_time
            logger.info(f"问答完成: conv={conversation_id}, tokens={len(full_response)}, 耗时={elapsed:.2f}s")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
