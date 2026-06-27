-- migration-v5-hnsw-fts.sql
-- v5: 混合检索引擎升级 — HNSW 索引 + 全文搜索 + content_with_weight
--
-- 变更内容:
--   1. knowledge_chunks 新增 fts (tsvector) 列 + GIN 索引 → BM25 关键词检索
--   2. knowledge_chunks 新增 content_with_weight (TEXT) 列 → 关键词加权重复
--   3. 向量索引从 IVFFlat 迁移到 HNSW → 更高召回率，无需训练
--   4. 现有数据的 fts 和 content_with_weight 回填
--
-- 执行方式: psql -U kes -d kes -f migration-v5-hnsw-fts.sql
-- 回滚方式: 见文件末尾

BEGIN;

-- ============================================================
-- 1. 新增列
-- ============================================================

-- content_with_weight: 关键词加权重复文本（用于 BM25 增强）
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS content_with_weight TEXT;

-- fts: PostgreSQL 全文搜索向量
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS fts tsvector;

-- ============================================================
-- 2. 回填现有数据
-- ============================================================

-- content_with_weight 初始值 = chunk_text
UPDATE knowledge_chunks
SET content_with_weight = chunk_text
WHERE content_with_weight IS NULL;

-- fts: 使用 simple 词典（中英文混合友好，不做 stemming）
UPDATE knowledge_chunks
SET fts = to_tsvector('simple', COALESCE(content_with_weight, chunk_text))
WHERE fts IS NULL;

-- ============================================================
-- 3. 全文搜索索引
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_kc_fts
    ON knowledge_chunks USING GIN (fts);

-- ============================================================
-- 4. 向量索引：IVFFlat → HNSW
-- ============================================================

-- 删除旧的 IVFFlat 索引
DROP INDEX IF EXISTS idx_kc_embedding;

-- 创建 HNSW 索引（m=16 为默认推荐值，ef_construction=64）
-- HNSW 优势：查询更快、召回率更高、无需手动训练
CREATE INDEX IF NOT EXISTS idx_kc_embedding_hnsw
    ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================
-- 5. 辅助列/索引
-- ============================================================

-- 为 metadata 中的有效日期字段添加函数索引（加速过期过滤）
CREATE INDEX IF NOT EXISTS idx_kc_effective_date
    ON knowledge_chunks (doc_effective_date)
    WHERE doc_effective_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kc_expiry_date
    ON knowledge_chunks (doc_expiry_date);

-- ============================================================
-- 6. 触发器：自动更新 fts
-- ============================================================

CREATE OR REPLACE FUNCTION update_kc_fts()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fts = to_tsvector('simple',
        regexp_replace(COALESCE(NEW.content_with_weight, NEW.chunk_text), '([一-鿿])', ' \\1 ', 'g'));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 如果触发器已存在则跳过
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_update_kc_fts'
    ) THEN
        CREATE TRIGGER trg_update_kc_fts
            BEFORE INSERT OR UPDATE OF chunk_text, content_with_weight
            ON knowledge_chunks
            FOR EACH ROW
            EXECUTE FUNCTION update_kc_fts();
    END IF;
END $$;

COMMIT;

-- ============================================================
-- 验证
-- ============================================================
-- 检查列是否存在:
--   SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name = 'knowledge_chunks'
--   AND column_name IN ('fts', 'content_with_weight');
--
-- 检查索引是否存在:
--   SELECT indexname, indexdef FROM pg_indexes
--   WHERE tablename = 'knowledge_chunks'
--   AND indexname IN ('idx_kc_fts', 'idx_kc_embedding_hnsw');

-- ============================================================
-- 回滚 (如需撤销变更)
-- ============================================================
-- BEGIN;
-- DROP INDEX IF EXISTS idx_kc_fts;
-- DROP INDEX IF EXISTS idx_kc_embedding_hnsw;
-- DROP TRIGGER IF EXISTS trg_update_kc_fts ON knowledge_chunks;
-- DROP FUNCTION IF EXISTS update_kc_fts();
-- ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS fts;
-- ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS content_with_weight;
-- CREATE INDEX IF NOT EXISTS idx_kc_embedding
--     ON knowledge_chunks USING IVFFLAT (embedding vector_cosine_ops) WITH (lists = 1024);
-- COMMIT;
