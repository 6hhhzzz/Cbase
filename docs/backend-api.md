# 后端接口文档

> 基于 Java 后端 11 个 Controller 的实际代码提取，共 **81 个端点**。

## 通用说明

### 基础地址

- **开发环境**: `http://localhost:8080`
- **生产环境**: 通过 Nginx 反向代理

### 认证方式

| Token | 位置 | 生命周期 | 用途 |
|-------|------|---------|------|
| `refresh_token` | `Authorization: Bearer <token>` | 7 天 | 登录、刷新、列 Space、切换 Space |
| `context_token` | `Authorization: Bearer <token>` | 30 分钟 | 所有业务 API |
| `api_key` | 请求体 | 永久（可设有效期） | MCP 密钥交换 |

### 统一响应格式

```json
// 成功
{ "code": 0, "data": {...} }

// 失败
{ "code": 非0, "error_code": "ERROR_CODE", "message": "描述" }
```

### 安全注解

| 注解 | 含义 |
|------|------|
| `@RequireSpaceAdmin` | 当前 Space 的 owner 或 admin |
| `@RequireGlobalAdmin` | `users.is_global_admin = true` |
| 无注解 + 手动检查 | Controller 内部调 `PermissionService` 做细粒度校验 |

---

## 1. Auth — 认证

**包**: `com.kes.auth.controller.AuthController`
**基础路径**: `/api/auth`

### POST /api/auth/register
注册新用户。

| 项目 | 内容 |
|------|------|
| 认证 | 无 |
| 请求体 | `{ "username": "string (3-32)", "password": "string (≥8)", "display_name": "string" }` |
| 响应 | `ApiResponse<UserInfo>` — `{ id, username, display_name, is_global_admin }` |

### POST /api/auth/login
登录，返回 refresh_token。

| 项目 | 内容 |
|------|------|
| 认证 | 无 |
| 请求体 | `{ "username": "string", "password": "string" }` |
| 响应 | `ApiResponse<TokenResponse>` — `{ refresh_token, user: { user_id, username, spaces: [{space_id, space_name, role}] } }` |

### POST /api/auth/refresh
刷新 refresh_token。

| 项目 | 内容 |
|------|------|
| 认证 | 无 |
| 请求体 | `{ "refresh_token": "string" }` |
| 响应 | `ApiResponse<TokenResponse>` — 新的 `{ refresh_token }` |
| 响应示例 | `{ "code": 0, "data": { "access_token": "eyJ...", "refresh_token": "eyJ..." } }` |

### GET /api/auth/spaces
获取用户的 Space 列表。

| 项目 | 内容 |
|------|------|
| 认证 | `Authorization` header（refresh_token） |
| 响应 | `ApiResponse<List<SpaceInfo>>` — `[{ space_id, space_name, role }]` |

### POST /api/auth/switch-space
切换到指定 Space，签发 30 分钟 context_token。

| 项目 | 内容 |
|------|------|
| 认证 | `Authorization` header（refresh_token） |
| 请求体 | `{ "space_id": "uuid" }` |
| 响应 | `ApiResponse<TokenResponse>` — `{ access_token }`（注：字段名为 `access_token`，前端用作 context_token） |

### GET /api/auth/accessible-kbs
获取当前 Space 下有权限的 KB 列表。

| 项目 | 内容 |
|------|------|
| 认证 | `Authorization` header（context_token） |
| 响应 | `ApiResponse<List<KbAccessInfo>>` — `[{ kb_id, name, description, visibility }]` |

### GET /api/auth/users/search
按用户名前缀搜索用户。

| 项目 | 内容 |
|------|------|
| 认证 | `Authorization` header |
| 参数 | `?q=<prefix>` |
| 响应 | `ApiResponse<List<Map>>` — `[{ user_id, username, display_name }]` |

### PUT /api/auth/password
修改密码。

| 项目 | 内容 |
|------|------|
| 认证 | `Authorization` header |
| 请求体 | `{ "old_password": "string", "new_password": "string" }` |

---

## 2. Space — 空间管理

**包**: `com.kes.auth.controller.SpaceController`
**基础路径**: `/api/spaces`

### 生命周期

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| POST | `/api/spaces` | Header | `{ name, type_label?, description? }` | 创建 Space |
| POST | `/api/spaces/{spaceId}/archive` | `@RequireSpaceAdmin` | — | 归档 Space |
| GET | `/api/spaces/{spaceId}/members` | `@RequireSpaceAdmin` | — | 查看成员（管理员列表 + 准入组列表） |

### 管理员

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| GET | `/api/spaces/{spaceId}/admins` | `@RequireSpaceAdmin` | — | 查看管理员 |
| POST | `/api/spaces/{spaceId}/admins` | Header（手动检查） | `{ user_id, role? }` | 添加管理员（仅 owner） |
| DELETE | `/api/spaces/{spaceId}/admins/{userId}` | Header（手动检查） | — | 移除管理员（仅 owner） |
| POST | `/api/spaces/{spaceId}/transfer-ownership` | Header（手动检查） | `{ user_id }` | 转让 owner |

### 准入组

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| GET | `/api/spaces/{spaceId}/groups` | `@RequireSpaceAdmin` | — | 查看准入组 |
| POST | `/api/spaces/{spaceId}/groups` | `@RequireSpaceAdmin` | `{ group_id }` | 添加准入组 |
| DELETE | `/api/spaces/{spaceId}/groups/{groupId}` | `@RequireSpaceAdmin` | — | 移除准入组 |

### ACE 矩阵

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| GET | `/api/spaces/{spaceId}/aces` | `@RequireSpaceAdmin` | — | 查看 ACE。`?resource_type=kb` |
| POST | `/api/spaces/{spaceId}/aces` | `@RequireSpaceAdmin` | `{ resource_type?, resource_id, principal_type?, principal_id, role_id, effect?, priority? }` | 创建 ACE |
| PUT | `/api/spaces/{spaceId}/aces/{aceId}` | `@RequireSpaceAdmin` | `{ role_id?, effect?, priority? }` | 修改 ACE |
| DELETE | `/api/spaces/{spaceId}/aces/{aceId}` | `@RequireSpaceAdmin` | — | 删除 ACE |

### KB 管理

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| POST | `/api/spaces/{spaceId}/kbs` | `@RequireSpaceAdmin` | `{ name, description?, visibility? }` | 创建 KB |
| GET | `/api/spaces/{spaceId}/kbs` | `@RequireSpaceAdmin` | — | 列出 KB |
| PUT | `/api/spaces/{spaceId}/kbs/{kbId}` | Header（手动检查） | `{ name?, visibility? }` | 修改 KB |
| DELETE | `/api/spaces/{spaceId}/kbs/{kbId}` | Header（手动检查） | — | 删除 KB。`?permanent=true` 永久删除 |
| POST | `/api/spaces/{spaceId}/kbs/{kbId}/restore` | Header（手动检查） | — | 恢复 KB |

### 其他

| 方法 | 路径 | 认证 | 参数 | 说明 |
|------|------|------|------|------|
| GET | `/api/spaces/{spaceId}/trash` | `@RequireSpaceAdmin` | — | 回收站 |
| GET | `/api/spaces/{spaceId}/audit-logs` | `@RequireSpaceAdmin` | `?page=0&size=20` | 操作日志（分页） |

---

## 3. Groups — 用户组管理

**包**: `com.kes.auth.controller.GroupController`
**基础路径**: `/api/groups`

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/api/groups` | `{ name, description?, parent_group_id? }` | 创建组 |
| GET | `/api/groups` | — | 列出组。`?parent_id=uuid` 筛选子组 |
| GET | `/api/groups/{groupId}` | — | 查看组详情 |
| PUT | `/api/groups/{groupId}` | `{ name?, description?, parent_group_id?, is_system_admin? }` | 修改组 |
| DELETE | `/api/groups/{groupId}` | — | 删除组 |
| GET | `/api/groups/{groupId}/admins` | — | 查看管理员 |
| POST | `/api/groups/{groupId}/admins` | `{ user_id, role? }` | 添加管理员 |
| DELETE | `/api/groups/{groupId}/admins/{userId}` | — | 移除管理员 |
| GET | `/api/groups/{groupId}/members` | — | 查看成员 |
| POST | `/api/groups/{groupId}/members` | `{ user_id }` | 添加成员 |
| DELETE | `/api/groups/{groupId}/members/{userId}` | — | 移除成员 |

> 所有端点从 `Authorization` header 提取操作者 ID。

---

## 4. Roles — 角色管理

**包**: `com.kes.auth.controller.RoleController`
**基础路径**: `/api/roles`

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| GET | `/api/roles` | — | 列出所有角色 |
| GET | `/api/roles/{roleId}` | — | 查看角色详情 |
| POST | `/api/roles` | `{ name, description?, permissions }` | 创建自定义角色 |
| PUT | `/api/roles/{roleId}` | `{ name?, description?, permissions? }` | 修改角色（系统角色仅可改名） |
| DELETE | `/api/roles/{roleId}` | — | 删除角色（系统角色/被引用的不可删） |

**预置 4 个系统角色**: Admin（`kb.* + ace.manage`）、Editor（`kb.read + kb.write`）、Viewer（`kb.read`）、Deny（空权限）。

---

## 5. Admin — 全局管理

**包**: `com.kes.auth.controller.AdminController`
**基础路径**: `/api/admin`
**认证**: 全部 `@RequireGlobalAdmin`

### Space 管理

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| GET | `/api/admin/spaces` | — | 列出所有 Space |
| POST | `/api/admin/spaces/{spaceId}/archive` | — | 归档 Space |
| DELETE | `/api/admin/spaces/{spaceId}` | — | 软删除 Space |
| POST | `/api/admin/spaces/{spaceId}/restore` | — | 恢复 Space |

### 用户管理

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| GET | `/api/admin/users` | — | 列出所有用户 |
| POST | `/api/admin/users` | `{ username, display_name, email?, password? }` | 创建用户（不填密码则自动生成） |
| PUT | `/api/admin/users/{userId}` | `{ display_name?, email?, status? }` | 编辑用户 |
| PUT | `/api/admin/users/{userId}/status` | `{ status }` | 启用/禁用用户 |
| PUT | `/api/admin/users/{userId}/global-admin` | `{ is_global_admin }` | 设置/取消全局管理员 |
| POST | `/api/admin/users/batch` | `multipart/form-data { file }` | CSV 批量导入 |

### 检索反馈

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/api/admin/feedback/disliked` | `?source=web_chat&limit=10` | 查询被踩 Trace 详情 |

---

## 6. AdminModel — 模型配置管理

**包**: `com.kes.auth.controller.AdminModelController`
**基础路径**: `/api/admin/models`

### Provider

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| GET | `/api/admin/models/providers` | `@RequireGlobalAdmin` | — | 列出供应商（脱敏） |
| POST | `/api/admin/models/providers` | `@RequireGlobalAdmin` | `{ name, type, base_url, api_key_env?, is_enabled? }` | 添加供应商 |
| PUT | `/api/admin/models/providers/{id}` | `@RequireGlobalAdmin` | 同上 | 修改供应商 |
| DELETE | `/api/admin/models/providers/{id}` | `@RequireGlobalAdmin` | — | 删除供应商 |

### Model Config

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| GET | `/api/admin/models/configs` | `@RequireGlobalAdmin` | — | `?provider_id=uuid` 按供应商筛选 |
| POST | `/api/admin/models/configs` | `@RequireGlobalAdmin` | `{ provider_id, model_name, model_type, dimension?, max_tokens?, is_enabled? }` | 添加模型 |
| PUT | `/api/admin/models/configs/{id}` | `@RequireGlobalAdmin` | 同上 | 修改模型 |
| DELETE | `/api/admin/models/configs/{id}` | `@RequireGlobalAdmin` | — | 删除模型 |

### Assignment

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| GET | `/api/admin/models/assignments` | `@RequireGlobalAdmin` | — | 获取环节→模型映射 |
| PUT | `/api/admin/models/assignments` | `@RequireGlobalAdmin` | `{ assignments: {purpose: model_id} }` | 批量更新映射 |

### 发现与测试（代理到 Python）

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/admin/models/discover/{providerId}` | `@RequireGlobalAdmin` | 自动发现可用模型 |
| POST | `/api/admin/models/test/{providerId}` | `@RequireGlobalAdmin` | 连通性测试 |

### 配置文件（v12，代理到 Python）

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| GET | `/api/admin/models/config` | `@RequireGlobalAdmin` | — | 获取 models.yaml |
| PUT | `/api/admin/models/config` | `@RequireGlobalAdmin` | `{ yaml_content: "<JSON string>" }` | 更新 models.yaml |

### Python 内网专用

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/admin/models/active` | 无（内网调用） | Python 获取全部激活配置 |
| GET | `/api/admin/models/version` | 无（内网调用） | 配置版本号（热重载用） |

---

## 7. ApiKey — MCP 密钥管理

**包**: `com.kes.auth.controller.ApiKeyController`
**基础路径**: `/api/auth/mcp`

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| GET | `/api/auth/mcp/keys` | — | 列出当前用户的密钥 |
| POST | `/api/auth/mcp/keys` | `{ name?, expires_days?, scope_kb_ids? }` | 创建密钥（返回完整 key 仅一次） |
| PUT | `/api/auth/mcp/keys/{keyId}` | `{ name }` | 重命名密钥 |
| DELETE | `/api/auth/mcp/keys/{keyId}` | — | 撤销密钥 |
| POST | `/api/auth/mcp/keys/{keyId}/extend` | `{ expires_days? }` | 延期有效期 |
| PUT | `/api/auth/mcp/keys/{keyId}/scope` | `{ scope_kb_ids }` | 修改 KB 范围 |
| POST | `/api/auth/mcp/exchange` | `{ api_key, space_id }` | API Key → context_token（无需登录态） |

> 除 `/exchange` 外，其他端点从 `Authorization` header 提取用户 ID 做所有权校验。

---

## 8. Conversations — 会话管理

**包**: `com.kes.conversation.controller.ConversationController`
**基础路径**: `/api/conversations`

| 方法 | 路径 | 认证 | 参数 | 说明 |
|------|------|------|------|------|
| GET | `/api/conversations` | context_token（Space 成员） | `?kb_id=uuid`（可选） | 列出会话。不传 kb_id 则按 Space 列全部 |
| GET | `/api/conversations/{convId}/messages` | 无注解 | — | 获取历史消息 |
| DELETE | `/api/conversations/{convId}` | context_token（所有权校验） | — | 删除会话（级联删除消息） |

**消息结构**: `{ id, conversation_id, role: "user"|"assistant"|"system", content, tokens_used, sources, created_at }`

---

## 9. Chat — RAG 问答

**包**: `com.kes.rag.controller.ChatController`
**基础路径**: `/api`

### POST /api/chat
SSE 流式 RAG 问答。

| 项目 | 内容 |
|------|------|
| 认证 | `Authorization` header（context_token） |
| 请求体 | `{ "query": "string (必填)", "conversation_id": "uuid (可选，空则自动生成)", "kb_id": "uuid (可选)", "excluded_kb_ids": ["uuid"] (可选) }` |
| 响应 | `SseEmitter`（SSE 流） |
| 权限 | 自动解析用户有权限的 `kb_ids`，排除 `excluded_kb_ids` |

**SSE 数据格式**:
```
data: {"token": "文本块", "done": false}
data: {"token": "", "done": true, "sources": [...], "trace": {"trace_id": "..."}}
```

**超时链**: 前端 120s → Java SseEmitter 120s → Python LLM 110s

### POST /api/chat/feedback
提交检索质量反馈。

| 项目 | 内容 |
|------|------|
| 请求体 | `{ "trace_id": "string", "rating": "like"|"dislike", "reason": "string (可选)" }` |

---

## 10. Documents — 文档管理

**包**: `com.kes.document.controller.DocumentController`
**基础路径**: `/api/documents`

### 文档 CRUD

| 方法 | 路径 | 认证 | 参数/请求体 | 说明 |
|------|------|------|------------|------|
| GET | `/api/documents` | Header | `?kb_id=uuid&page=1&pageSize=20&status=active` | 分页列表 |
| GET | `/api/documents/{docId}` | 无注解 | — | 文档详情 |
| GET | `/api/documents/{docId}/file` | token 参数 | `?token=context_token` | 下载/预览（支持内联 PDF） |
| POST | `/api/documents` | Header | multipart: `{ file, kb_id, effective_date?, expiry_date?, version? }` | 上传文档 |
| PUT | `/api/documents/{docId}` | Header | multipart: `{ file }` | 更新文件 |
| PUT | `/api/documents/{docId}/metadata` | `@RequireSpaceAdmin` | `{ effective_date?, expiry_date?, version?, inherit_permissions? }` | 更新元数据 |
| DELETE | `/api/documents/{docId}` | Header（手动权限） | — | 软删除 |
| POST | `/api/documents/{docId}/restore` | `@RequireSpaceAdmin` | — | 恢复 |
| DELETE | `/api/documents/{docId}/permanent` | `@RequireSpaceAdmin` | — | 永久删除 |

### 审批

| 方法 | 路径 | 认证 | 请求体 | 说明 |
|------|------|------|--------|------|
| GET | `/api/documents/approvals` | `@RequireSpaceAdmin` | `?kb_id=uuid` | 待审批列表 |
| POST | `/api/documents/approvals/{approvalId}/approve` | `@RequireSpaceAdmin` | — | 审批通过 → 触发 ETL |
| POST | `/api/documents/approvals/{approvalId}/reject` | `@RequireSpaceAdmin` | `{ comment }` | 审批驳回 |

---

## 11. Health — 健康检查

**包**: `com.kes.common.controller.HealthController`

| 方法 | 路径 | 认证 | 响应 | 说明 |
|------|------|------|------|------|
| GET | `/api/health` | 无 | `ApiResponse<"ok">` | 健康检查 |

---

## 权限模型速查

### 三层身份

| 身份 | 判定 | 权限范围 |
|------|------|---------|
| 全局管理员 | `users.is_global_admin` 或所属组 `is_system_admin=true` | 所有 Space/KB |
| Space 管理员 | `space_admins` 表（owner/admin） | Space 内所有 KB |
| Space 成员 | `space_groups` 关联的组成员（含嵌套） | 由 ACE 矩阵决定 |
| API Key 持有者 | `api_keys` 表 + token 交换 | ACE 权限 ∩ Key scope_kb_ids |

### ACE 权限模型

```
effective_kb_ids = (空间内所有 KB 中，用户所属组被 ACE allow 的 KB)
                   ∪ (space_wide 的 KB，Space 成员自动可见)
                   − (ACE deny 显式排除的 KB)
```

### 端点数量统计

| Controller | 端点数 |
|------------|--------|
| AuthController | 8 |
| SpaceController | 21 |
| GroupController | 11 |
| RoleController | 5 |
| AdminController | 11 |
| AdminModelController | 16 |
| ApiKeyController | 7 |
| ConversationController | 3 |
| ChatController | 2 |
| DocumentController | 12 |
| HealthController | 1 |
| **总计** | **97** |
