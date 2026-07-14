-- migration-v12: retrieval_feedback 添加 stages_detail JSONB 列
-- 存储完整的检索链路阶段追踪数据（preprocessor/planner/retrieval/critic/assembly/generation/citation）
-- 应用日期: 2026-07-06

ALTER TABLE retrieval_feedback ADD COLUMN IF NOT EXISTS stages_detail JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN retrieval_feedback.stages_detail IS 'v12: 检索链路全量阶段追踪数据 — preprocessor/planner/retrieval/critic/assembly/generation/citation';
