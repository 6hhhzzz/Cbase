-- ============================================================
-- v3.1 回收站功能：文档状态机 + 向量隔离
--
-- 设计理念：回收站是状态机而非新表
--   document_meta.status: active ↔ soft_deleted
--   knowledge_chunks.status: active ↔ soft_deleted
--   永久删除直接 DELETE 记录
--   定时清理任务后续实现，expires_at 字段已预留
-- ============================================================

-- 1. document_meta 新增 status 和 expires_at 字段
ALTER TABLE document_meta
  ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'active';

ALTER TABLE document_meta
  ADD CONSTRAINT chk_dm_status CHECK (status IN ('active', 'soft_deleted'));

ALTER TABLE document_meta
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;

-- 2. 迁移现有数据：已软删除的文档标记为 soft_deleted
UPDATE document_meta
SET status = 'soft_deleted'
WHERE deleted_at IS NOT NULL AND status = 'active';

-- 为已删除文档计算过期时间
UPDATE document_meta
SET expires_at = deleted_at + INTERVAL '30 days'
WHERE deleted_at IS NOT NULL AND expires_at IS NULL;

-- 3. 索引
CREATE INDEX IF NOT EXISTS idx_dm_status ON document_meta(status);
CREATE INDEX IF NOT EXISTS idx_dm_expires ON document_meta(expires_at);

-- 4. knowledge_chunks 新增 status 字段
ALTER TABLE knowledge_chunks
  ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'active';

ALTER TABLE knowledge_chunks
  ADD CONSTRAINT chk_kc_status CHECK (status IN ('active', 'soft_deleted'));

-- 5. 同步已有数据：已软删除文档的 chunks 也标记为 soft_deleted
UPDATE knowledge_chunks kc
SET status = 'soft_deleted'
FROM document_meta dm
WHERE kc.doc_id = dm.id::text
  AND dm.status = 'soft_deleted'
  AND kc.status = 'active';

-- 加索引加速按 doc_id + status 查询
CREATE INDEX IF NOT EXISTS idx_kc_status ON knowledge_chunks(status);
