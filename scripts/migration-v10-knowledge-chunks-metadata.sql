-- migration-v10: knowledge_chunks 添加 metadata JSONB 列
-- ETL MetadataEnrichStep 产出结构化元数据 (chunk_type/level/heading/page_range/doc_id)
-- MCP Resource (entities/structure) 的权威数据源
-- 应用日期: 2026-06-29

ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN knowledge_chunks.metadata IS 'v10: ETL MetadataEnrichStep 产出的结构化元数据 (chunk_type/level/heading/page_range/doc_id)';
