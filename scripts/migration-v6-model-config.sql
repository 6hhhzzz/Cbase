-- migration-v6-model-config.sql
-- v6: 模型配置动态管理 — Provider / Model / Assignment 三表 + 种子数据
--
-- 设计原则:
--   1. API Key 不存数据库，只存环境变量名（如 ${DASHSCOPE_API_KEY}）
--   2. 配置版本号 system_config 支持热重载
--   3. 全局管理员通过前端管理界面配置，Python 启动时拉取
--
-- 执行: psql -U kes -d kes -f migration-v6-model-config.sql

BEGIN;

-- ============================================================
-- 1. model_providers — 模型供应商
-- ============================================================
CREATE TABLE IF NOT EXISTS model_providers (
    id            UUID         PRIMARY KEY,
    name          VARCHAR(64)  NOT NULL UNIQUE,       -- "dashscope", "ollama", "bge"
    type          VARCHAR(32)  NOT NULL,              -- "openai_compatible" | "ollama" | "cross_encoder"
    base_url      VARCHAR(512) NOT NULL,              -- API 地址
    api_key_env   VARCHAR(128),                       -- 环境变量名 "${DASHSCOPE_API_KEY}"
    is_enabled    BOOLEAN      DEFAULT TRUE,
    extra         JSONB        DEFAULT '{}',
    created_at    TIMESTAMP    DEFAULT NOW(),
    updated_at    TIMESTAMP    DEFAULT NOW()
);

-- ============================================================
-- 2. model_configs — 模型实例
-- ============================================================
CREATE TABLE IF NOT EXISTS model_configs (
    id            UUID         PRIMARY KEY,
    provider_id   UUID         NOT NULL REFERENCES model_providers(id) ON DELETE CASCADE,
    model_name    VARCHAR(128) NOT NULL,              -- "qwen-plus"
    model_type    VARCHAR(32)  NOT NULL,              -- "chat" | "embedding" | "reranker"
    dimension     INTEGER,                            -- embedding 向量维度
    max_tokens    INTEGER,                            -- 上下文窗口
    is_enabled    BOOLEAN      DEFAULT TRUE,
    extra         JSONB        DEFAULT '{}',           -- temperature, top_p 等
    created_at    TIMESTAMP    DEFAULT NOW(),
    UNIQUE(provider_id, model_name)
);

-- ============================================================
-- 3. model_assignments — 环节→模型映射
-- ============================================================
CREATE TABLE IF NOT EXISTS model_assignments (
    id            UUID         PRIMARY KEY,
    purpose       VARCHAR(32)  NOT NULL UNIQUE,       -- "chat"|"rewrite"|"intent"|"embedding"|"reranker"|"rerank_llm"
    model_id      UUID         REFERENCES model_configs(id) ON DELETE SET NULL,
    updated_at    TIMESTAMP    DEFAULT NOW()
);

-- ============================================================
-- 4. system_config — 配置版本号（热重载信号）
-- ============================================================
CREATE TABLE IF NOT EXISTS system_config (
    key           VARCHAR(64)  PRIMARY KEY,
    value         TEXT         NOT NULL,
    updated_at    TIMESTAMP    DEFAULT NOW()
);

INSERT INTO system_config (key, value) VALUES ('model_config_version', '1')
    ON CONFLICT (key) DO NOTHING;

-- ============================================================
-- 5. 种子数据 — 默认 Provider + Model + Assignment
-- ============================================================

-- DashScope (阿里云百炼)
INSERT INTO model_providers (id, name, type, base_url, api_key_env)
VALUES ('b0000000-0000-0000-0000-000000000001', 'dashscope', 'openai_compatible',
        'https://dashscope.aliyuncs.com/compatible-mode/v1', '${DASHSCOPE_API_KEY}')
ON CONFLICT (name) DO NOTHING;

-- Ollama (本地)
INSERT INTO model_providers (id, name, type, base_url, api_key_env)
VALUES ('b0000000-0000-0000-0000-000000000002', 'ollama', 'ollama',
        'http://localhost:11434', NULL)
ON CONFLICT (name) DO NOTHING;

-- BGE Reranker (本地交叉编码器)
INSERT INTO model_providers (id, name, type, base_url, api_key_env)
VALUES ('b0000000-0000-0000-0000-000000000003', 'bge', 'cross_encoder',
        'local', NULL)
ON CONFLICT (name) DO NOTHING;

-- DashScope 模型
INSERT INTO model_configs (id, provider_id, model_name, model_type, dimension, max_tokens)
VALUES ('c0000000-0000-0000-0000-000000000001',
        'b0000000-0000-0000-0000-000000000001', 'qwen-plus', 'chat', NULL, 131072)
ON CONFLICT (provider_id, model_name) DO NOTHING;

INSERT INTO model_configs (id, provider_id, model_name, model_type, dimension, max_tokens)
VALUES ('c0000000-0000-0000-0000-000000000002',
        'b0000000-0000-0000-0000-000000000001', 'qwen-turbo', 'chat', NULL, 131072)
ON CONFLICT (provider_id, model_name) DO NOTHING;

INSERT INTO model_configs (id, provider_id, model_name, model_type, dimension, max_tokens)
VALUES ('c0000000-0000-0000-0000-000000000003',
        'b0000000-0000-0000-0000-000000000001', 'text-embedding-v3', 'embedding', 1024, NULL)
ON CONFLICT (provider_id, model_name) DO NOTHING;

-- 默认环节映射
INSERT INTO model_assignments (id, purpose, model_id)
VALUES ('d0000000-0000-0000-0000-000000000001', 'chat',
        'c0000000-0000-0000-0000-000000000001')
ON CONFLICT (purpose) DO NOTHING;

INSERT INTO model_assignments (id, purpose, model_id)
VALUES ('d0000000-0000-0000-0000-000000000002', 'rewrite',
        'c0000000-0000-0000-0000-000000000002')
ON CONFLICT (purpose) DO NOTHING;

INSERT INTO model_assignments (id, purpose, model_id)
VALUES ('d0000000-0000-0000-0000-000000000003', 'intent',
        'c0000000-0000-0000-0000-000000000002')
ON CONFLICT (purpose) DO NOTHING;

INSERT INTO model_assignments (id, purpose, model_id)
VALUES ('d0000000-0000-0000-0000-000000000004', 'embedding',
        'c0000000-0000-0000-0000-000000000003')
ON CONFLICT (purpose) DO NOTHING;

INSERT INTO model_assignments (id, purpose, model_id)
VALUES ('d0000000-0000-0000-0000-000000000005', 'reranker',
        NULL)  -- 默认不启用
ON CONFLICT (purpose) DO NOTHING;

INSERT INTO model_assignments (id, purpose, model_id)
VALUES ('d0000000-0000-0000-0000-000000000006', 'rerank_llm',
        'c0000000-0000-0000-0000-000000000002')
ON CONFLICT (purpose) DO NOTHING;

COMMIT;

-- 验证:
-- SELECT * FROM model_providers;
-- SELECT * FROM model_configs;
-- SELECT * FROM model_assignments;
-- SELECT * FROM system_config;
