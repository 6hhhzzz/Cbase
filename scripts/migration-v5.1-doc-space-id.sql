-- migration-v5.1-doc-space-id.sql
-- v5.1: 为 document_meta 表添加 space_id 冗余列
--
-- 用于加速按 Space 查询文档的 SQL，避免 JOIN knowledge_bases

BEGIN;

-- 添加 space_id 列
ALTER TABLE document_meta
    ADD COLUMN IF NOT EXISTS space_id UUID;

-- 回填现有数据：从 knowledge_bases 表获取 space_id
UPDATE document_meta dm
SET space_id = kb.space_id
FROM knowledge_bases kb
WHERE dm.kb_id = kb.id
  AND dm.space_id IS NULL;

-- 设置为 NOT NULL（回填完成之后）
ALTER TABLE document_meta
    ALTER COLUMN space_id SET NOT NULL;

-- 添加外键约束
ALTER TABLE document_meta
    ADD CONSTRAINT fk_doc_space
    FOREIGN KEY (space_id) REFERENCES spaces(id)
    ON DELETE CASCADE;

-- 索引加速按 Space 查询
CREATE INDEX IF NOT EXISTS idx_doc_space ON document_meta(space_id);

COMMIT;

-- 验证:
-- SELECT space_id, COUNT(*) FROM document_meta GROUP BY space_id;
