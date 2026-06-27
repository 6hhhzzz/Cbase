-- v10: 角色 permissions 格式迁移 — 旧格式(JSON对象) → 新格式(JSON数组)
-- 同时将旧 key 名(doc:read/kb:admin) 迁移到新 key 名(kb.read/kb.manage)

UPDATE roles SET permissions = '["kb.read","kb.write","kb.delete","kb.manage","ace.manage"]'
WHERE id = 'dddddddd-0000-4000-d000-000000000001'
  AND permissions LIKE '{%';  -- 仅更新旧格式数据

UPDATE roles SET permissions = '["kb.read","kb.write"]'
WHERE id = 'dddddddd-0000-4000-d000-000000000002'
  AND permissions LIKE '{%';

UPDATE roles SET permissions = '["kb.read"]'
WHERE id = 'dddddddd-0000-4000-d000-000000000003'
  AND permissions LIKE '{%';

UPDATE roles SET permissions = '[]'
WHERE id = 'dddddddd-0000-4000-d000-000000000004'
  AND permissions LIKE '{%';
