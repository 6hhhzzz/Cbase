"""Trace 持久化 — asyncpg 数据库 INSERT/UPDATE 操作。"""

import json
import uuid

from common import get_logger

logger = get_logger(__name__)


class FeedbackRepository:
    """检索反馈数据库操作（asyncpg）。"""

    def __init__(self, pool=None):
        self._pool = pool

    async def save_trace(self, trace: dict) -> str:
        """INSERT trace 到 retrieval_feedback 表。"""
        if self._pool is None:
            logger.warning("连接池未初始化，无法保存 trace")
            return trace.get("trace_id", "")

        trace_id = trace.get("trace_id", str(uuid.uuid4()))

        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO retrieval_feedback (
                        id, created_at, source, user_id, space_id, session_id,
                        original_query, rewritten_query, kb_ids, keywords,
                        resolved_filters, retrieval_path, top_k, min_score,
                        latency_breakdown, recall_stats, reranked_count,
                        filtered_count, llm_tokens, chunks, generated_response,
                        faithfulness_score, answer_relevance, context_relevance,
                        judge_model, judge_latency_ms,
                        rating, feedback_reason, feedback_at, extra,
                        stages_detail
                    ) VALUES (
                        $1,  NOW(),  $2,  $3,  $4,  $5,
                        $6,  $7,  $8::jsonb,  $9::jsonb,
                        $10::jsonb, $11, $12, $13,
                        $14::jsonb, $15::jsonb, $16,
                        $17, $18::jsonb, $19::jsonb, $20,
                        $21, $22, $23,
                        $24, $25,
                        $26, $27, $28, $29::jsonb,
                        $30::jsonb
                    )
                """,
                    trace_id,
                    trace.get("source", ""),
                    trace.get("user_id", ""),
                    trace.get("space_id", ""),
                    trace.get("session_id", ""),
                    trace.get("original_query", ""),
                    trace.get("rewritten_query", ""),
                    json.dumps(trace.get("kb_ids", [])),
                    json.dumps(trace.get("keywords", [])),
                    json.dumps(trace.get("resolved_filters", {})),
                    trace.get("retrieval_path", ""),
                    trace.get("top_k", 0),
                    trace.get("min_score", 0.0),
                    json.dumps(trace.get("latency_breakdown", {})),
                    json.dumps(trace.get("recall_stats", {})),
                    trace.get("reranked_count", 0),
                    trace.get("filtered_count", 0),
                    json.dumps(trace.get("llm_tokens", {})),
                    json.dumps(trace.get("chunks", [])),
                    trace.get("generated_response", ""),
                    trace.get("faithfulness_score"),
                    trace.get("answer_relevance"),
                    trace.get("context_relevance"),
                    trace.get("judge_model"),
                    trace.get("judge_latency_ms"),
                    trace.get("rating"),
                    trace.get("feedback_reason"),
                    None,  # feedback_at
                    json.dumps(trace.get("extra", {})),
                    json.dumps(trace.get("stages_detail", {})),
                )
            logger.debug(f"Trace 已保存: {trace_id}")
        except Exception as e:
            logger.error(f"保存 trace 失败: {e}")

        return trace_id

    async def update_feedback(
        self, trace_id: str, rating: str, reason: str = ""
    ) -> bool:
        """UPDATE 已有 trace 的反馈和 Judge 评分。"""
        if self._pool is None:
            logger.warning("连接池未初始化，无法更新反馈")
            return False

        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE retrieval_feedback
                    SET rating = $2,
                        feedback_reason = $3,
                        feedback_at = NOW()
                    WHERE id = $1
                """, trace_id, rating, reason or None)
                updated = result != "UPDATE 0"
                if updated:
                    logger.info(f"反馈已更新: {trace_id} rating={rating}")
                else:
                    logger.warning(f"Trace 不存在: {trace_id}")
                return updated
        except Exception as e:
            logger.error(f"更新反馈失败: {e}")
            return False

    async def update_judge_scores(
        self,
        trace_id: str,
        faithfulness: float,
        answer_relevance: float,
        context_relevance: float,
        judge_model: str = "",
        judge_latency_ms: int = 0,
    ) -> bool:
        """UPDATE Judge 评分到已有 trace。"""
        if self._pool is None:
            return False

        try:
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    UPDATE retrieval_feedback
                    SET faithfulness_score = $2,
                        answer_relevance = $3,
                        context_relevance = $4,
                        judge_model = $5,
                        judge_latency_ms = $6
                    WHERE id = $1
                """, trace_id, faithfulness, answer_relevance,
                    context_relevance, judge_model, judge_latency_ms)
                logger.debug(f"Judge 评分已更新: {trace_id}")
                return True
        except Exception as e:
            logger.error(f"更新 Judge 评分失败: {e}")
            return False
