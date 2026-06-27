-- ============================================================
-- 企业知识助手 — v3 → v4 ACE 权限模型迁移（升级用）
--
-- 仅用于从 v3 升级到 v4。全新安装请直接使用 init-pgvector.sql。
--
-- 用法:
--   docker exec -i kes-postgres psql -U kes -d kes < scripts/migration-v4-ace-permission.sql
-- ============================================================

-- Step 1: 创建 v4 新表（如已通过 init 创建则跳过）
CREATE TABLE IF NOT EXISTS user_groups (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_group_id  UUID         REFERENCES user_groups(id) ON DELETE SET NULL,
    name             VARCHAR(128) NOT NULL,
    description      TEXT         DEFAULT '',
    is_system_admin  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_by       UUID         NOT NULL REFERENCES users(id),
    created_at       TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_groups_parent ON user_groups(parent_group_id);

CREATE TABLE IF NOT EXISTS user_group_members (
    id         UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id   UUID       NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    user_id    UUID       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    joined_at  TIMESTAMP  NOT NULL DEFAULT NOW(),
    UNIQUE(group_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_ugm_user  ON user_group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_ugm_group ON user_group_members(group_id);

CREATE TABLE IF NOT EXISTS roles (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(64)  NOT NULL,
    description  TEXT         DEFAULT '',
    permissions  JSONB        NOT NULL DEFAULT '{}',
    is_system    BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS space_admins (
    space_id   UUID       NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    user_id    UUID       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role       VARCHAR(20) NOT NULL CHECK (role IN ('owner', 'admin')),
    granted_by UUID       REFERENCES users(id),
    created_at TIMESTAMP  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (space_id, user_id)
);

CREATE TABLE IF NOT EXISTS space_groups (
    id         UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id   UUID       NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    group_id   UUID       NOT NULL REFERENCES user_groups(id) ON DELETE CASCADE,
    joined_at  TIMESTAMP  NOT NULL DEFAULT NOW(),
    UNIQUE(space_id, group_id)
);
CREATE INDEX IF NOT EXISTS idx_sg_space ON space_groups(space_id);
CREATE INDEX IF NOT EXISTS idx_sg_group ON space_groups(group_id);

CREATE TABLE IF NOT EXISTS access_control_entries (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    space_id        UUID         NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
    resource_type   VARCHAR(16)  NOT NULL CHECK (resource_type IN ('kb', 'document')),
    resource_id     UUID         NOT NULL,
    principal_type  VARCHAR(16)  NOT NULL CHECK (principal_type IN ('group', 'user')),
    principal_id    UUID         NOT NULL,
    role_id         UUID         NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    effect          VARCHAR(8)   NOT NULL DEFAULT 'allow' CHECK (effect IN ('allow', 'deny')),
    priority        INT          NOT NULL DEFAULT 0,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    UNIQUE(space_id, resource_type, resource_id, principal_type, principal_id)
);
CREATE INDEX IF NOT EXISTS idx_ace_space     ON access_control_entries(space_id);
CREATE INDEX IF NOT EXISTS idx_ace_resource  ON access_control_entries(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_ace_principal ON access_control_entries(principal_type, principal_id);

-- Step 2: 预置系统角色（幂等）
INSERT INTO roles (id, name, description, permissions, is_system, created_at) VALUES
    ('dddddddd-0000-4000-d000-000000000001', 'Admin',  'KB 管理员：读写删 + 管理', '["kb.read","kb.write","kb.delete","kb.manage","ace.manage"]', TRUE, NOW()),
    ('dddddddd-0000-4000-d000-000000000002', 'Editor', '内容编辑：读写',          '["kb.read","kb.write"]', TRUE, NOW()),
    ('dddddddd-0000-4000-d000-000000000003', 'Viewer', '只读：仅查看',            '["kb.read"]', TRUE, NOW()),
    ('dddddddd-0000-4000-d000-000000000004', 'Deny',   '显式拒绝',                '[]', TRUE, NOW())
ON CONFLICT (id) DO NOTHING;

-- Step 3: document_meta 加文档级权限字段
ALTER TABLE document_meta ADD COLUMN IF NOT EXISTS inherit_permissions BOOLEAN NOT NULL DEFAULT TRUE;

-- Step 4: 删除 v3 旧表
DROP TABLE IF EXISTS kb_members CASCADE;
DROP TABLE IF EXISTS space_members CASCADE;
