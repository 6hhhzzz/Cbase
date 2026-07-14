# API 端点参考

所有 REST API 端点列表，含方法、路径、说明。

> 从 CLAUDE.md 提取，原始行范围: L675-L862

## API Endpoint Summary

### Auth (`/api/auth`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register user, auto-join default Space as owner |
| POST | `/api/auth/login` | Login, returns refresh_token + user spaces |
| POST | `/api/auth/refresh` | Rotate refresh_token |
| GET | `/api/auth/spaces` | List user's Spaces (requires refresh_token) |
| POST | `/api/auth/switch-space` | Issue 30-min context_token for selected Space |
| GET | `/api/auth/accessible-kbs` | List accessible KBs in current Space (requires context_token) |
| GET | `/api/auth/users/search?q={prefix}` | Search users by name prefix (for member invitation) |

#### MCP API 密钥 (`/api/auth/mcp`) ★ v8
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/mcp/keys` | 列出当前用户的 API 密钥 |
| POST | `/api/auth/mcp/keys` | 创建密钥 → 返回完整 key（仅一次）+ 配置代码块 |
| PUT | `/api/auth/mcp/keys/{id}` | 重命名密钥 |
| DELETE | `/api/auth/mcp/keys/{id}` | 撤销密钥 |
| POST | `/api/auth/mcp/exchange` | API Key → context_token + refresh_token（无需登录态） |

### Chat (`/api/chat`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | RAG chat via SSE (resolves kb_ids from JWT, saves messages) |
| POST | `/api/chat/feedback` | ★ v12: 提交检索质量反馈（trace_id + rating like/dislike + reason） |

### Conversations (`/api/conversations`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/conversations` | List conversations in KB (kb_id param) |
| GET | `/api/conversations/{id}/messages` | Get messages |
| DELETE | `/api/conversations/{id}` | Delete (ownership check) |

### Documents (`/api/documents`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/documents` | Paginated list — kb_id 可选，不传则查全 space（KB 标签列展示所属 KB） |
| POST | `/api/documents` | Upload (file + kb_id + optional effective_date/expiry_date/version → MinIO + MQ + approval). 管理员直接入库，成员走审批。 |
| GET | `/api/documents/{id}` | Single document detail |
| GET | `/api/documents/{id}/file` | Download/preview file |
| PUT | `/api/documents/{id}` | Update file (admin: direct, member: approval) |
| PUT | `/api/documents/{docId}/metadata` | Edit effective_date / expiry_date / version (**仅管理员**) |
| DELETE | `/api/documents/{id}` | Soft delete — 有 kb.delete 权限直接删，否则提交审批 |
| DELETE | `/api/documents/batch` | ★ 批量软删除 — 逐文档检查权限，返回 {deleted: [...], pending_approval: [...]} |
| DELETE | `/api/documents/batch/permanent` | ★ 批量永久删除（**仅 Space Admin**） |
| POST | `/api/documents/{docId}/restore` | Restore soft-deleted document (**仅管理员**) |
| DELETE | `/api/documents/{docId}/permanent` | Permanent delete (MinIO + Python chunks) (**仅管理员**) |
| GET | `/api/documents/approvals` | Pending approvals (**仅管理员**) |
| POST | `/api/documents/approvals/{id}/approve` | Approve → triggers ETL (**仅管理员**) |
| POST | `/api/documents/approvals/{id}/reject` | Reject with comment (**仅管理员**) |

### Space 管理 (`/api/spaces`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/spaces` | 创建新 Space（任何登录用户，创建者成为 owner） |
| POST | `/api/spaces/{spaceId}/archive` | 归档 Space（admin only） |
| GET | `/api/spaces/{spaceId}/members` | 查看 Space 成员（管理员列表 + 准入组列表） |
| GET | `/api/spaces/{spaceId}/admins` | 查看 Space 管理员 |
| POST | `/api/spaces/{spaceId}/admins` | 添加管理员（仅 owner） |
| DELETE | `/api/spaces/{spaceId}/admins/{userId}` | 移除管理员（仅 owner） |
| POST | `/api/spaces/{spaceId}/transfer-ownership` | 转让 owner（仅 owner） |
| GET | `/api/spaces/{spaceId}/groups` | 查看 Space 准入组 |
| POST | `/api/spaces/{spaceId}/groups` | 分配用户组到 Space（admin only） |
| DELETE | `/api/spaces/{spaceId}/groups/{groupId}` | 移除准入组（admin only） |
| GET | `/api/spaces/{spaceId}/aces` | 查看 ACE 矩阵（?resource_type=kb） |
| POST | `/api/spaces/{spaceId}/aces` | 创建 ACE 条目（admin only） |
| PUT | `/api/spaces/{spaceId}/aces/{aceId}` | 修改 ACE（admin only） |
| DELETE | `/api/spaces/{spaceId}/aces/{aceId}` | 删除 ACE（admin only） |
| POST | `/api/spaces/{spaceId}/kbs` | 创建 KB（admin only） |
| GET | `/api/spaces/{spaceId}/kbs` | 列出 KB |
| PUT | `/api/spaces/{spaceId}/kbs/{kbId}` | 修改 KB |
| DELETE | `/api/spaces/{spaceId}/kbs/{kbId}` | 软删除 KB（?permanent=true 永久删除） |
| POST | `/api/spaces/{spaceId}/kbs/{kbId}/restore` | 恢复 KB |
| GET | `/api/spaces/{spaceId}/trash` | 查看回收站（admin only） |
| GET | `/api/spaces/{spaceId}/audit-logs` | 操作日志（admin only, 分页） |

### 用户组管理 (`/api/groups`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/groups` | 创建全局用户组 |
| GET | `/api/groups` | 列出用户组（?parent_id= 筛选子组） |
| GET | `/api/groups/{id}` | 查看组详情 |
| PUT | `/api/groups/{id}` | 修改组 |
| DELETE | `/api/groups/{id}` | 删除组 |
| GET | `/api/groups/{id}/members` | 查看组成员 |
| POST | `/api/groups/{id}/members` | 添加成员 |
| DELETE | `/api/groups/{id}/members/{userId}` | 移除成员 |

### 角色管理 (`/api/roles`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/roles` | 列出所有角色 |
| GET | `/api/roles/{id}` | 查看角色详情 |
| POST | `/api/roles` | 创建自定义角色 |
| PUT | `/api/roles/{id}` | 修改角色（系统角色仅可改名） |
| DELETE | `/api/roles/{id}` | 删除角色（系统角色/被引用的不可删） |

### 全局管理 (`/api/admin`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/spaces` | 列出所有 Space（**仅全局管理员**） |
| POST | `/api/admin/spaces/{spaceId}/archive` | 归档 Space |
| DELETE | `/api/admin/spaces/{spaceId}` | 软删除 Space |
| POST | `/api/admin/spaces/{spaceId}/restore` | 恢复 Space |

#### 用户管理 (`/api/admin/users`) ★ v7
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/users` | 列出所有用户 |
| POST | `/api/admin/users` | 管理员创建单个用户 |
| PUT | `/api/admin/users/{id}` | 编辑用户（displayName/email/status） |
| PUT | `/api/admin/users/{id}/status` | 启用/禁用用户 |
| PUT | `/api/admin/users/{id}/global-admin` | 设置/取消全局管理员 |
| POST | `/api/admin/users/batch` | CSV 批量导入用户 |

#### 检索反馈 (`/api/admin/feedback`) ★ v12
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/feedback/disliked?source=web_chat&limit=10` | 查询最近被踩 Trace 详情（**仅全局管理员**） |

#### 模型配置管理 (`/api/admin/models`) ★ v6
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/models/providers` | 列出供应商（脱敏） |
| POST | `/api/admin/models/providers` | 添加供应商 |
| PUT | `/api/admin/models/providers/{id}` | 修改供应商 |
| DELETE | `/api/admin/models/providers/{id}` | 删除供应商 |
| GET | `/api/admin/models/configs?provider_id=` | 模型列表 |
| POST | `/api/admin/models/configs` | 添加模型 |
| PUT | `/api/admin/models/configs/{id}` | 修改模型 |
| DELETE | `/api/admin/models/configs/{id}` | 删除模型 |
| GET | `/api/admin/models/assignments` | 获取环节→模型映射 |
| PUT | `/api/admin/models/assignments` | 批量更新映射 |
| POST | `/api/admin/models/discover/{providerId}` | 模型自动发现 |
| POST | `/api/admin/models/test/{providerId}` | 连通性测试 |
| GET | `/api/admin/models/config` | ★ v12: 获取 models.yaml 配置（全局管理员） |
| PUT | `/api/admin/models/config` | ★ v12: 更新 models.yaml 配置（全局管理员） |
| GET | `/api/admin/models/active` | **Python 用**：获取全部激活配置（保留兼容） |
| GET | `/api/admin/models/version` | 配置版本号（热重载用，保留兼容） |

### Python AI (`/v1`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat` | SSE RAG endpoint (kb_ids in filter_params) |
| GET | `/v1/health` | Component health check |
| POST | `/v1/documents/status` | Sync document status to knowledge_chunks (internal, Java-triggered) |
| DELETE | `/v1/documents/{doc_id}/chunks` | Permanently delete document's vector chunks (internal, Java-triggered) |
| POST | `/v1/admin/models/discover` | ★ v6: 模型发现（供 Java 代理） |
| GET | `/v1/admin/models/config` | ★ v12: 获取当前 models.yaml（JSON 格式） |
| PUT | `/v1/admin/models/config` | ★ v12: 更新 models.yaml（JSON/YAML 双格式，校验+原子写入） |
| POST | `/v1/admin/models/test` | ★ v6: 连通性测试（供 Java 代理） |

### MCP 知识服务 ★ v8
MCP stdio Server — 启动: `KES_API_KEY=xxx KES_SPACE_ID=sp-001 python -m kes_mcp.server`

以外部 Agent 为一等公民设计。**核心设计：Agent 先用 Resource 读"知识地图"（entities/structure/time_range），再用 Tool 精确检索——不是盲搜。**

| Tool (1) | 参数 | 说明 |
|----------|------|------|
| `search_chunks` | query, kb_ids, top_k, include_context, **context_hint**, **focus_aspects**, **doc_type**, **time_range** | 混合检索文档块 → 结构化元数据（来源/页码/版本/有效期/is_expired）。**纯检索，不调 LLM**。30s 超时，信号量限 5 并发 |
| `report_quality` | trace_id, rating(like/dislike), reason | ★ v12: 上报检索质量反馈，更新 retrieval_feedback 表 |

★ search_chunks 新增参数（让 Agent 基于先验信息精确检索）：
- `context_hint`: Agent 已知的用户背景，不参与检索，仅注入 LLM 生成阶段（ask_expert 已移除，此参数保留供未来扩展）
- `focus_aspects`: 限定关注方面（installation/configuration/troubleshooting/api_reference/best_practices/security/version_history）
- `doc_type`: 限定文档类型（manual/policy/report/guide/specification/any）
- `time_range.expired`: 过期文档策略 — "exclude"(默认排除) | "include"(新旧混合) | "only"(仅查历史版本)

| Resource (5) | URI | 数据来源 | 说明 |
|-------------|-----|---------|------|
| 知识库目录 | `doc://catalog` | Java API → ACE 权限解析 | 有权限的 KB 列表（名称、文档数、可见性） |
| 实体索引 | `doc://kb/{kb_id}/entities` | `knowledge_chunks.metadata` JSONB | 标题/产品名、版本号(doc_version列)、技术术语——Agent用这些精确术语构造query |
| 文档结构树 | `doc://kb/{kb_id}/structure` | `knowledge_chunks.metadata` JSONB | 每个文档的章节标题+层级，按文档分组，Agent据此定位信息所在文档 |
| 时间跨度 | `doc://kb/{kb_id}/time_range` | `knowledge_chunks` 日期列聚合 | 最早/最新生效日期、过期文档数、is_actively_maintained标志 |
| 文档元数据 | `doc://{doc_id}/meta` | Java API → document_meta 表 | 单文档的文件名/类型/版本/有效期/状态——Agent验证来源可信度 |

**Resource 设计原则**：所有 Resource 零 LLM 调用（纯 SQL 或 HTTP API），数据在 ETL 入库时由 MetadataEnrichStep 预先计算存入 `knowledge_chunks.metadata` JSONB 列——不是运行时正则猜测。

| Prompt (3) | 类型 | 说明 |
|------------|------|------|
| **`kb_search_strategy`** | ★ 行为指导 | "先看地图再搜"——教 Agent 先读 catalog→entities→structure 了解知识库，再用精确术语调 search_chunks；含时效性指导 |
| `qa_template` | 结果使用 | 标准 RAG 问答输出模板（如何使用检索结果） |
| `document_analysis` | 结果使用 | 文档分析模板（核心要点/风险/建议） |

**检索链路**: `McpQueryPreparator.prepare()`（jieba 实体提取，+5ms，零 LLM） → `RetrievalOrchestrator.execute()`（共享执行层：HybridSearch + Reranker）

**依赖**: `mcp` SDK, `httpx`, `jieba`, 复用 `RetrievalOrchestrator.execute()` + `ContextAssembler`

