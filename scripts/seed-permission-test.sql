-- ============================================================
-- v4 ACE 权限验证 — 测试种子数据
--
-- 创建预置的测试结构，供 verify_permissions_v3.py 使用。
-- 或在手动测试时直接导入。
--
-- 用法:
--   docker exec -i kes-postgres psql -U kes -d kes < scripts/seed-permission-test.sql
-- ============================================================

-- 测试用户（is_global_admin 由管理员手动设置）
-- 密码均为 BCrypt(Test123456):
--   $2b$12$LJ3m4ys3Lg8xHwGOFz3JXeK5z8z8z8z8z8z8z8z8z8z8z8z8z8z8
-- 或通过 API 注册，不需要手动插入密码

INSERT INTO users (id, username, password, display_name, is_global_admin, created_at, updated_at)
VALUES (
    'perf-admin-0000-4000-a000-000000000001',
    'perf_admin',
    '$2b$12$LJ3m4ys3Lg8xHwGOFz3JXeK5z8z8z8z8z8z8z8z8z8z8z8z8z8z8',
    '权限测试管理员',
    TRUE,
    NOW(), NOW()
) ON CONFLICT (username) DO NOTHING;

INSERT INTO users (id, username, password, display_name, is_global_admin, created_at, updated_at)
VALUES (
    'perf-member-0000-4000-a000-000000000002',
    'perf_member',
    '$2b$12$LJ3m4ys3Lg8xHwGOFz3JXeK5z8z8z8z8z8z8z8z8z8z8z8z8z8z8',
    '权限测试普通成员',
    FALSE,
    NOW(), NOW()
) ON CONFLICT (username) DO NOTHING;

INSERT INTO users (id, username, password, display_name, is_global_admin, created_at, updated_at)
VALUES (
    'perf-finan-0000-4000-a000-000000000003',
    'perf_finance',
    '$2b$12$LJ3m4ys3Lg8xHwGOFz3JXeK5z8z8z8z8z8z8z8z8z8z8z8z8z8z8',
    '权限测试财务',
    FALSE,
    NOW(), NOW()
) ON CONFLICT (username) DO NOTHING;

-- 测试 Space
INSERT INTO spaces (id, name, type_label, description, status, created_by, created_at, updated_at)
VALUES (
    'perf-space-0000-4000-b000-000000000001',
    '权限测试空间',
    'test',
    '用于验证 v3 RBAC 权限体系',
    'active',
    'perf-admin-0000-4000-a000-000000000001',
    NOW(), NOW()
) ON CONFLICT (id) DO NOTHING;

-- v4 Space 管理员
-- perf_admin → owner (可管理 Space)
INSERT INTO space_admins (space_id, user_id, role, granted_by, created_at)
VALUES (
    'perf-space-0000-4000-b000-000000000001',
    'perf-admin-0000-4000-a000-000000000001',
    'owner', NULL, NOW()
) ON CONFLICT (space_id, user_id) DO NOTHING;

-- v4 测试用全局用户组
INSERT INTO user_groups (id, name, description, created_by, created_at, updated_at)
VALUES ('perf-group-rd-0000-4000-a000-000000000001', '研发部',  '测试用研发部组',   'perf-admin-0000-4000-a000-000000000001', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO user_groups (id, name, description, created_by, created_at, updated_at)
VALUES ('perf-group-fin-0000-4000-a000-000000000002', '财务部', '测试用财务部组', 'perf-admin-0000-4000-a000-000000000001', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- 用户归属组
INSERT INTO user_group_members (id, group_id, user_id) VALUES
    ('perf-ugm-01-0000-4000-d000-000000000301', 'perf-group-rd-0000-4000-a000-000000000001',  'perf-admin-0000-4000-a000-000000000001'),
    ('perf-ugm-02-0000-4000-d000-000000000302', 'perf-group-rd-0000-4000-a000-000000000001',  'perf-member-0000-4000-a000-000000000002'),
    ('perf-ugm-03-0000-4000-d000-000000000303', 'perf-group-fin-0000-4000-a000-000000000002', 'perf-finan-0000-4000-a000-000000000003')
ON CONFLICT (group_id, user_id) DO NOTHING;

-- v4 Space 准入组（研发部、财务部均可进入测试 Space）
INSERT INTO space_groups (id, space_id, group_id) VALUES
    ('perf-sg-01-0000-4000-b000-000000000101', 'perf-space-0000-4000-b000-000000000001', 'perf-group-rd-0000-4000-a000-000000000001'),
    ('perf-sg-02-0000-4000-b000-000000000102', 'perf-space-0000-4000-b000-000000000001', 'perf-group-fin-0000-4000-a000-000000000002')
ON CONFLICT (space_id, group_id) DO NOTHING;

-- KB-A: space_wide — 所有人可见
INSERT INTO knowledge_bases (id, space_id, name, description, visibility, created_by, created_at, updated_at)
VALUES (
    'perf-kba-0000-4000-c000-000000000001',
    'perf-space-0000-4000-b000-000000000001',
    '公开技术文档',
    'Space 内所有人可见的技术文档库',
    'space_wide',
    'perf-admin-0000-4000-a000-000000000001',
    NOW(), NOW()
) ON CONFLICT (id) DO NOTHING;

-- KB-B: restricted — 仅 perf_admin + perf_finance 可见
INSERT INTO knowledge_bases (id, space_id, name, description, visibility, created_by, created_at, updated_at)
VALUES (
    'perf-kbb-0000-4000-c000-000000000002',
    '私密财务文档',
    '仅特定成员可访问的财务文档库',
    'restricted',
    'perf-admin-0000-4000-a000-000000000001',
    NOW(), NOW()
) ON CONFLICT (id) DO NOTHING;

-- v4 ACE: KB-B 授权给 财务部 → Viewer (allow)
-- perf_admin 作为 owner 已全量可见，无需 ACE
INSERT INTO access_control_entries (id, space_id, resource_type, resource_id, principal_type, principal_id, role_id, effect)
VALUES (
    'perf-ace-01-0000-4000-e000-000000000401',
    'perf-space-0000-4000-b000-000000000001',
    'kb',
    'perf-kbb-0000-4000-c000-000000000002',
    'group',
    'perf-group-fin-0000-4000-a000-000000000002',
    'dddddddd-0000-4000-d000-000000000003',  -- Viewer 角色
    'allow'
) ON CONFLICT (space_id, resource_type, resource_id, principal_type, principal_id) DO NOTHING;
