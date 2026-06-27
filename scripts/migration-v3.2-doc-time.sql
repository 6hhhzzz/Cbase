-- ============================================================
-- v3.2 文档业务时效字段
--
-- 新增字段:
--   doc_effective_date: 文档生效日期，必填，默认上传当天
--   doc_expiry_date:   文档失效日期，可空，空表示长期有效
--   doc_version:        文档版本号，如 v2.0 / 2026年修订版
--
-- knowledge_chunks 同步添加，供后续 AI 时间意图识别使用
-- ============================================================

-- 1. document_meta 新增字段
ALTER TABLE document_meta
  ADD COLUMN IF NOT EXISTS doc_effective_date DATE NOT NULL DEFAULT CURRENT_DATE;

ALTER TABLE document_meta
  ADD COLUMN IF NOT EXISTS doc_expiry_date DATE;

ALTER TABLE document_meta
  ADD COLUMN IF NOT EXISTS doc_version VARCHAR(32);

-- 有效日期加索引，用于"即将过期"查询
CREATE INDEX IF NOT EXISTS idx_dm_effective ON document_meta(doc_effective_date);
CREATE INDEX IF NOT EXISTS idx_dm_expiry ON document_meta(doc_expiry_date);
CREATE INDEX IF NOT EXISTS idx_dm_version ON document_meta(doc_version);

-- 2. knowledge_chunks 新增字段（供未来 AI 时间过滤）
ALTER TABLE knowledge_chunks
  ADD COLUMN IF NOT EXISTS doc_effective_date DATE;

ALTER TABLE knowledge_chunks
  ADD COLUMN IF NOT EXISTS doc_expiry_date DATE;

ALTER TABLE knowledge_chunks
  ADD COLUMN IF NOT EXISTS doc_version VARCHAR(32);

-- 可选：为已有 chunks 回填空默认值（后续由 ETL 重新注入）
UPDATE knowledge_chunks
SET doc_effective_date = CURRENT_DATE
WHERE doc_effective_date IS NULL;
