-- ============================================================
-- v12: RAGAS 评估框架 — 数据库扩展
-- ============================================================
-- 为 retrieval_feedback 表添加 ragas_scores JSONB 列，
-- 用于存储 RAGAS 离线批量评估的标准化指标分数。
--
-- RAGAS 指标格式:
--   {
--     "faithfulness": 0.85,
--     "response_relevancy": 0.92,
--     "answer_correctness": 0.78,
--     "llm_context_precision_with_reference": 0.80,
--     "llm_context_recall": 0.76,
--     "eval_model": "qwen-plus",
--     "eval_timestamp": "2026-07-06T12:00:00+00:00"
--   }
-- ============================================================

ALTER TABLE IF EXISTS retrieval_feedback
    ADD COLUMN IF NOT EXISTS ragas_scores JSONB;

COMMENT ON COLUMN retrieval_feedback.ragas_scores IS
    'RAGAS 离线批量评估分数 JSONB。键为指标名，值为 0-1 分数。';

-- ============================================================
-- 新增合成数据 source 类型（可选）
-- ============================================================
-- retrieval_feedback.source 原约束: CHECK (source IN ('web_chat', 'mcp'))
-- 合成评估数据写入时 source = 'synthetic'

-- 如果约束已存在，先删除再重建（仅当需要写入合成数据时）
-- ALTER TABLE retrieval_feedback DROP CONSTRAINT IF EXISTS retrieval_feedback_source_check;
-- ALTER TABLE retrieval_feedback ADD CONSTRAINT retrieval_feedback_source_check
--     CHECK (source IN ('web_chat', 'mcp', 'synthetic'));
