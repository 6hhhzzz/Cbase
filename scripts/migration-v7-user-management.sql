-- v7: 用户管理增强
-- 新增字段: email, status, source, must_change_password
-- 支持管理员创建用户、批量导入、禁用/启用、OIDC 预备

ALTER TABLE users ADD COLUMN IF NOT EXISTS email               VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS status              VARCHAR(16)  DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS source              VARCHAR(32)  DEFAULT 'local';
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN     DEFAULT FALSE;

-- status 约束
ALTER TABLE users ADD CONSTRAINT chk_users_status
    CHECK (status IN ('active', 'disabled'));

-- source 约束
ALTER TABLE users ADD CONSTRAINT chk_users_source
    CHECK (source IN ('local', 'import', 'oidc'));

-- 索引
CREATE INDEX IF NOT EXISTS idx_users_email  ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

COMMENT ON COLUMN users.email               IS '用户邮箱，可选，用于批量导入匹配和 OIDC 映射';
COMMENT ON COLUMN users.status              IS '账户状态: active=正常, disabled=已禁用';
COMMENT ON COLUMN users.source              IS '账户来源: local=自助注册, import=管理员导入, oidc=外部IdP联邦';
COMMENT ON COLUMN users.must_change_password IS '是否强制在下次登录时修改密码';
