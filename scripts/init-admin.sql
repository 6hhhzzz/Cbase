-- ============================================================
-- v4 ACE 管理员初始化脚本
--
-- 账号速查:
--   admin_company / admin123  → Space: 默认空间 (owner)
--
-- 用法:
--   docker exec -i kes-postgres psql -U kes -d kes < scripts/init-admin.sql
-- ============================================================

-- ============================================================
-- 用户
-- ============================================================
INSERT INTO users (id, username, password, display_name, is_global_admin, created_at, updated_at)
VALUES (
    'aaaaaaaa-0000-4000-a000-000000000001',
    'admin_company',
    '$2b$12$q2tZr0NQJ87dDS1ANj8MDeS.V0cE/oILRlndO.m0ybPM/644sQW9i',  -- BCrypt(admin123)
    '公司管理员',
    TRUE,
    NOW(), NOW()
) ON CONFLICT (username) DO NOTHING;

INSERT INTO users (id, username, password, display_name, is_global_admin, created_at, updated_at)
VALUES (
    'aaaaaaaa-0000-4000-a000-000000000002',
    'admin_dept_tech',
    '$2b$12$zj8KGrn6v7ZpKbrNoSZocu7i4rZZeZrWJqge1/.X4AvuyB8RXqC/u',  -- BCrypt(dept123)
    '技术部管理员',
    FALSE,
    NOW(), NOW()
) ON CONFLICT (username) DO NOTHING;

-- ============================================================
-- 默认 Space
-- ============================================================
INSERT INTO spaces (id, name, type_label, description, created_by, created_at, updated_at)
VALUES (
    'bbbbbbbb-0000-4000-b000-000000000001',
    '默认空间',
    'general',
    '系统默认工作空间',
    'aaaaaaaa-0000-4000-a000-000000000001',
    NOW(), NOW()
) ON CONFLICT (id) DO NOTHING;

-- v4: 创建者成为 Space 的 owner
INSERT INTO space_admins (space_id, user_id, role, granted_by, created_at)
VALUES (
    'bbbbbbbb-0000-4000-b000-000000000001',
    'aaaaaaaa-0000-4000-a000-000000000001',
    'owner',
    NULL,
    NOW()
) ON CONFLICT (space_id, user_id) DO NOTHING;

-- v4: 第二个管理员作为普通 member（后续可通过 API 升级为 admin）
INSERT INTO space_admins (space_id, user_id, role, granted_by, created_at)
VALUES (
    'bbbbbbbb-0000-4000-b000-000000000001',
    'aaaaaaaa-0000-4000-a000-000000000002',
    'admin',
    'aaaaaaaa-0000-4000-a000-000000000001',
    NOW()
) ON CONFLICT (space_id, user_id) DO NOTHING;

-- ============================================================
-- 默认 KB（space_wide 可见）
-- ============================================================
INSERT INTO knowledge_bases (id, space_id, name, description, visibility, created_by, created_at, updated_at)
VALUES (
    'cccccccc-0000-4000-c000-000000000001',
    'bbbbbbbb-0000-4000-b000-000000000001',
    '默认知识库',
    '系统默认知识库',
    'space_wide',
    'aaaaaaaa-0000-4000-a000-000000000001',
    NOW(), NOW()
) ON CONFLICT (id) DO NOTHING;
