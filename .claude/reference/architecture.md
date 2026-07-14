# 架构详解

ACE 权限模型、JWT 双 Token、SSE 格式、超时链、文档审批流、Redis 缓存。

> 从 CLAUDE.md 提取，原始行范围: L138-L331

## Architecture: Responsibility Split (v4 重构后)

Two-backend system with strict boundaries. 跨模块副作用通过 Spring Events（Java）和 PipelineStep 链（Python）解耦。

**Java Backend owns:**
- All PostgreSQL writes (users, spaces, knowledge_bases, user_groups, roles, space_admins, space_groups, access_control_entries, conversations, messages, document_meta, approvals)
- JWT authentication (dual-token: refresh_token + context_token)
- ACE-based permission resolution: computes `kb_ids` list from space_admins + space_groups + ACE entries + group hierarchy expansion
- Building `FilterParams(kb_ids)` from resolved permissions
- MinIO file upload/delete
- SSE stream relay: Python SSE → strip `data:` prefix → forward to frontend
- Saving `assistant` messages to PostgreSQL after SSE stream completes
- Document approval workflow
- kb_ids permission caching (Redis, 5min TTL)
- ★ v12: 检索反馈查询 — `FeedbackService` 从 `retrieval_feedback` 表读取 Trace/Judge 数据
- **v4 重构**: 跨模块副作用通过 Spring `ApplicationEventPublisher` 发布事件，由各自模块的 `@EventListener` 处理

**Python AI Service owns:**
- Embedding generation & pgvector vector search (HNSW 索引)
- LLM invocation (streaming via OpenAI-compatible API)
- Document ETL pipeline: MinIO download → parsing/ (结构化解析) → chunking/ (语义分块) → **LlmMetadataEnrich** (LLM 元数据提取) → embedding → pgvector insert
- Context assembly (system prompt + summary + Java-forwarded history + retrieval results)
- Hybrid search (Dense HNSW ∥ Sparse BM25 → RRF fusion, TraceContext nested spans) — ★ v12 两路检索 + 追踪
- Reranker (API → Cross-Encoder (BGE-Reranker-v2-m3) → LLM 降级 → 截断)
- QueryPlanner (单次 LLM → complexity + DAG 拆解 + keywords + top_k) — Web Chat 专用
- Query preprocessing (QueryPreprocessor — 三合一 SLM 指代消解+省略补全+语义约束) — Web Chat 专用
- DAGExecutor (拓扑排序 → wave 并行 → HyDE 假答案生成 + 3D 提取 → 熔断) — Web Chat 专用
- MCP query preparation (McpQueryPreparator — jieba entity extraction + focus_aspects mapping, zero LLM) — MCP 专用，纯本地 ~5ms
- Retrieval execution layer (HybridSearch + Reranker + Critic) — **Web Chat 与 MCP 共享**
- Citation insertion with monotonic constraint (引用标注+位置约束)
- Retrieval trace + Judge evaluation (RetrievalTracer → PG + JudgeEvaluator 四维评估：忠实度/答案相关性/上下文相关性/答案正确性) — ★ v12 质量追踪
- Semantic Cache (Redis 高频查询拦截, ~5ms) — ★ v12
- TraceContext 统一追踪 (SpanHandle/SpanSnapshot → Langfuse span 树 + DB trace dict)
- Model Pool (从 models.yaml 读配置，30s mtime 热重载，降级到 Java HTTP)
- Model auto-discovery & connectivity test (供 Java `/api/admin/models/*` 代理)

**Python must NEVER:**
- Write to PostgreSQL business tables
- Validate JWT tokens or manage users
- Build its own permission filters (must use Java-provided `filter_params.kb_ids` verbatim)

**Java must NEVER:**
- Call pgvector or vector database directly
- Call LLM or Embedding APIs directly
- Perform document parsing/chunking/sanitization

### v4 ACE: Enterprise Access Control Model

Core principle: **"成员归属于用户组，文档归属于KB，管理员配置用户组与KB之间的关系（带上角色）"**

```
user_identities (v9: 外部IdP绑定)    api_keys (v8: MCP密钥)
       │                                  │
       │  user_id                         │  user_id
       ▼                                  ▼
user_groups (全局可嵌套)           roles (可自定义权限套餐)
       │                                  │
       ├── space_groups ──→ Space ←── space_admins (owner/admin)
       │                                  │
       └── ACE ──→ KB (visibility: space_wide | restricted)
                          │
                          └── Document (inherit_permissions, Phase 3)
```

**Three-layer identity model:**

| 身份 | 判定方式 | 权限范围 |
|------|---------|---------|
| 全局超级管理员 | `users.is_global_admin` 或所属组 `is_system_admin=true` | 所有 Space 的所有 KB |
| Space 管理员 | `space_admins` 表直接关联 User（owner/admin 两级） | Space 管理权 |
| Space 普通成员 | 通过 `space_groups` 关联的全局用户组（含嵌套展开） | KB 访问权由 ACE 决定 |

- **用户组（全局可嵌套）**: `user_groups` + `user_group_members`，支持 `parent_group_id` 层级
- **Space 管理员**: `space_admins` 直接关联 User — owner（可删 Space/转让）和 admin（可管 KB/准入组）
- **Space 准入**: `space_groups` 将全局用户组分配到 Space，组成员自动成为 Space 成员
- **ACE 矩阵**: `access_control_entries(space_id, resource_type, resource_id, principal_type, principal_id, role_id, effect)` — allow/deny，deny 始终覆盖 allow
- **角色**: `roles(permissions JSONB)` — 预置 Admin/Editor/Viewer/Deny 四种系统角色，管理员可自定义
- **KB visibility**: `space_wide` 对所有 Space 成员自动可见（便捷快捷方式）
- **组嵌套继承**: 子组成员自动继承父组权限（向上展开 `parent_group_id` 链）
- **文档级权限**: Phase 3 预留 `inherit_permissions` 字段
- **软删除**: Space/KB/Document 均支持（`deleted_at`）
- **审计日志**: `admin_action_logs` 记录所有管理操作
- **★ v9 企业扩展**: `users.metadata` / `spaces.metadata` / `knowledge_bases.metadata` JSONB 列 + `user_identities` 外部身份绑定表 — 为对接企业 OA/LDAP/OIDC 铺路
- **★ v8 MCP 知识服务**: API Key → JWT 交换 → `kes_mcp/` stdio Server，对外部 Agent 提供权限穿透的知识检索

**Permission resolution (核心算法):**
```
resolveAccessibleKbIds(spaceId, userId):
  1. 全局管理员 → 全量返回
  2. expandUserEffectiveGroups(userId) → 用户有效组（含嵌套上溯）
  3. 计算 Space 身份: space_admins? space_groups ∩ effectiveGroups?
  4. Space admin → 所有 KB 可见
  5. space_wide KBs → 自动加入结果
  6. 查询 ACE: allow → 加入，deny → 移除（deny 覆盖 allow）
  7. Redis 缓存 (5min TTL)
```

Key files (v4 重构后 — AuthService 已拆分为 7 个独立 Service):
- `backend/.../auth/service/AuthService.java` — 认证核心（register/login/refresh/changePassword/switchSpace/getSpaces）
- `backend/.../auth/service/SpaceService.java` — Space 生命周期 + 管理员 (space_admins) + 准入组 (space_groups)
- `backend/.../auth/service/KbService.java` — KB 全生命周期管理（CRUD + 软删除/恢复/永久删除 + 回收站）
- `backend/.../auth/service/AceService.java` — ACE 矩阵管理（access_control_entries CRUD）
- `backend/.../auth/service/PermissionQueryService.java` — KB/文档权限查询（resolveAccessibleKbIds / resolveAccessibleDocIds）
- `backend/.../auth/service/AdminService.java` — 全局管理员操作（Space/用户管理 + v7 用户 CRUD + 批量导入 + 审计日志查询）
- `backend/.../auth/service/ApiKeyService.java` — ★ v8: MCP API 密钥管理（创建/撤销/重命名/验证/exchange）
- `backend/.../auth/service/PermissionService.java` — 统一权限校验（三层：全局管理员/Space管理员/Space成员）
- `backend/.../auth/service/GroupService.java` — 用户组 CRUD + 层级展开
- `backend/.../auth/service/RoleService.java` — 角色 CRUD + 系统角色保护
- `backend/.../common/service/AuditLogger.java` — 统一审计日志（发布 AuditLogEvent）
- `backend/.../common/event/` — 跨模块事件记录（KbSoftDeletedEvent, DocumentStatusChangedEvent 等 6 个）
- `backend/.../common/dto/SpaceDtos.java` — 12 种响应 DTO 类型，替代手写 HashMap
- `backend/.../auth/event/AuditEventListeners.java` — 审计日志事件监听（持久化 AdminActionLog）
- `backend/.../auth/event/KbCleanupEventListeners.java` — KB/文档永久删除时清理 ACE 条目
- `backend/.../document/event/DocumentEventListeners.java` — KB 生命周期→文档级联操作
- `backend/.../rag/event/AiSyncEventListeners.java` — 文档状态变更→Python AI 服务同步

**Design principles:**
- 普通成员靠组批量管理，管理员靠人精准指派
- Annotations are **coarse entry gates** at the Controller layer
- `PermissionService` does the authoritative DB check
- `createKb` / ACE 管理 → Space admin (查 `space_admins`)
- Owner 特有操作（删 Space、转让、管理 admin）→ `requireSpaceOwner()`
- File download verifies Space membership via `PermissionService.requireSpaceMember()`

**★ `getUserSpaceRole` 修复 (2026-06-28):**
全局管理员不再无条件返回 `"owner"`。新判定顺序：`space_admins` 显式角色 → 全局管理员回退 `"admin"` → `space_groups` 成员 → null。所有 `requireSpaceOwner`/`requireSpaceAdmin`/`hasPermission` 均独立检查 `isGlobalAdmin`，权限不受角色标签影响。

**Owner vs Admin 权限差异:**
- Owner 独有：`addSpaceAdmin`、`removeSpaceAdmin`、`transferOwnership`（管人）
- Admin 可做：KB CRUD、ACE 管理、准入组管理、归档 Space（管事）
- 全局管理员旁路所有检查（`isGlobalAdmin` return early）

### Inter-service Communication

1. **Sync (HTTP):**
   - Java POST → `http://python:8000/v1/chat` with `{query, filter_params: {kb_ids: [...]}, conversation_id, history_messages, top_k}`. Python returns SSE stream.
   - Java POST → `http://python:8000/v1/documents/status` — sync document status (active/soft_deleted) to `knowledge_chunks` table.
   - Java DELETE → `http://python:8000/v1/documents/{docId}/chunks` — permanently delete all vector chunks for a document.
2. **Async (RabbitMQ):** Java publishes `document.ingest` messages → Python consumes, runs ETL, publishes `document.ingest.callback` → Java updates `document_meta.ingest_status`.
3. **★ v12 检索反馈 (共享 PG):** Python `RetrievalTracer` 写入 `retrieval_feedback` 表（Trace + Judge 评分）→ Java `FeedbackService` 读取供前端展示 → 用户通过 `POST /api/chat/feedback` 提交 like/dislike → Python/Java 均可 UPDATE 反馈字段。

### Security: `filter_params` Field

`filter_params` is a **security red line**. Python validates non-null and returns 400 if missing. Java computes the `kb_ids` list, Python mechanically builds `WHERE kb_id = ANY($1)`. Python never makes permission decisions.

### JWT Dual-Token Scheme

| Token | Lifetime | Contains | Used For |
|-------|----------|----------|----------|
| `refresh_token` | 7 days | `{sub: userId, type: "refresh"}` | login, refresh, listing spaces, switch-space |
| `context_token` | 30 minutes | `{sub: userId, space_id, role}` | all business API calls |

The `JwtFilter` accepts both token types. Refresh Token used for auth endpoints (`/api/auth/spaces`, `/api/auth/switch-space`), Context Token for business endpoints.

### SSE Data Format

```
data: {"token": "text", "done": false}
data: {"token": "", "done": true, "sources": [...]}
```

### ★ SSE 错误处理三层防护 (2026-06-28)

问答失败时不再返回空白。三层各自兜底：

| 层 | 文件 | 防护 |
|----|------|------|
| **Python** | `api/chat.py` | 异常区分 5 类（认证失败/模型不存在/超时/连接失败/通用），错误消息作为 token 发送；`finally` 确保 sources 不丢失 |
| **Java** | `ChatController.java` | `handleSseComplete` 检测空 content → 发送 JSON 错误提示；`saveAssistantMessage` 空值写入兜底文案 |
| **前端** | `useChatSSE.js` | `done` 事件时检查 content 是否为空 → 注入兜底提示 "抱歉，AI 服务暂不可用，请稍后重试。" |

### Timeout Chain

Frontend (120s total, 60s first-token) → Java (120s SSE, 120s read, 30s write) → Python (110s LLM stream).

### Document Approval Flow

1. User uploads document → stored in MinIO, `DocumentMeta` created (admin uploads: `approved` directly; member uploads: `pending`)
2. Admin reviews → POST `/api/documents/approvals/{id}/approve` or `/reject` (**仅管理员**)
3. On approval → Java publishes `document.ingest` to RabbitMQ → Python ETL pipeline runs → callback updates `ingest_status` to `COMPLETED`

### Redis: kb_ids Permission Cache

```
Key:    kes:user:{userId}:kb_ids:{spaceId}     (Set, TTL 300s)
Aux:    kes:space:{spaceId}:user_ids           (Set, TTL 300s)
```

Cache hit: returns cached kb_ids. Miss: computes from space_admins + space_groups + ACE entries + group hierarchy expansion, writes back to Redis.
Invalidated on: KB visibility change, member add/remove, KB create/delete.

### File Download / Preview

`GET /api/documents/{docId}/file?token={context_token}` — streams file from MinIO through backend. PDF opens inline; other formats trigger download.

