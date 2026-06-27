-- v9: 企业 OA 扩展 — JSONB 扩展列 + 外部身份绑定表
-- 不改业务逻辑，只铺数据基础，为对接企业 IdP/权限模型做准备

-- ============================================================
-- 1. users 加 metadata JSONB（企业自定义字段）
-- ============================================================
ALTER TABLE users ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
COMMENT ON COLUMN users.metadata IS '企业扩展字段: department, job_title, employee_id, 任意自定义键值';

-- ============================================================
-- 2. user_groups 加外部标识 + 扩展
-- ============================================================
ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS external_id VARCHAR(256);
ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS source VARCHAR(32) DEFAULT 'local';
ALTER TABLE user_groups ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
COMMENT ON COLUMN user_groups.external_id IS '外部系统组标识，如 LDAP DN / Okta Group ID';
COMMENT ON COLUMN user_groups.source IS '组来源: local | ldap | oidc';
COMMENT ON COLUMN user_groups.metadata IS '企业扩展字段';

-- ============================================================
-- 3. spaces 加扩展
-- ============================================================
ALTER TABLE spaces ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
COMMENT ON COLUMN spaces.metadata IS '企业扩展字段: cost_center, org_unit, 任意自定义键值';

-- ============================================================
-- 4. knowledge_bases 加扩展
-- ============================================================
ALTER TABLE knowledge_bases ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
COMMENT ON COLUMN knowledge_bases.metadata IS '企业扩展字段: department, classification, 任意自定义键值';

-- ============================================================
-- 5. ★ 外部身份绑定表
--    一个 KES 用户可以绑定多个外部身份
--    "张三在 Okta 是 zhangsan, 在 AD 是 zs"
-- ============================================================
CREATE TABLE IF NOT EXISTS user_identities (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider          VARCHAR(32) NOT NULL,   -- okta | azure_ad | ldap | wechat_work | dingtalk
    external_id       VARCHAR(256) NOT NULL,  -- IdP 中的唯一标识 (sub / DN / openid)
    external_username VARCHAR(128),           -- IdP 中的用户名（可选，便于审计）
    idp_attributes    JSONB DEFAULT '{}',     -- IdP 返回的原始属性（groups, roles, department...）
    last_synced_at    TIMESTAMP,
    created_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(provider, external_id)
);

CREATE INDEX IF NOT EXISTS idx_ui_user ON user_identities(user_id);
CREATE INDEX IF NOT EXISTS idx_ui_provider_ext ON user_identities(provider, external_id);

COMMENT ON TABLE user_identities IS '外部身份绑定 — 一个 KES 用户可绑定多个 IdP 账号';
COMMENT ON COLUMN user_identities.provider IS '身份提供商: okta, azure_ad, ldap, wechat_work, dingtalk';
COMMENT ON COLUMN user_identities.external_id IS 'IdP 中的唯一标识符';
COMMENT ON COLUMN user_identities.idp_attributes IS 'IdP 返回的原始属性 JSON，便于自定义权限解析';
