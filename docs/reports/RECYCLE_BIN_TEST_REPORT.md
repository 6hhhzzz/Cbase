# 回收站功能测试报告

> 测试日期: 2026-06-16 | 测试人: Claude Agent

## 测试结果总览

| # | 测试场景 | 结果 | 备注 |
|---|---------|------|------|
| 1 | 空回收站查询 | ✅ | 初始状态返回空列表 |
| 2 | 文档软删除→回收站→恢复 | ✅ | 完整生命周期验证通过 |
| 3 | 文档软删除→永久删除 | ✅ | 向量+MinIO+DB 均清理 |
| 4 | KB 级联软删除/恢复 | ✅ | 文档跟随 KB 进入/退出回收站 |
| 5 | 非管理员权限拒绝 | ✅ | 所有管理端点返回 403 |
| 6 | 向量搜索隔离（软删除后搜索排除） | ✅ | chunks 状态同步为 soft_deleted |
| 7 | KB 级联向量隔离 | ✅ | 级联时 chunks 同步状态变化 |
| 8 | 文档永久删除向量清理 | ✅ | chunks 完全删除 |
| 9 | KB 永久删除级联清理 | ✅ (修复后) | 文档+chunks+MinIO 均清理 |

## 发现并修复的问题

### 1. 数据库 Schema 缺少列（3 个缺失列）

**文件**: `scripts/init-pgvector-v3.sql` 已更新但数据库未同步

修复操作：
- 运行 `migration-v3.1-recycle-bin.sql` 添加 `status`、`expires_at` 列
- 手动添加 `doc_effective_date`、`doc_expiry_date`、`doc_version` 到 `document_meta`
- 手动添加 `doc_effective_date`、`doc_expiry_date`、`doc_version` 到 `knowledge_chunks`

### 2. Python ETL 日期类型错误

**文件**: `ai-service/retrieval/vector_store.py`  
**错误**: `'str' object has no attribute 'toordinal'` — 日期字符串直接传给 asyncpg

**修复**: 添加 `_parse_date()` 函数将 `YYYY-MM-DD` 字符串转为 `datetime.date`

```python
def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)
```

### 3. KB 永久删除未级联清理文档

**文件**: `backend/.../auth/service/AuthService.java`  
**错误**: `permanentDeleteKb` 直接删 KB，但 `document_meta_kb_id_fkey` 无 CASCADE

**修复**:
- 注入 `MinioStorageService` 依赖
- 永久删除前：遍历所有文档 → 调 Python 删 chunks → 删 MinIO 文件 → 删 DB 记录
- 新增 `DocumentMetaRepository.findAllByKbId()` 非分页查询

## 已验证的功能点

### 状态机
- `active` ↔ `soft_deleted` 状态切换正常
- `deleted_at` 和 `expires_at` (= deleted_at + 30d) 正确设置
- 恢复时正确清空 `deleted_at` 和 `expires_at`

### 回收站 API (`GET /api/spaces/{spaceId}/trash`)
- 返回 `kb_items` 和 `doc_items` 两类
- 文档项包含 `kb_name`、`deleted_at`、`expires_at`、`file_type`
- 已随 KB 删除的文档不出现在 doc_items 中（避免重复）

### 权限控制 (`@RequireAdmin` + `AdminGuard`)
- 非管理员查看回收站 → 403 ✅
- 非管理员删除/恢复/永久删除 → 403 ✅

### 向量隔离
- 软删除时 Python `/v1/documents/status` 同步 `knowledge_chunks.status = 'soft_deleted'`
- 向量搜索 SQL 强制 `WHERE status = 'active'`
- 恢复时状态恢复为 `active`

### 永久删除清理链
1. Python `/v1/documents/{docId}/chunks` 删除向量
2. MinIO 文件删除
3. DB 记录 DELETE

## 测试环境

| 组件 | 状态 |
|------|------|
| PostgreSQL + pgvector | ✅ healthy |
| Redis | ✅ healthy |
| RabbitMQ | ✅ healthy |
| MinIO | ✅ healthy |
| Java Backend (8080) | ✅ running |
| Python AI (8000) | ✅ running |
| Frontend (5173) | 未测试（仅后端 API 验证） |
