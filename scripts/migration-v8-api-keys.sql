-- v8: MCP API 密钥管理
-- 用户自助创建/撤销，密钥权限 = 创建者权限

CREATE TABLE IF NOT EXISTS api_keys (
    id            UUID         PRIMARY KEY,
    user_id       UUID         NOT NULL REFERENCES users(id),
    name          VARCHAR(128) NOT NULL,
    key_hash      VARCHAR(255) NOT NULL,
    key_prefix    VARCHAR(16)  NOT NULL,
    expires_at    TIMESTAMP    NOT NULL,
    last_used_at  TIMESTAMP,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at    TIMESTAMP,
    scope_kb_ids  JSONB        -- 预留：限定 KB 范围，NULL = 无限制
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE UNIQUE INDEX IF NOT EXISTS uq_api_keys_user_name ON api_keys(user_id, name);

COMMENT ON TABLE api_keys IS 'MCP API 密钥 — 用户自助管理，用于外部 Agent 接入';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA-256(完整密钥)';
COMMENT ON COLUMN api_keys.key_prefix IS '密钥前缀（展示用，如 kes_mcp_xxxx）';
COMMENT ON COLUMN api_keys.revoked_at IS '撤销时间，NULL = 有效';
