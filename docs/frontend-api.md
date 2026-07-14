# 前端接口文档

> 基于 `frontend/src/api/index.js` 和 `frontend/src/router/index.js` 自动提取，版本 v12。

## 认证体系

### Token 类型

| Token | 存储位置 | 生命周期 | 用途 |
|-------|---------|---------|------|
| `refresh_token` | `localStorage` | 7 天 | 登录、刷新、列 Space、切换 Space |
| `context_token` | `localStorage` | 30 分钟 | 业务 API 调用（绑定 Space） |

### Token 自动注入规则

```
请求 URL                         → 使用 Token
──────────────────────────────────────────────────
/auth/login, /auth/register     → 不附加 Token
/auth/refresh                    → 不附加 Token
/auth/spaces, /auth/switch-space → refresh_token
其他所有 /auth/*, /*              → context_token（fallback refresh_token）
```

### 401 自动刷新流程

1. 任一 API 返回 401 → 拦截器用 `refresh_token` 调 `POST /auth/refresh`
2. 成功后更新 localStorage 中的 `refresh_token`，重放原请求
3. 刷新期间其他并发请求排队等待
4. `context_token` 过期 → 清除 localStorage 并跳转到 `/spaces`

### 错误码映射

| error_code | 处理方式 |
|-----------|---------|
| `AUTH_TOKEN_EXPIRED` | 清除所有 Token → 跳转 `/login` |
| `AUTH_NOT_LOGGED_IN` | 清除 context_token → 跳转 `/spaces` |
| `SPACE_ACCESS_DENIED` | `ElMessage.warning` |
| `KB_ACCESS_DENIED` | `ElMessage.warning` |
| 其他 | `ElMessage.error` |

---

## 路由结构

| 路径 | 视图 | 权限要求 |
|------|------|---------|
| `/login` | Login.vue | guest（已登录则跳转 `/spaces`） |
| `/spaces` | SpaceSwitcher.vue | 需登录 |
| `/groups` | GroupManagement.vue | 需登录 |
| `/roles` | RoleManagement.vue | 需登录 |
| `/app/:spaceId/chat` | Chat.vue | 需登录 + 需已选 Space |
| `/app/:spaceId/chat/:convId` | Chat.vue | 需登录 + 需已选 Space |
| `/app/:spaceId/documents` | Documents.vue | 需登录 + 需已选 Space |
| `/app/:spaceId/approvals` | Approvals.vue | 需 Space Admin |
| `/app/:spaceId/aces` | AceConfig.vue | 需登录 + 需已选 Space |
| `/app/:spaceId/settings` | SpaceSettings.vue | 需登录 + 需已选 Space |
| `/admin` | AdminDashboard.vue | 需全局管理员 |
| `/admin/feedback` | FeedbackDashboard.vue | 需全局管理员 |

### 路由守卫逻辑

```
guest + 已登录         → /spaces
requiresAuth + 未登录   → /login
requiresSpace + 未选Space → /spaces
requiresAdmin + 非Admin  → /app/:spaceId/documents
requiresGlobalAdmin + 非全局管理员 → /spaces
```

---

## API 接口

### 基础配置

- **baseURL**: `/api`
- **超时**: 30 秒
- **Content-Type**: `application/json`（文件上传用 `multipart/form-data`）

### 统一响应格式

```json
// 成功
{ "code": 0, "data": ... }

// 失败
{ "code": 非0, "error_code": "ERROR_CODE", "message": "错误描述" }
```

---

## 1. Auth API

### `authApi`

| 方法 | HTTP | 路径 | 说明 | Token |
|------|------|------|------|-------|
| `login(data)` | POST | `/auth/login` | 登录。body: `{username, password}`，返回 `{refresh_token, user, spaces}` | 无需 |
| `register(data)` | POST | `/auth/register` | 注册。body: `{username, password, display_name}` | 无需 |
| `getSpaces(rt)` | GET | `/auth/spaces` | 获取用户 Space 列表 | refresh_token |
| `switchSpace(sid, rt)` | POST | `/auth/switch-space` | 切换到指定 Space。body: `{space_id}`，返回 `{context_token, ...}` | refresh_token |
| `getAccessibleKBs()` | GET | `/auth/accessible-kbs` | 获取当前 Space 下可访问的 KB 列表 | context_token |
| `changePassword(data)` | PUT | `/auth/password` | 修改密码 | context_token |

---

## 2. Conversations API

### `conversationsApi`

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `list(params)` | GET | `/conversations` | 列出会话。query: `?kb_id=xxx`（可选，不传则按 Space 列全部） |
| `messages(convId, params?)` | GET | `/conversations/{convId}/messages` | 获取会话历史消息，可选 query 参数 |
| `delete(convId)` | DELETE | `/conversations/{convId}` | 删除会话（含所有权校验），DB 级联删除关联消息 |

**返回格式**:
```json
// list
{ "code": 0, "data": { "items": [{ "id": "uuid", "title": "...", "kb_id": "...", "space_id": "...", "status": "active", "message_count": 5, "updated_at": "..." }] } }

// messages
{ "code": 0, "data": { "items": [{ "id": 1, "role": "user|assistant|system", "content": "...", "sources": [...], "created_at": "..." }] } }
```

---

## 3. Chat API（SSE 流式）

### `chatSSE(query, conversationId, excludedKbIds, onToken, onDone, onError)`

- **端点**: `POST /api/chat`（原生 fetch，非 axios）
- **超时**: 首 Token 60s，总计 120s
- **返回**: `() => void` 取消函数

**请求体**:
```json
{
  "query": "用户输入",
  "conversation_id": "uuid 或空字符串",
  "excluded_kb_ids": ["kb-xxx"]
}
```

**SSE 数据格式**:
```
data: {"token": "文本块", "done": false}
data: {"token": "", "done": true, "sources": [...], "trace": {"trace_id": "..."}}
```

**回调说明**:

| 回调 | 触发时机 |
|------|---------|
| `onToken(chunk)` | 每收到一个 token。chunk: `{token, done, sources?, trace?}` |
| `onDone(chunk)` | 流式完成。chunk: `{done: true, sources: [...]}` |
| `onError(err)` | 超时或网络错误 |

### `submitFeedback(traceId, rating, reason = '')`

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| POST | `/chat/feedback` | body: `{trace_id, rating: "like"\|"dislike", reason}` |

---

## 4. Documents API

### `documentsApi`

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `list(params)` | GET | `/documents` | 分页列表。query: `?kb_id=xxx&page=0&size=20` |
| `upload(formData)` | POST | `/documents` | 上传文件。FormData: `{file, kb_id, effective_date?, expiry_date?, version?}` |
| `update(id, formData)` | PUT | `/documents/{id}` | 更新文件 |
| `delete(id)` | DELETE | `/documents/{id}` | 软删除（管理员） |
| `updateMetadata(id, data)` | PUT | `/documents/{id}/metadata` | 更新元数据。body: `{effective_date?, expiry_date?, version?}`（管理员） |
| `restore(id)` | POST | `/documents/{id}/restore` | 恢复软删除文档（管理员） |
| `permanentDelete(id)` | DELETE | `/documents/{id}/permanent` | 永久删除（管理员） |
| `getApprovals(params)` | GET | `/documents/approvals` | 待审批列表（管理员） |
| `approve(id)` | POST | `/documents/approvals/{id}/approve` | 审批通过 → 触发 ETL（管理员） |
| `reject(id, comment)` | POST | `/documents/approvals/{id}/reject` | 审批拒绝。body: `{comment}`（管理员） |
| `viewUrl(docId)` | — | `/documents/{id}/file?token=xxx` | 生成文件预览 URL |

---

## 5. Space 管理 API

### `spaceApi`

#### Space 生命周期

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `create(name, typeLabel, desc)` | POST | `/spaces` | 创建 Space。body: `{name, type_label, description}` |

#### 管理员

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `getAdmins(spaceId)` | GET | `/spaces/{spaceId}/admins` | 查看管理员列表 |
| `addAdmin(spaceId, userId, role)` | POST | `/spaces/{spaceId}/admins` | 添加管理员。body: `{user_id, role: "admin"}`（仅 owner） |
| `removeAdmin(spaceId, userId)` | DELETE | `/spaces/{spaceId}/admins/{userId}` | 移除管理员（仅 owner） |
| `transferOwnership(spaceId, userId)` | POST | `/spaces/{spaceId}/transfer-ownership` | 转让 owner。body: `{user_id}`（仅 owner） |

#### 准入组

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `getGroups(spaceId)` | GET | `/spaces/{spaceId}/groups` | 查看准入组 |
| `addGroup(spaceId, groupId)` | POST | `/spaces/{spaceId}/groups` | 添加准入组（admin） |
| `removeGroup(spaceId, groupId)` | DELETE | `/spaces/{spaceId}/groups/{groupId}` | 移除准入组（admin） |

#### ACE 矩阵

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `getAces(spaceId, resourceType)` | GET | `/spaces/{spaceId}/aces?resource_type=kb` | 查看 ACE 条目 |
| `createAce(spaceId, data)` | POST | `/spaces/{spaceId}/aces` | 创建 ACE。body: `{resource_type, resource_id, principal_type, principal_id, role_id, effect}`（admin） |
| `updateAce(spaceId, aceId, data)` | PUT | `/spaces/{spaceId}/aces/{aceId}` | 修改 ACE（admin） |
| `deleteAce(spaceId, aceId)` | DELETE | `/spaces/{spaceId}/aces/{aceId}` | 删除 ACE（admin） |

#### KB 管理

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `listKbs(spaceId)` | GET | `/spaces/{spaceId}/kbs` | 列出 KB |
| `createKb(spaceId, name, desc, visibility)` | POST | `/spaces/{spaceId}/kbs` | 创建 KB。body: `{name, description, visibility: "space_wide"\|"restricted"}`（admin） |
| `updateKb(spaceId, kbId, name, visibility)` | PUT | `/spaces/{spaceId}/kbs/{kbId}` | 修改 KB |
| `deleteKb(spaceId, kbId, permanent)` | DELETE | `/spaces/{spaceId}/kbs/{kbId}?permanent=true` | 删除 KB |
| `restoreKb(spaceId, kbId)` | POST | `/spaces/{spaceId}/kbs/{kbId}/restore` | 恢复 KB |
| `getTrash(spaceId)` | GET | `/spaces/{spaceId}/trash` | 回收站（admin） |
| `getAuditLogs(spaceId, page, size)` | GET | `/spaces/{spaceId}/audit-logs?page=0&size=20` | 操作日志（admin） |

---

## 6. 用户组 API

### `groupsApi`

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `list(params)` | GET | `/groups?parent_id=xxx` | 列出用户组 |
| `create(data)` | POST | `/groups` | 创建组 |
| `update(groupId, data)` | PUT | `/groups/{groupId}` | 修改组 |
| `delete(groupId)` | DELETE | `/groups/{groupId}` | 删除组 |
| `getMembers(groupId)` | GET | `/groups/{groupId}/members` | 查看组成员 |
| `addMember(groupId, userId)` | POST | `/groups/{groupId}/members` | 添加成员。body: `{user_id}` |
| `removeMember(groupId, userId)` | DELETE | `/groups/{groupId}/members/{userId}` | 移除成员 |
| `getAdmins(groupId)` | GET | `/groups/{groupId}/admins` | 查看组管理员 |
| `addAdmin(groupId, userId, role)` | POST | `/groups/{groupId}/admins` | 添加组管理员 |
| `removeAdmin(groupId, userId)` | DELETE | `/groups/{groupId}/admins/{userId}` | 移除组管理员 |

---

## 7. 角色 API

### `rolesApi`

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `list()` | GET | `/roles` | 列出所有角色 |
| `create(data)` | POST | `/roles` | 创建自定义角色 |
| `update(roleId, data)` | PUT | `/roles/{roleId}` | 修改角色（系统角色仅可改名） |
| `delete(roleId)` | DELETE | `/roles/{roleId}` | 删除角色 |

---

## 8. 全局管理员 API

### `adminApi`

#### Space 管理

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `getAllSpaces()` | GET | `/admin/spaces` | 列出所有 Space（全局管理员） |
| `archiveSpace(spaceId)` | POST | `/admin/spaces/{spaceId}/archive` | 归档 Space |
| `deleteSpace(spaceId)` | DELETE | `/admin/spaces/{spaceId}` | 软删除 Space |
| `restoreSpace(spaceId)` | POST | `/admin/spaces/{spaceId}/restore` | 恢复 Space |

#### 用户管理

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `listUsers()` | GET | `/admin/users` | 列出所有用户 |
| `createUser(data)` | POST | `/admin/users` | 创建用户 |
| `updateUser(userId, data)` | PUT | `/admin/users/{userId}` | 编辑用户 |
| `setUserStatus(userId, status)` | PUT | `/admin/users/{userId}/status` | 启用/禁用。body: `{status}` |
| `setGlobalAdmin(userId, bool)` | PUT | `/admin/users/{userId}/global-admin` | 设置全局管理员。body: `{is_global_admin}` |
| `batchImportUsers(formData)` | POST | `/admin/users/batch` | CSV 批量导入（multipart/form-data） |

#### 检索反馈

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `getFeedbackDisliked(source = 'web_chat', limit = 10)` | GET | `/admin/feedback/disliked?source=web_chat&limit=10` | 查询被踩 Trace 详情 |

---

## 9. 模型配置 API（v6）

### `modelAdminApi`

#### Provider

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `listProviders()` | GET | `/admin/models/providers` | 列出供应商（脱敏） |
| `createProvider(data)` | POST | `/admin/models/providers` | 添加供应商 |
| `updateProvider(id, data)` | PUT | `/admin/models/providers/{id}` | 修改供应商 |
| `deleteProvider(id)` | DELETE | `/admin/models/providers/{id}` | 删除供应商 |

#### Model Config

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `listConfigs(providerId)` | GET | `/admin/models/configs?provider_id=xxx` | 列出供应商下的模型 |
| `createConfig(data)` | POST | `/admin/models/configs` | 添加模型 |
| `updateConfig(id, data)` | PUT | `/admin/models/configs/{id}` | 修改模型 |
| `deleteConfig(id)` | DELETE | `/admin/models/configs/{id}` | 删除模型 |

#### Assignment

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `getAssignments()` | GET | `/admin/models/assignments` | 获取环节→模型映射 |
| `updateAssignments(data)` | PUT | `/admin/models/assignments` | 批量更新映射 |

#### 发现 & 测试

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `discover(providerId)` | POST | `/admin/models/discover/{providerId}` | 模型自动发现 |
| `test(providerId)` | POST | `/admin/models/test/{providerId}` | 连通性测试 |

#### 配置文件读写（v12）

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `getConfig()` | GET | `/admin/models/config` | 获取 models.yaml 完整配置 |
| `updateConfig(yaml)` | PUT | `/admin/models/config` | 更新 models.yaml。body: `{yaml_content: "<JSON string>"}`，30s 内热重载生效 |

---

## 10. 其他 API

### `userApi`

| 方法 | HTTP | 路径 | 说明 |
|------|------|------|------|
| `search(query)` | GET | `/auth/users/search?q=xxx` | 按用户名前缀搜索用户 |

---

## 状态管理

### localStorage 键

| 键 | 内容 | 设置时机 |
|----|------|---------|
| `refresh_token` | JWT refresh token | 登录/刷新后 |
| `context_token` | JWT context token | 切换 Space 后 |
| `user` | 用户信息 JSON | 登录后 |
| `spaces` | Space 列表 JSON | 登录后 |
| `active_space` | 当前活跃 Space JSON | 切换 Space 后 |

### Pinia Store (`auth.js`)

```
authStore
├── isLoggedIn         → !!localStorage.refresh_token
├── spaces             → 用户所有 Space
├── activeSpace        → 当前选中的 Space
├── hasActiveSpace     → !!activeSpace
├── currentRole        → 当前 Space 中的角色
├── isSpaceAdmin       → role === 'owner' || 'admin'
├── isGlobalAdmin      → user.is_global_admin
├── login()            → 调用 authApi.login → 存储 Token
├── logout()           → 清除所有 localStorage
├── switchSpace()      → 调用 authApi.switchSpace → 存储 context_token
└── getEffectiveKbIds() → 从 activeSpace 计算可访问 KB 列表
```

---

## 前端调用示例

### 典型 RAG 问答流程

```javascript
// 1. 用户在 Chat.vue 输入问题
// 2. useChatSSE.send(text) 被调用
// 3. 如果无 convId → generateUUID() → router.push 新路由
// 4. chatSSE(query, convId, excludedKbIds, onToken, onDone, onError)
//    → POST /api/chat (SSE)
//    → onToken 逐块更新 messages[assistantIdx].content
//    → onDone 时触发 loadConversations() 刷新侧栏列表
// 5. 流结束后调用 onConversationsChanged 回调

// 6. 用户可提交反馈:
submitFeedback(traceId, 'like', '')
```

### 会话删除流程

```javascript
// 1. 用户 hover ConversationList 中某条 → 出现红色删除图标
// 2. 点击 → confirmDelete(name) → 弹出确认框
// 3. 确认 → conversationsApi.delete(convId)
// 4. 如果删除的是当前对话 → router.push('/app/:spaceId/chat')
// 5. loadConversations() 刷新列表
```

### 模型配置更新流程

```javascript
// 1. ModelManagement.vue 中编辑配置
// 2. saveConfig() 构建 JS 对象 → JSON.stringify(raw) → JSON 字符串
// 3. modelAdminApi.updateConfig(jsonString)
//    → PUT /api/admin/models/config  { yaml_content: "<JSON string>" }
//    → Java 转发 Python → yaml.safe_load() 解析 → 写入 models.yaml
//    → 30s 内 Python 热重载生效
```
