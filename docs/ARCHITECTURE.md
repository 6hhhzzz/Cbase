# 企业知识助手 (KES) — 系统架构文档

> 最后更新: 2026-06-26
> 版本: v9 (企业 JSONB 扩展 + MCP 知识服务)

---

## 1. 系统总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                        外部 AI Agent / MCP Client                     │
│                   (Claude Desktop / Cursor / Continue)                 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ MCP Protocol (stdio)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ┌───────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │   Vue 3 Frontend  │  │  Java Backend    │  │  Python AI Service │  │
│  │   Port :5173      │  │  Port :8080      │  │  Port :8000        │  │
│  │                   │  │                  │  │                    │  │
│  │  Element Plus     │  │  Spring Boot 3   │  │  FastAPI            │  │
│  │  Pinia Store      │◄─┤  JPA + Security  │◄─┤  pgvector + LLM    │  │
│  │  Axios + SSE      │  │  JWT Dual Token  │  │  RAG Pipeline      │  │
│  │                   │  │  ACE Permission  │  │  MCP stdio Server  │  │
│  └───────────────────┘  └────────┬─────────┘  └─────────┬──────────┘  │
│                                  │                       │            │
└──────────────────────────────────┼───────────────────────┼────────────┘
                                   │                       │
                    ┌──────────────┼───────────────────────┼──────────┐
                    │              ▼                       ▼          │
                    │  ┌──────────────┐  ┌──────────┐  ┌──────────┐  │
                    │  │ PostgreSQL 16│  │  Redis 7  │  │ RabbitMQ │  │
                    │  │ Port :5432   │  │ Port :6379│  │ :5672    │  │
                    │  │ + pgvector   │  │ Session   │  │ Doc      │  │
                    │  │ + HNSW idx   │  │ Cache     │  │ Ingest   │  │
                    │  └──────────────┘  └──────────┘  └──────────┘  │
                    │                                                 │
                    │  ┌──────────────┐                               │
                    │  │    MinIO     │                               │
                    │  │ Port :9000   │                               │
                    │  │ File Storage │                               │
                    │  └──────────────┘                               │
                    │           Infrastructure Layer                  │
                    └─────────────────────────────────────────────────┘
```

### 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | Vue 3 + Vite + Element Plus + Pinia | SPA, SSE 流式对话 |
| Java 后端 | Spring Boot 3.3 + JPA + Security + JWT | 业务逻辑 + 权限控制 |
| Python AI | FastAPI + asyncpg + pgvector + OpenAI SDK | 向量检索 + LLM 调用 |
| 数据库 | PostgreSQL 16 + pgvector | 业务数据 + HNSW 向量索引 |
| 缓存 | Redis 7 | kb_ids 权限缓存 + 对话历史 |
| 消息队列 | RabbitMQ 3 | 异步文档入库管道 |
| 对象存储 | MinIO | 上传文件存储 |

### 端口

| 服务 | 端口 |
|------|------|
| Frontend | 5173 |
| Java Backend | 8080 |
| Python AI Service | 8000 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| RabbitMQ | 5672 / 15672 (管理) |
| MinIO | 9000 / 9001 (控制台) |

---

## 2. DDD 分层架构

```
┌─────────────────────────────────────────────────────┐
│                  Interfaces Layer                     │
│  Controller (HTTP)  │  MCP Server (stdio)            │
│  仅接收参数/返回结果，严禁业务逻辑                      │
├─────────────────────────────────────────────────────┤
│               Application Service Layer               │
│  编排核心业务逻辑，跨模块协调通过 Event 机制             │
│  Auth │ Document │ Conversation │ RAG                │
├─────────────────────────────────────────────────────┤
│                  Domain Model Layer                   │
│  Entity + Repository Interface                       │
│  User │ Space │ KB │ ACE │ Document │ Conversation    │
├─────────────────────────────────────────────────────┤
│               Infrastructure Layer                    │
│  JPA 实现 │ pgvector │ Redis │ RabbitMQ │ MinIO       │
└─────────────────────────────────────────────────────┘

单向依赖: Interfaces → Application → Domain → Infrastructure
严禁反向依赖 (Domain 不得 import Application)
```

### Java 模块划分

```
backend/src/main/java/com/kes/
├── auth/           # 认证授权模块
│   ├── controller/  # AuthController, SpaceController, ApiKeyController...
│   ├── service/     # AuthService, PermissionService, KbService, AceService...
│   ├── model/       # User, Space, KnowledgeBase, ACE, ApiKey...
│   ├── repository/  # JPA Repository 接口
│   ├── event/       # AuditEventListeners, KbCleanupEventListeners
│   └── config/      # SecurityConfig, JwtFilter
├── document/       # 文档模块
│   ├── controller/  # DocumentController
│   ├── service/     # DocumentService, MinioStorageService, IngestCallbackConsumer
│   ├── model/       # DocumentMeta, DocumentApproval
│   ├── repository/  # DocumentMetaRepository, DocumentApprovalRepository
│   └── event/       # DocumentEventListeners
├── conversation/   # 对话模块
│   ├── controller/  # ConversationController
│   ├── service/     # ConversationService
│   └── model/       # Conversation, Message
├── rag/            # RAG 中继模块
│   ├── controller/  # ChatController (SSE relay)
│   ├── client/      # AiServiceClient (WebClient → Python)
│   └── event/       # AiSyncEventListeners
└── common/         # 共享基础
    ├── util/        # JwtUtil, ControllerAuthHelper
    ├── event/       # 6 个跨模块事件 record
    ├── service/     # AuditLogger
    ├── aop/         # AdminGuard (权限注解切面)
    ├── annotation/  # @RequireSpaceAdmin, @RequireGlobalAdmin
    ├── exception/   # BusinessException, GlobalExceptionHandler
    ├── dto/         # SpaceDtos (12 种响应 DTO)
    └── config/      # MinioConfig, RedisConfig, AmqpConfig, WebConfig
```

### Python 模块划分

```
ai-service/
├── api/            # FastAPI 应用
│   ├── app.py          # 应用工厂 + lifespan DI
│   ├── chat.py         # POST /v1/chat (SSE RAG 端点)
│   ├── dependencies.py # Depends 注入函数
│   ├── documents.py    # 文档状态同步端点
│   ├── admin_models.py # 模型发现/测试端点
│   └── health.py       # GET /v1/health
├── kes_mcp/        # MCP 知识服务
│   ├── auth.py         # API Key → JWT 交换 + 自动续期
│   ├── server.py       # MCP stdio Server (3 Tools + 2 Resources + 2 Prompts)
│   └── tools.py        # search_chunks / read_document / ask_expert
├── retrieval/      # 混合检索引擎
│   ├── orchestrator.py # 全流程编排 (7 阶段)
│   ├── hybrid_search.py# Dense ∥ Sparse → RRF 融合
│   ├── dense.py        # HNSW 向量检索
│   ├── sparse.py       # tsvector BM25 关键词
│   ├── fusion.py       # RRF 排名融合 (k=60)
│   ├── reranker.py     # Cross-Encoder → LLM 降级
│   ├── query_rewriter.py# 查询改写 (缓存 + 短路)
│   ├── intent_router.py # 意图路由 (规则 + LLM)
│   ├── citation.py     # 引用标注 + 位置单调约束
│   └── vector_store.py # PGVectorClient
├── parsing/        # 文档解析引擎 (借鉴 RAGFlow deepdoc)
│   ├── orchestrator.py # MIME 路由
│   ├── pdf/            # PDF (layout/ocr/table/merger)
│   ├── office/         # DOCX/XLSX/PPTX
│   └── web/            # HTML/Markdown/Text
├── chunking/       # 语义分块引擎
│   ├── token_chunker.py
│   ├── title_chunker.py
│   └── enrich.py       # 上下文注入
├── llm/            # LLM 抽象层
│   ├── factory.py      # 模型工厂
│   ├── model_pool.py   # 动态模型池 (从 Java 拉取)
│   └── prompts/        # RAG/摘要/改写/意图/Rerank 提示词
├── mq/             # 消息队列
│   ├── client.py       # RabbitMQ 连接管理
│   └── handler.py      # 入库消息处理器
├── core/
│   ├── config/         # YAML + 环境变量加载
│   └── context/        # 上下文组装 + 历史管理 + 摘要引擎
├── models/         # Pydantic 数据模型
├── etl/            # [旧] ETL 管道 (迁移中)
└── common/         # 日志/异常/工具
```

---

## 3. 权限模型 (v4 ACE)

### 三层身份判定

```
                  users.is_global_admin = TRUE?
                  ├── YES → 全局超级管理员 (所有 Space 所有 KB)
                  └── NO  → 查 space_admins 表
                            ├── role='owner' → Space Owner
                            ├── role='admin' → Space Admin
                            └── 无记录 → 通过 space_groups 查用户组
                                        ├── 组成员 → Space Member (KB 访问由 ACE 决定)
                                        └── 非成员 → 无权限
```

### ACE 矩阵规则

```
用户组 (全局可嵌套) ──space_groups──→ Space
                                       │
用户 ──space_admins──→ Space (owner/admin)
                                       │
角色 (permissions JSONB) ──ACE 条目──→ KB (space_wide | restricted)
                                       │
                                       └──→ Document (inherit_permissions)
```

**算法: resolveAccessibleKbIds(spaceId, userId)**
```
1. 全局管理员 → 全量返回
2. expandUserEffectiveGroups(userId) → 用户有效组 (含嵌套上溯)
3. 计算 Space 身份: space_admins? space_groups ∩ effectiveGroups?
4. Space admin → 所有 KB 可见
5. space_wide KBs → 自动加入结果
6. 查询 ACE: allow → 加入, deny → 移除 (deny 覆盖 allow)
7. Redis 缓存 (5min TTL)
```

### JWT 双 Token 方案

| Token | 有效期 | 包含字段 | 用途 |
|-------|--------|---------|------|
| `refresh_token` | 7 天 | `{sub: userId, type: "refresh"}` | 登录/刷新/列 Space/切换 Space |
| `context_token` | 30 分钟 | `{sub: userId, space_id, role}` | 所有业务 API 调用 |

---

## 4. 数据库核心表

```
                         ┌──────────────┐
                         │    users     │
                         │ id (UUID PK) │
                         │ username     │
                         │ password_has │
                         │ is_global_ad │
                         │ email, status│
                         │ metadata JSN │
                         └──────┬───────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │ user_groups   │  │space_admins  │  │   api_keys   │
    │ id (UUID PK) │  │space_id+user │  │ id (UUID PK) │
    │ parent_group │  │role(owner/ad)│  │ user_id (FK) │
    │ is_system_ad │  └──────────────┘  │ key_hash     │
    │ external_id  │                    │ scope_kb_ids │
    │ metadata JSN │                    │ expires_at   │
    └──────┬───────┘                    │ revoked_at   │
           │                            └──────────────┘
    ┌──────┴──────────┐
    ▼                 ▼
┌──────────┐  ┌──────────────┐
│user_group│  │ space_groups │
│_members  │  │space_id+grp  │
└──────────┘  └──────────────┘
                     │
                     ▼
              ┌──────────────┐         ┌──────────────┐
              │    spaces    │         │    roles     │
              │ id (UUID PK) │         │ id (UUID PK) │
              │ name         │         │ name         │
              │ status       │         │ permissions  │
              │ deleted_at   │         │ is_system    │
              │ metadata JSN │         └──────┬───────┘
              └──────┬───────┘                │
                     │                        ▼
                     ▼              ┌──────────────────┐
              ┌──────────────┐     │ access_control_   │
              │knowledge_bases│     │    entries (ACE)  │
              │ id (UUID PK) │     │ space_id          │
              │ space_id (FK)│◄────│ resource_type=kb  │
              │ visibility   │     │ principal_type    │
              │ deleted_at   │     │ principal_id      │
              │ metadata JSN │     │ role_id           │
              └──────┬───────┘     │ effect(allow/deny)│
                     │             └──────────────────┘
                     ▼
              ┌──────────────┐
              │document_meta │
              │ id (UUID PK) │
              │ kb_id (FK)   │
              │ space_id     │
              │ filename     │
              │ status       │
              │ ingest_status│
              │ file_type    │
              └──────────────┘

其他表:
  ├── conversations (id, user_id, kb_id, space_id, title)
  ├── messages (id, conversation_id, role, content, tokens_used)
  ├── knowledge_chunks (id, doc_id, kb_id, content, embedding, tsvector)
  ├── refresh_tokens (id, user_id, token, expires_at)
  ├── document_approvals (id, document_id, status, action_type)
  ├── admin_action_logs (operator_id, space_id, action, target_type)
  ├── model_providers / model_configs / model_assignments
  └── system_config (model_config_version)
```

---

## 5. 数据流

### 5.1 RAG 问答流程

```
┌─────────┐   POST /api/chat    ┌──────────┐   POST /v1/chat    ┌──────────┐
│ Frontend │ ─────────────────→ │   Java   │ ─────────────────→ │  Python  │
│ (SSE)    │ ◄───────────────── │ Backend  │ ◄───────────────── │ AI Svc   │
└─────────┘   SSE (data: {...}) └──────────┘   SSE Stream        └──────────┘
                                                              │
  1. Java 解析 JWT → userId + spaceId                          │
  2. Java resolveAccessibleKbIds() → kb_ids 列表              │
  3. Java → Python: {query, filter_params: {kb_ids}, ...}     │
                                               │
  4. Python Query Rewriter (缓存 + 短路)         ◄────────────┘
  5. Python Intent Router (规则 + LLM)
  6. Python Hybrid Search: Dense (HNSW) ∥ Sparse (BM25)
  7. Python RRF Fusion (k=60) → Top-K chunks
  8. Python Reranker: Cross-Encoder → LLM 降级
  9. Python Context Assembler: [system] → [summary] → [history] → [chunks]
  10. Python LLM generate → SSE tokens
                                               │
  11. Python Citation Inserter → 标注引用       ◄────────────┘
  12. Java SSE relay → 保存 assistant message 到 PostgreSQL
```

### 5.2 文档入库 (异步管道)

```
┌─────────┐  POST /api/documents   ┌──────────┐
│ Frontend │ ────────────────────→ │   Java   │
└─────────┘                        └────┬─────┘
                                        │
  1. 文件上传到 MinIO                    │
  2. 创建 DocumentMeta (status: pending) │
  3. 发布 document.ingest 消息 ─────────→ RabbitMQ
                                                    │
        ┌───────────────────────────────────────────┘
        ▼
  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Download │ →  │  Parse   │ →  │  Chunk   │ →  │  Embed   │
  │ (MinIO)  │    │ (PDF/DOC)│    │ (语义)    │    │ (1024d)  │
  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                       │
        ┌──────────────────────────────────────────────┘
        ▼
  ┌──────────┐    POST callback       ┌──────────┐
  │ pgvector │ ← ─ ─ ─ ─ ─ ─ ─ ─ ─ →│   Java   │
  │  Insert  │    ingest.callback     │ 更新状态 │
  └──────────┘                        └──────────┘
```

### 5.3 MCP 知识服务流程

```
┌──────────────┐    API Key    ┌──────────┐    context_token   ┌──────────┐
│ MCP Client   │ ───────────→ │   Java   │ ────────────────→ │  Python  │
│ (Claude/Cursor)│  exchange   │ Backend  │   JWT + scope     │ MCP Srv  │
└──────────────┘              └──────────┘                   └────┬─────┘
       ▲                                                          │
       │  MCP Protocol (stdio)                                    │
       │  Tool: search_chunks / read_document / ask_expert         │
       │  Resource: doc://catalog                                  │
       └──────────────────────────────────────────────────────────┘

权限三层交集:
  effective = tool_kb_ids ∩ ACE kb_ids (用户权限) ∩ scope_kb_ids (Key 白名单)
```

---

## 6. 跨模块事件系统

6 个事件 record，通过 Spring ApplicationEventPublisher 解耦跨模块副作用：

| 事件 | 发布者 | 消费者 |
|------|--------|--------|
| `AuditLogEvent` | DocumentService, KbService, ApiKeyService... | AuditEventListeners → admin_action_logs |
| `DocumentStatusChangedEvent` | DocumentService (softDelete/restore) | AiSyncEventListeners → Python 同步 |
| `DocumentPermanentlyDeletedEvent` | DocumentService (permanentDelete) | AiSyncEventListeners, KbCleanupEventListeners |
| `KbSoftDeletedEvent` | KbService | DocumentEventListeners → 级联文档操作 |
| `KbRestoredEvent` | KbService | DocumentEventListeners |
| `KbPermanentlyDeletedEvent` | KbService | DocumentEventListeners, KbCleanupEventListeners → ACE 清理 |

---

## 7. API 端点全景

### 认证 `/api/auth`
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册 |
| POST | `/auth/login` | 登录 → refresh_token |
| POST | `/auth/refresh` | 刷新 token |
| GET | `/auth/spaces` | 列出 Space |
| POST | `/auth/switch-space` | 签发 context_token |
| GET | `/auth/accessible-kbs` | 可访问 KB 列表 |
| GET | `/auth/users/search` | 用户搜索 |
| PUT | `/auth/password` | 修改密码 |

### MCP API Key `/api/auth/mcp`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/mcp/keys` | 列出密钥 |
| POST | `/mcp/keys` | 创建密钥 |
| PUT | `/mcp/keys/{id}` | 重命名 |
| DELETE | `/mcp/keys/{id}` | 撤销 |
| POST | `/mcp/keys/{id}/extend` | 续期 |
| PUT | `/mcp/keys/{id}/scope` | 修改 KB 范围 |
| POST | `/mcp/exchange` | API Key → JWT |

### Space 管理 `/api/spaces`
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/spaces` | 创建 Space |
| POST | `/spaces/{id}/archive` | 归档 |
| GET | `/spaces/{id}/members` | 查看成员 |
| GET/POST/DELETE | `/spaces/{id}/admins` | 管理员 CRUD |
| POST | `/spaces/{id}/transfer-ownership` | 转让 |
| GET/POST/DELETE | `/spaces/{id}/groups` | 准入组管理 |
| GET/POST/PUT/DELETE | `/spaces/{id}/aces` | ACE 矩阵 |
| GET/POST/PUT/DELETE | `/spaces/{id}/kbs` | KB CRUD |
| POST | `/spaces/{id}/kbs/{kbId}/restore` | 恢复 KB |
| GET | `/spaces/{id}/trash` | 回收站 |
| GET | `/spaces/{id}/audit-logs` | 操作日志 |

### 文档 `/api/documents`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/documents` | 文档列表 |
| POST | `/documents` | 上传 |
| GET | `/documents/{id}` | 详情 |
| GET | `/documents/{id}/file` | 下载/预览 |
| PUT | `/documents/{id}` | 更新文件 |
| PUT | `/documents/{id}/metadata` | 编辑元数据 |
| DELETE | `/documents/{id}` | 软删除 |
| POST | `/documents/{id}/restore` | 恢复 |
| DELETE | `/documents/{id}/permanent` | 永久删除 |
| GET | `/documents/approvals` | 待审批列表 |
| POST | `/documents/approvals/{id}/approve` | 通过审批 |
| POST | `/documents/approvals/{id}/reject` | 驳回 |

### 对话 + 聊天
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/conversations` | 对话列表 |
| GET | `/conversations/{id}/messages` | 消息列表 |
| DELETE | `/conversations/{id}` | 删除对话 |
| POST | `/chat` | RAG 问答 (SSE) |

### 全局管理 `/api/admin`
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/spaces` | 所有 Space |
| POST/DELETE | `/admin/spaces/{id}/archive\|delete\|restore` | Space 管理 |
| GET/POST/PUT | `/admin/users` | 用户 CRUD |
| POST | `/admin/users/batch` | CSV 批量导入 |
| GET/POST/PUT/DELETE | `/admin/models/*` | 模型配置管理 |

### 用户组 + 角色
| 模块 | 路径 | CRUD |
|------|------|------|
| 用户组 | `/groups` | POST/GET/PUT/DELETE + 成员管理 |
| 角色 | `/roles` | POST/GET/PUT/DELETE |

### Python AI `/v1`
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/chat` | SSE RAG 端点 |
| GET | `/v1/health` | 组件健康检查 |
| POST | `/v1/documents/status` | 文档状态同步 |
| DELETE | `/v1/documents/{id}/chunks` | 删除向量块 |
| POST | `/v1/admin/models/discover` | 模型发现 |
| POST | `/v1/admin/models/test` | 连通性测试 |

---

## 8. MCP 知识服务

### 启动方式
```json
{
  "mcpServers": {
    "kes": {
      "command": "python",
      "args": ["-m", "kes_mcp.server"],
      "env": {
        "KES_API_KEY": "kes_mcp_xxxxxxxxxxxxxxxxxxxxx",
        "KES_SPACE_ID": "bbbbbbbb-0000-4000-b000-000000000001"
      }
    }
  }
}
```

### 注册的能力

| 类型 | 名称 | 说明 |
|------|------|------|
| **Tool** | `search_chunks` | 混合检索文档块 + 完整元数据 |
| **Tool** | `read_document` | 读取文档元数据 + 内容 |
| **Tool** | `ask_expert` | RAG 问答 + LLM 生成 + 引用标注 |
| **Resource** | `doc://catalog` | 有权限的 KB 列表 |
| **Prompt** | `qa_template` | 标准 RAG 问答模板 |
| **Prompt** | `document_analysis` | 文档分析模板 |

### 权限模型: A+C 混合
```
effective_kb_ids = tool_kb_ids     ← Agent 传参 (可选)
                 ∩ ace_kb_ids      ← 用户 ACE 权限 (Java 实时解析)
                 ∩ scope_kb_ids    ← API Key 白名单 (创建时设定, 可修改)
```

---

## 9. 前端组件架构

```
src/
├── views/            # 页面级组件 (路由匹配)
│   ├── Login.vue         # 登录
│   ├── SpaceSwitcher.vue # Space 选择 + 创建
│   ├── SpaceSettings.vue # Space 设置 (6 个 Tab)
│   ├── Chat.vue          # RAG 对话 (编排 ChatInput + ChatMessage + KbSelector)
│   ├── Documents.vue     # 文档管理
│   ├── Approvals.vue     # 审批管理
│   ├── AdminDashboard.vue# 全局管理 (用户/空间)
│   ├── ModelManagement.vue# 模型配置
│   ├── GroupManagement.vue# 用户组管理
│   ├── RoleManagement.vue# 角色管理
│   └── AceConfig.vue     # ACE 矩阵配置
├── components/       # 可复用组件
│   ├── chat/             # ChatInput, ChatMessage, ConversationList...
│   ├── documents/        # UploadDialog, UpdateDialog
│   ├── settings/         # ApiKeyManager, KbSettings, TrashPanel, AuditLogTable...
│   ├── groups/           # GroupTree, GroupDetail, GroupMemberTable
│   ├── common/           # UserSearchSelect
│   └── aces/             # AceEntryTable, AceEditDialog
├── composables/      # 共享业务逻辑
│   ├── useChatSSE.js     # SSE 发送 + streaming + cancel
│   ├── useChatMessages.js# 消息加载/格式化
│   ├── useDocuments.js   # 文档 CRUD
│   ├── useKbFetcher.js   # KB 列表获取
│   ├── useConfirmAction.js# 确认对话框
│   ├── useUserSearch.js  # 远程用户搜索
│   └── useChatKbFilter.js# Chat KB 筛选
├── stores/           # Pinia 状态
│   └── auth.js           # 用户 + Space + Token
├── api/              # HTTP 层
│   └── index.js          # Axios + JWT 自动刷新 + SSE + 所有 API 方法
├── router/           # 路由
│   └── index.js          # /login, /spaces, /app/:spaceId/...
└── utils/            # 工具函数
    ├── datetime.js       # 日期格式化
    ├── constants.js      # 状态映射表 + API Key 有效期选项
    ├── errorHandler.js   # 统一错误处理
    └── idgen.js          # UUID 生成
```

---

## 10. 安全层次

```
┌─────────────────────────────────────────┐
│         Spring Security Filter Chain     │
│  JwtFilter → 验证签名 + 解析 userId     │
│  SecurityConfig → STATELESS session     │
├─────────────────────────────────────────┤
│         AOP 权限切面                     │
│  @RequireGlobalAdmin → AdminGuard       │
│  @RequireSpaceAdmin  → AdminGuard       │
├─────────────────────────────────────────┤
│         Service 权限校验                 │
│  PermissionService.require*()           │
│  三层: 全局管理员/Space 管理员/Space 成员│
├─────────────────────────────────────────┤
│         运行时权限解析                    │
│  PermissionQueryService                 │
│  resolveAccessibleKbIds() → kb_ids 列表  │
│  Redis 缓存 (5min TTL)                   │
├─────────────────────────────────────────┤
│         MCP 权限交集                     │
│  tool_kb_ids ∩ ace_kb_ids ∩ scope_kb_ids│
└─────────────────────────────────────────┘
```

---

## 11. 配置与密钥

| 配置项 | 位置 | 说明 |
|--------|------|------|
| JWT Secret | `application.yml: jwt.secret` | 生产需替换 256-bit 密钥 |
| DB 密码 | `application.yml: spring.datasource.password` | 需环境变量外置 |
| LLM API Key | 环境变量 `${DASHSCOPE_API_KEY}` | 已外部化 ✅ |
| Python LLM 降级 | `ai-service/config/llm.yaml` | 当 Java 模型池不可用时的降级 |
| Java → Python URL | `application.yml: aiservice.base-url` | 默认 `http://localhost:8000` |
| Python → Java URL | 环境变量 `KES_JAVA_URL` | 默认 `http://localhost:8080` |
| MinIO 凭证 | `application.yml: minio.*` | 需外置 |
| RabbitMQ 凭证 | `application.yml: spring.rabbitmq.*` | 需外置 |
| Docker 密码 | `docker-compose.yaml` | 默认 `kes123/minioadmin` |
| CORS 来源 | `WebConfig.java` | 硬编码 `localhost:5173` |

---

## 12. 已知技术债务

| 类别 | 问题 | 优先级 |
|------|------|--------|
| 安全 | JWT 无吊销机制 (禁用用户后 token 仍有效 7 天) | P0 |
| 安全 | 登录无频率限制 | P0 |
| 安全 | API Key 无盐 SHA-256 | P1 |
| 多租户 | 文档列表无权限校验 (知道 kb_id 遍历数据) | P0 |
| 多租户 | 5 个 Space 端点暴露元数据给非成员 | P1 |
| 部署 | 无应用 Dockerfile | P0 |
| 部署 | 无健康检查端点 (Java) | P0 |
| 运维 | 无数据库迁移自动化 (Flyway) | P1 |
| 运维 | 无备份策略 | P1 |
| 弹性 | 无断路器/重试 | P2 |
| 测试 | Java ~7% / Python ~9% / 前端 0% | P2 |
| 代码 | DocumentService 483 行上帝类 | P2 |
| 代码 | 18 端点返回 Map 而非 DTO | P2 |
| 代码 | DDD 跨模块直接注入 Repository | P3 |
