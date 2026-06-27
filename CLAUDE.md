# CLAUDE.md
架构与分层强制规则：
严格分层：本项目采用 DDD（领域驱动设计）。Controller 层只负责接收参数和返回结果，严禁包含任何业务逻辑；Service 层负责编排和核心业务逻辑；Repository 层只负责数据库 CRUD。
单向依赖：内层模块（Domain/Infrastructure）绝对禁止反向依赖外层模块（Application/Interfaces）。
防上帝类：任何单个类或函数不得超过 300 行。如果超过，必须主动提出拆分建议。
跨模块通信：禁止在 Auth 模块直接注入 Document 模块的 Repository。跨模块调用必须通过 Application Service 层或事件机制（Event）进行编排。
依赖注入：禁止在类内部手动 new 依赖，必须通过构造函数注入。

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
注意对话使用中文。
## Project Overview

企业知识助手 (Enterprise Knowledge Assistant) — a RAG-based Q&A system with document ingestion and Space/KB access control (v4 ACE) and MCP knowledge service (v8). 企业 OA 融合基础就绪 (v9 JSONB 扩展 + user_identities)。

## 项目目标与设计方针（★ 2026-06-27 确立）

**KES 定位为知识中间件（Knowledge Middleware），外部 AI Agent 为一等公民。**

本项目包含两个独立的知识消费场景，它们在检索链路上**共享检索执行层但查询准备层完全独立**：

| 场景 | 消费者 | KES 角色 | 查询特征 | 查询准备 |
|------|--------|---------|---------|---------|
| **Web Chat** (`/v1/chat`) | 人类用户 | 答案生成器 | 口语化、省略、多轮指代 | QueryRewriter (LLM 消解指代) + IntentRouter |
| **MCP** (`kes_mcp/`) | 外部 AI Agent | 知识源 | 精炼、结构化、单轮 | **McpQueryPreparator** (jieba 实体提取，零 LLM) + MCP 协议层约束 |

核心设计原则：
1. **Agent 一等公民**：整个 MCP → 检索 → 返回结果链路以外部 Agent 的需求为设计起点
2. **KES 是知识中间件**：对 Agent 而言输出应结构化、可溯源，KES 不是答案生成器
3. **复杂度前置到协议层**：查询质量的保障靠 MCP Tool description / inputSchema / Prompt 指导 Agent 构造高质量输入
4. **服务端检索零 LLM 调用**：Agent 自己就是 LLM 驱动的，KES 检索阶段不做重复语义理解

**两条检索路径架构**：
```
                       ┌──────────────────────────────┐
                       │      检索执行层 (共享)         │
                       │  RetrievalOrchestrator.execute│
                       │  HybridSearch ∥ Reranker      │
                       └──────────────┬───────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
    ┌────────────┴────────────┐               ┌────────────┴───────────┐
    │  Web Chat (为人服务)     │               │  MCP (为 Agent 服务)    │
    │  retrieve()             │               │  McpQueryPreparator    │
    │  QueryRewriter +        │               │  + execute()           │
    │  IntentRouter +         │               │  协议约束 + jieba提取   │
    │  ContextAssembler       │               │  延迟: +5ms, LLM: 0次  │
    └─────────────────────────┘               └────────────────────────┘
```
**绝对不能混淆**：MCP 不是 Web Chat 的"无历史退化版本"，而是独立的一等场景。

## Documentation Maintenance

**重要功能修改后必须同步更新相关文档，避免文档腐烂 (documentation rot)。**

When making significant functional changes, you **MUST** update:

1. **CLAUDE.md** — architecture, service responsibilities, source locations, API endpoints, config
2. **scripts/init-pgvector.sql** — if schema changes (new tables, columns, indexes)
3. **Comments in code** — if behavior diverges from what existing comments describe

### Docs Directory Structure

```
docs/
├── adr/          # 架构决策记录（不可变，新决策 = 新文件，不编辑旧文件）
│   └── 001-space-kb-permission-model.md
├── plans/        # 功能实施计划（实现完成后标记 [已完成]）— 目前空
├── reference/    # 参考资料、外部项目分析
│   └── RAGFlow_文档处理模块源码拆解.md
├── reports/      # 一次性报告，永久冻结
│   └── RECYCLE_BIN_TEST_REPORT.md
└── PROJECT.md    # 项目定位 + 总览
```

**重要架构变更必须写 ADR**（参考 `docs/adr/001-space-kb-permission-model.md` 格式）。
**已完成功能的 plan 文档不要删除**，在标题加 `[✅ 已完成 — YYYY-MM-DD]` 标记。

## Services & Ports

| Service | Port | Tech Stack |
|---------|------|------------|
| Frontend | 5173 | Vue 3 + Vite + Element Plus + Pinia |
| Java Backend | 8080 | Spring Boot 3.3 + JPA + Security + JWT |
| Python AI Service | 8000 | FastAPI + asyncpg + pgvector + OpenAI SDK |
| PostgreSQL | 5432 | Business data + vector search (pgvector) |
| Redis | 6379 | Session cache, kb_ids permission cache, conversation history |
| RabbitMQ | 5672/15672 | Async doc ingestion pipeline |
| MinIO | 9000/9001 | Object storage for uploaded files |

## Quick Start

```bash
./setup.sh                                      # Install all dependencies
export DASHSCOPE_API_KEY="your-key"             # Required LLM API key
./start.sh                                      # Start everything
./stop.sh                                       # Stop all services
```

## Development Commands

### Infrastructure (Docker)
```bash
docker compose up -d              # Start all infra services
docker compose ps                 # Check service health
docker compose down -v            # Stop infra + remove volumes (fresh DB)
```

### Python AI Service (`ai-service/`)
```bash
cd ai-service
uv sync                                                     # Install deps
uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Java Backend (`backend/`)
```bash
cd backend
mvn compile                                                 # Compile
mvn test                                                    # Run tests (33 tests)
mvn spring-boot:run                                        # Run dev server
```

### Python AI Service (`ai-service/`)
```bash
cd ai-service
uv sync                                                     # Install deps
uv run pytest --rootdir=. tests/                            # Run tests (30 tests)
uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend (`frontend/`)
```bash
cd frontend
npm install                                                 # Install deps
npm run dev                                                 # Dev server (port 5173)
npm run build                                               # Production build
```

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
- **v4 重构**: 跨模块副作用通过 Spring `ApplicationEventPublisher` 发布事件，由各自模块的 `@EventListener` 处理

**Python AI Service owns:**
- Embedding generation & pgvector vector search (HNSW 索引)
- LLM invocation (streaming via OpenAI-compatible API)
- Document ETL pipeline: MinIO download → parsing/ (结构化解析) → chunking/ (语义分块) → embedding → pgvector insert
- Context assembly (system prompt + summary + Java-forwarded history + retrieval results)
- Hybrid search (Dense HNSW ∥ Sparse BM25 → RRF fusion)
- Reranker (Cross-Encoder → LLM 降级)
- Query rewriting with cache + short-circuit (缓存+短路+关键词提取) — Web Chat 专用，多轮对话消解指代
- MCP query preparation (jieba entity extraction + focus_aspects mapping, zero LLM) — MCP 专用，纯本地 ~5ms
- Intent routing (规则前置 + LLM 兜底) — Web Chat 专用
- Retrieval execution layer (HybridSearch + Reranker) — **Web Chat 与 MCP 共享**
- Citation insertion with monotonic constraint (引用标注+位置约束)
- Model Pool (启动时从 Java 拉取模型配置，支持热重载)
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

### Inter-service Communication

1. **Sync (HTTP):**
   - Java POST → `http://python:8000/v1/chat` with `{query, filter_params: {kb_ids: [...]}, conversation_id, history_messages, top_k}`. Python returns SSE stream.
   - Java POST → `http://python:8000/v1/documents/status` — sync document status (active/soft_deleted) to `knowledge_chunks` table.
   - Java DELETE → `http://python:8000/v1/documents/{docId}/chunks` — permanently delete all vector chunks for a document.
2. **Async (RabbitMQ):** Java publishes `document.ingest` messages → Python consumes, runs ETL, publishes `document.ingest.callback` → Java updates `document_meta.ingest_status`.

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

## Configuration

- **Python LLM config:** `ai-service/config/llm.yaml` — 旧版静态配置。v6 升级后作为降级方案，当 Java 后端不可用时使用。
- **★ v6 模型配置中心:** 全局管理员通过前端界面动态配置 Provider/Model/环节映射，存储于 `model_providers` / `model_configs` / `model_assignments` 三表。Python 启动时从 Java `GET /api/admin/models/active` 拉取，30 秒热重载。
- **Java config:** `backend/src/main/resources/application.yml` — `jwt.secret`, `jwt.refresh-expiration` (7d), `jwt.context-expiration` (30m), `aiservice.base-url`, `minio.*`, `spring.data.redis.*`, `spring.rabbitmq.*`.
- **Infrastructure:** `docker-compose.yaml` — all ports, credentials, volumes. Network: `kes-net`.
- **DB Schema:** `scripts/init-pgvector.sql` — executed on first PostgreSQL start. Creates all tables with v4 ACE model.
- **Seed Data:** `scripts/init-admin.sql` — creates admin users, default Space, default KB.

### LLM Provider

v6 模型配置中心支持动态切换。全局管理员在 AdminDashboard → 模型管理 Tab 配置。

默认供应商:
- **LLM**: 任何 OpenAI 兼容 API（DashScope / vLLM / DeepSeek / Ollama）
- **Embedding**: text-embedding-v3 (1024维)
- **Reranker**: BGE-Reranker (Cross-Encoder) 或 LLM 降级

配置优先级: 数据库模型配置 → `llm.yaml` 降级 → 环境变量 `${DASHSCOPE_API_KEY}`

Switch providers: change `type` in `config/llm.yaml` + register new implementation via `ModelFactory.register_llm()`.

## Key Source Locations

```
ai-service/
├── api/
│   ├── app.py              # FastAPI app factory, lifespan DI
│   ├── chat.py             # POST /v1/chat (SSE RAG endpoint, Depends 注入)
│   ├── admin_models.py     # ★ v6: POST /v1/admin/models/{discover,test} (供 Java 代理)
│   ├── dependencies.py     # 声明式 Depends 函数（get_llm, get_pgvector_client 等 8 个）
│   ├── documents.py        # POST /v1/documents/status, DELETE /v1/documents/{doc_id}/chunks
│   └── health.py           # GET /v1/health (component health check, Depends 注入)
├── core/
│   ├── config/settings.py  # YAML + env var config loading
│   ├── context/
│   │   ├── context_assembler.py  # [system] → [summary] → [history] → [query]
│   │   ├── history_manager.py    # Redis-backed history cache
│   │   └── summary_engine.py     # Summary generation + 2nd-level compression
│   └── security/           # 空（预留）
├── parsing/                # ★ v5: 文档解析引擎（借鉴 RAGFlow deepdoc）
│   ├── orchestrator.py         # ParseOrchestrator — MIME 路由
│   ├── base.py                 # BaseParser ABC + 模板方法
│   ├── models.py               # ParsedDocument, TextBlock, TableBlock, ImageBlock
│   ├── registry.py             # ParserRegistry — 按文件类型注册
│   ├── pdf/                    # PDF 深度解析（Phase 1b）
│   │   ├── parser.py           #   PdfParser — 多阶段编排
│   │   ├── layout.py           #   LayoutAnalyzer — ONNX 布局识别
│   │   ├── ocr.py              #   OcrEngine — PaddleOCR 封装
│   │   ├── table.py            #   TableExtractor — 表格结构识别
│   │   └── merger.py           #   TextMerger — 文本合并 + 阅读顺序
│   ├── office/                 # Office 解析器
│   │   ├── docx.py             #   DocxParser — 保留表格/标题层级
│   │   ├── xlsx.py             #   XlsxParser — Sheet → TableBlock
│   │   └── pptx.py             #   PptxParser — ★ 新增 PPTX 支持
│   └── web/                    # Web 文档解析器
│       ├── html.py             #   HtmlParser — 保留标题/表格
│       ├── markdown.py         #   MarkdownParser — ★ 保留标题层级
│       └── text.py             #   TextParser — UTF-8/GBK
├── chunking/               # ★ v5: 语义分块引擎（借鉴 RAGFlow charunker）
│   ├── orchestrator.py         # ChunkOrchestrator — 策略选择 + 上下文注入
│   ├── base.py                 # BaseChunker ABC
│   ├── models.py               # Chunk, ChunkRelation
│   ├── token_chunker.py        # TokenChunker — token 感知 + 分隔符优先级
│   ├── title_chunker.py        # TitleChunker — 标题层级分块 + 父子关系
│   ├── semantic_chunker.py     # SemanticChunker — TODO 延后
│   ├── merge.py                # naive_merge 移植（待补充）
│   └── enrich.py               # ContextEnricher — 表格/图片上下文注入
├── llm/
│   ├── base.py
│   ├── factory.py
│   ├── model_pool.py           # ★ v6: 动态模型池（从 Java 拉配置, 热重载, 降级到 factory）
│   ├── openai_compatible.py
│   ├── rerank_llm.py           # ★ v5: LLM 降级 Reranker
│   └── prompts/
│       ├── rag.py              # RAG 问答 prompt
│       ├── summary.py          # 摘要 prompt
│       ├── rewrite.py          # ★ v5: Query 改写 prompt
│       ├── intent.py           # ★ v5: 意图分类 prompt
│       └── rerank.py           # ★ v5: LLM rerank 降级 prompt
├── retrieval/              # ★ v5: 混合检索引擎（借鉴 RAGFlow Dealer）
│   ├── orchestrator.py         # RetrievalOrchestrator — execute() 共享执行层 + retrieve() Web Chat 全流程
│   ├── mcp_query_preparator.py # ★ MCP 查询准备器 — jieba 实体提取 + focus_aspects 映射（零 LLM，~5ms）
│   ├── models.py               # ScoredChunk, IntentResult, RewriteResult, RetrievalContext
│   ├── hybrid_search.py        # HybridSearch — Dense ∥ Sparse → RRF
│   ├── dense.py                # DenseRetriever — HNSW 向量检索
│   ├── sparse.py               # SparseRetriever — tsvector BM25 关键词
│   ├── fusion.py               # RRF 排名融合（k=60）
│   ├── reranker.py             # Reranker — Cross-Encoder (BGE-Reranker-v2-m3) → LLM 降级
│   ├── query_rewriter.py       # QueryRewriter — 缓存 + 短路 + 关键词提取
│   ├── intent_router.py        # IntentRouter — 规则前置 + LLM 兜底
│   ├── citation.py             # CitationInserter — 引用标注 + 位置单调约束（文档原始位置）
│   └── vector_store.py         # PGVectorClient — HNSW + tsvector(jieba分词) + content_with_weight
├── mq/                     # 消息队列消费
│   ├── handler.py              # IngestMessageHandler 接口
│   └── client.py               # MQClient — RabbitMQ 连接管理
├── kes_mcp/                # ★ v8: MCP 知识服务（Agent 一等公民）
│   ├── auth.py                 # API Key → context_token 交换 + 自动续期 + scope 缓存
│   ├── tools.py                # search_chunks / read_document / ask_expert（McpQueryPreparator + execute()）
│   └── server.py               # MCP stdio Server — 协议层强化（Tool 场景指导 + inputSchema 示例 + kb_search_strategy Prompt）
├── models/
│   ├── chat.py, document.py, retrieval.py, config.py, llm.py
│   └── ...
├── common/                 # 共享工具（logging, exceptions, utils, tokenize_chinese）
└── tests/
    ├── unit/
    │   ├── test_pipeline_steps.py  # ETL pipeline step 测试 (10)
    │   └── test_merger.py          # TextMerger 列检测 + 合并测试 (20)
    └── integration/

注：旧 etl/ 模块将在后续清理时移除。

backend/src/main/java/com/kes/
├── KesApplication.java     # @SpringBootApplication + @EnableJpaRepositories
├── auth/
│   ├── controller/AuthController.java    # /api/auth/* (register, login, refresh, spaces, switch-space, accessible-kbs)
│   ├── controller/SpaceController.java   # /api/spaces/* (v4: admins + groups + ACE + KB + trash, DTO响应)
│   ├── controller/GroupController.java   # /api/groups/* (全局用户组 CRUD + 成员, DTO响应)
│   ├── controller/RoleController.java    # /api/roles/* (角色 CRUD, DTO响应)
│   ├── controller/AdminController.java   # /api/admin/* (全局管理员 + v7 用户CRUD/批量导入 + DTO响应)
│   ├── controller/AdminModelController.java # ★ v6: /api/admin/models/* (模型配置管理, 13 端点)
│   ├── controller/ApiKeyController.java   # ★ v8: /api/auth/mcp/* (API 密钥 CRUD + Token 交换)
│   ├── service/AdminModelService.java    # ★ v6: Provider/Model/Assignment CRUD + 脱敏 + 热重载信号
│   ├── service/AuthService.java          # 认证（register/login/refresh/switchSpace/getSpaces）
│   ├── service/SpaceService.java         # Space 生命周期 + 管理员 + 准入组管理
│   ├── service/KbService.java            # KB 全生命周期 + 回收站
│   ├── service/AceService.java           # ACE 矩阵管理
│   ├── service/PermissionQueryService.java  # KB/文档权限解析（resolveAccessibleKbIds / resolveAccessibleDocIds）
│   ├── service/AdminService.java         # 全局管理员操作 + 审计日志查询
│   ├── model/ModelProviderEntity.java    # ★ v6: 模型供应商 JPA Entity
│   ├── model/ModelConfigEntity.java      # ★ v6: 模型实例 JPA Entity
│   ├── model/ModelAssignmentEntity.java  # ★ v6: 环节映射 JPA Entity
│   ├── service/PermissionService.java    # 统一权限校验 (三层身份判定)
│   ├── service/GroupService.java         # 用户组 CRUD + 层级展开
│   ├── service/RoleService.java          # 角色 CRUD + 系统角色保护
│   ├── service/KbPermissionCache.java    # Redis kb_ids 权限缓存
│   ├── event/                            # ★ v4: 事件监听器
│   │   ├── AuditEventListeners.java      #   审计日志持久化
│   │   └── KbCleanupEventListeners.java  #   ACE 条目清理
│   ├── config/SecurityConfig.java        # Spring Security: stateless JWT
│   ├── config/JwtFilter.java             # OncePerRequestFilter: dual-token
│   ├── model/                            # 实体类（不含已删除的 v3 遗留: SpaceMember, KBMember）
│   └── repository/                       # JPA Repository 接口
├── conversation/                         # （不变）
├── document/
│   ├── controller/DocumentController.java   # /api/documents CRUD + approvals
│   ├── service/DocumentService.java         # 文档 CRUD + 审批 + MQ（跨模块调用已改为事件）
│   ├── service/IngestCallbackConsumer.java  # Consumes Python ETL callback
│   ├── service/MinioStorageService.java     # MinIO client
│   ├── event/DocumentEventListeners.java    # ★ v4: KB 生命周期→文档级联操作
│   ├── model/                               # DocumentMeta (+ spaceId 冗余), DocumentApproval, ApprovalItem
│   └── repository/
├── rag/
│   ├── controller/ChatController.java   # POST /api/chat (SSE relay, 回调方法已提取)
│   ├── client/AiServiceClient.java      # WebClient → Python
│   ├── event/AiSyncEventListeners.java  # ★ v4: 文档状态变更→Python AI 同步
│   └── model/
└── common/
    ├── annotation/                       # @RequireSpaceAdmin, @RequireGlobalAdmin (Javadoc 已修正)
    ├── aop/AdminGuard.java               # AOP 切面
    ├── config/                           # AmqpConfig, MinioConfig, RedisConfig, WebConfig
    ├── dto/SpaceDtos.java                # ★ v4: 12 种响应 DTO（替代手写 HashMap）
    ├── event/                            # ★ v4: 6 个跨模块事件 record
    │   ├── KbSoftDeletedEvent.java, KbRestoredEvent.java, KbPermanentlyDeletedEvent.java
    │   ├── DocumentStatusChangedEvent.java, DocumentPermanentlyDeletedEvent.java
    │   └── AuditLogEvent.java
    ├── service/AuditLogger.java          # 统一审计日志（发布 AuditLogEvent）
    ├── model/ApiResponse.java
    ├── exception/BusinessException.java, GlobalExceptionHandler.java
    └── util/JwtUtil.java

backend/src/test/java/com/kes/auth/service/
├── AuthServiceTest.java         # AuthService 单元测试（6 tests）
├── PermissionServiceTest.java   # PermissionService 单元测试（14 tests）
└── AdminServiceTest.java       # ★ v7: AdminService 用户管理测试（13 tests）

frontend/src/
├── main.js               # Vue app setup (Pinia + Router + ElementPlus)
├── App.vue               # Root component
├── api/
│   └── index.js          # Axios + JWT auto-refresh + SSE (chatSSE 返回 cancel 函数)
├── router/
│   └── index.js          # v4 routes: /spaces, /app/:spaceId/chat, /app/:spaceId/documents
├── stores/
│   └── auth.js           # v4: spaces, activeSpace, switchSpace（localStorage 防崩解析）
├── composables/          # ★ v4 重构：共享业务逻辑
│   ├── useKbFetcher.js       # KB 列表获取（Chat/Docs/Approvals 复用）
│   ├── useUserSearch.js      # 远程用户搜索（Settings/Groups 复用）
│   ├── useConfirmAction.js   # 确认对话框封装（全局复用）
│   ├── usePagination.js      # 分页状态管理
│   ├── useChatKbFilter.js    # Chat KB 筛选模式
│   ├── useChatMessages.js    # 消息加载/格式化
│   ├── useChatSSE.js         # SSE 发送 + streaming 状态 + cancel
│   └── useDocuments.js       # 文档 CRUD 操作
├── components/           # ★ v4 重构：UI 组件
│   ├── common/UserSearchSelect.vue  # 远程用户搜索选择器（最高复用）
│   ├── chat/                     # KbSelector, ConversationList, ChatMessage, ChatInput, SidebarFooter
│   ├── documents/                # UploadDialog, UpdateDialog
│   ├── settings/                 # AdminManagement, GroupAccessManagement, KbSettings, TrashPanel, AuditLogTable, ApiKeyManager
│   └── groups/                   # GroupTree, GroupDetail, GroupMemberTable, GroupDialog
├── utils/                # ★ v4 重构：共享工具
│   ├── datetime.js           # fmtTime 统一日期格式化
│   ├── constants.js          # ROLE_LABEL_MAP, INGEST_STATUS_MAP 等常量
│   ├── idgen.js              # generateUUID
│   └── errorHandler.js       # handleError / withErrorToast 统一错误处理
├── views/
│   ├── Login.vue          # (146行)
│   ├── SpaceSwitcher.vue  # Space selection + 修改密码对话框
│   ├── SpaceSettings.vue  # ★ 6 tab 组件编排（含 API 密钥）
│   ├── AdminDashboard.vue # 全局管理面板（含 v7 用户管理）
│   ├── ModelManagement.vue # ★ v6: 模型配置管理（Provider/Model/Assignment CRUD + 发现 + 测试）
│   ├── Chat.vue           # ★ 组件编排（130行，原296行）
│   ├── Documents.vue      # ★ 组件编排（150行，原357行）
│   └── Approvals.vue      # Approval management (admin-only)
└── public/
    └── sse-debug.html

scripts/
├── init-pgvector.sql              # v4: 全量表定义 + 系统角色种子（新安装用）
├── init-admin.sql                 # v4: admin users + global_admin + default Space + default KB
├── migration-v3.1-recycle-bin.sql # v3.1: status + expires_at on document_meta + knowledge_chunks
├── migration-v3.2-doc-time.sql    # v3.2: doc_effective_date, doc_expiry_date, doc_version
├── migration-v4-ace-permission.sql # v4: v3→v4 升级脚本（已有 v3 数据的升级用）
├── migration-v5-hnsw-fts.sql     # v5: HNSW 索引 + tsvector + content_with_weight
├── migration-v5.1-doc-space-id.sql # v5.1: document_meta 添加 space_id 列
├── migration-v6-model-config.sql  # v6: 模型配置三表 + 种子数据
├── migration-v7-user-management.sql # v7: users 加 email/status/source/must_change_password
├── migration-v8-api-keys.sql      # v8: MCP API 密钥表
├── migration-v9-enterprise-extensions.sql # v9: JSONB 扩展列 + user_identities 外部身份绑定
├── seed-permission-test.sql       # v4: 权限验证测试数据 (3 用户, 1 Space, 2 KB)
├── generate_test_docs.py          # LLM-powered test document generator
├── upload_test_docs.py            # Upload test docs via API
├── render_iwms_docs.py            # Generate IWMS project test documents (md → docx/xlsx/pdf/html)
├── verify_permissions_v3.py       # v3: 自动化权限验证脚本 (HTTP API)
├── verify_permissions_v4.py       # v4: ACE 权限模型验证脚本
├── NotoSansSC.ttf                 # Chinese font for PDF generation
└── test_docs/                     # Test document corpus (iwms: 20 documents, source/ + output/)

```


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

### Conversations (`/api/conversations`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/conversations` | List conversations in KB (kb_id param) |
| GET | `/api/conversations/{id}/messages` | Get messages |
| DELETE | `/api/conversations/{id}` | Delete (ownership check) |

### Documents (`/api/documents`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/documents` | Paginated list by KB (kb_id param) |
| POST | `/api/documents` | Upload (file + kb_id + optional effective_date/expiry_date/version → MinIO + MQ + approval) |
| GET | `/api/documents/{id}` | Single document detail |
| GET | `/api/documents/{id}/file` | Download/preview file |
| PUT | `/api/documents/{id}` | Update file (admin: direct, member: approval) |
| PUT | `/api/documents/{docId}/metadata` | Edit effective_date / expiry_date / version (**仅管理员**) |
| DELETE | `/api/documents/{id}` | Soft delete (**仅管理员**) |
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
| GET | `/api/admin/models/active` | **Python 用**：获取全部激活配置 |
| GET | `/api/admin/models/version` | 配置版本号（热重载用） |

### Python AI (`/v1`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat` | SSE RAG endpoint (kb_ids in filter_params) |
| GET | `/v1/health` | Component health check |
| POST | `/v1/documents/status` | Sync document status to knowledge_chunks (internal, Java-triggered) |
| DELETE | `/v1/documents/{doc_id}/chunks` | Permanently delete document's vector chunks (internal, Java-triggered) |
| POST | `/v1/admin/models/discover` | ★ v6: 模型发现（供 Java 代理） |
| POST | `/v1/admin/models/test` | ★ v6: 连通性测试（供 Java 代理） |

### MCP 知识服务 ★ v8
MCP stdio Server — 启动: `KES_API_KEY=xxx KES_SPACE_ID=sp-001 python -m kes_mcp.server`

以外部 Agent 为一等公民设计，协议层提供完整的 query 构造指导、场景选择规则和行为指导 Prompt。

| Tool | 参数 | 说明 |
|------|------|------|
| `search_chunks` | query, kb_ids, top_k, include_context, **context_hint**, **focus_aspects**, **doc_type** | 混合检索文档块 → 结构化元数据（来源/页码/相关性分数）。**纯检索，不调 LLM** |
| `read_document` | doc_id | 读取文档完整元数据 + 内容（scope 检查） |
| `ask_expert` | query, kb_ids, top_k, **context_hint**, **focus_aspects** | 检索 → LLM 生成 → 引用标注。**context_hint 注入 LLM 背景** |

★ 新增参数（让 Agent 透传已知上下文）：
- `context_hint`: Agent 已知的用户背景（环境/版本/已尝试步骤），不参与检索，仅注入 LLM 生成阶段
- `focus_aspects`: 限定关注方面（installation/configuration/troubleshooting/api_reference/best_practices/security/version_history）
- `doc_type`: 限定文档类型（manual/policy/report/guide/specification/any）

| Resource | 说明 |
|----------|------|
| `doc://catalog` | 有权限的 KB 列表（含 doc_count 等概览信息），建议检索前先调用 |

| Prompt | 类型 | 说明 |
|--------|------|------|
| **`kb_search_strategy`** | ★ 行为指导 | 教授 Agent 如何提取关键实体、选择 Tool、构造高质量 query |
| `qa_template` | 结果使用 | 标准 RAG 问答输出模板（如何使用检索结果） |
| `document_analysis` | 结果使用 | 文档分析模板（核心要点/风险/建议） |

**检索链路**: `McpQueryPreparator.prepare()`（jieba 实体提取，+5ms，零 LLM） → `RetrievalOrchestrator.execute()`（共享执行层：HybridSearch + Reranker）

**依赖**: `mcp` SDK, `httpx`, `jieba`, 复用 `RetrievalOrchestrator.execute()` + `ContextAssembler`

## Database Tables (v6~v9 新增)

| Table | Version | Description |
|-------|---------|-------------|
| `model_providers` | v6 | 模型供应商配置（DashScope/Ollama/BGE...） |
| `model_configs` | v6 | 模型实例（qwen-plus/text-embedding-v3...） |
| `model_assignments` | v6 | 环节→模型映射（chat/rewrite/embedding...） |
| `system_config` | v6 | 系统级键值配置，`model_config_version` 驱动热重载 |
| `api_keys` | v8 | MCP API 密钥 — 用户自助管理，scope_kb_ids 预留 |
| `user_identities` | v9 | 外部身份绑定 — 一个 KES 用户绑定多个 IdP 账号 |

### v7~v9 Schema 扩展

| 表 | 新增列 | 版本 | 说明 |
|----|--------|------|------|
| `users` | `email`, `status`, `source`, `must_change_password` | v7 | 用户管理增强 |
| `users` | `metadata JSONB` | v9 | 企业自定义字段（工号/部门/职级等） |
| `user_groups` | `external_id`, `source`, `metadata JSONB` | v9 | 外部组标识 + 来源 + 扩展 |
| `spaces` | `metadata JSONB` | v9 | 空间级扩展（成本中心/组织单元等） |
| `knowledge_bases` | `metadata JSONB` | v9 | KB 级扩展（分类标签等） |

---

## ★ v8 MCP 生产化 — 2026-06-25 / 更新 2026-06-27

### 2026-06-27 检索链路重构：Agent 一等公民

**核心变更**：拆分 Web Chat 和 MCP 的查询准备层，共享检索执行层。

| 组件 | 变更 |
|------|------|
| `retrieval/orchestrator.py` | 新增 `execute()` 共享执行层（HybridSearch → Reranker）；`retrieve()` 保留但改为委托 `execute()` |
| `retrieval/mcp_query_preparator.py` | ★ 新建 — jieba 实体提取 + focus_aspects 映射，纯本地 ~5ms，零 LLM |
| `kes_mcp/tools.py` | 改用 `McpQueryPreparator.prepare()` → `orchestrator.execute()` |
| `kes_mcp/server.py` | 协议层全面重写 — Tool description 含 query 构造指导 + 场景选择；新增 context_hint/focus_aspects/doc_type 参数；新增 kb_search_strategy Prompt |

**设计原则**：
1. 外部 Agent 是一等公民，MCP 场景不是 Web Chat 的退化子集
2. 查询准备层语义相反：Web Chat 做语义收敛（模糊→精确），MCP 做语义扩展（精确→丰富）
3. MCP 检索阶段零 LLM 调用——Agent 自己就是 LLM 驱动的
4. 查询质量保障前置到 MCP 协议层——通过 Tool description/inputSchema/Prompt 指导 Agent 构造高质量输入

### A+C 混合权限模型

MCP 三个 Tool 已完整实现并接入三层权限交集：

```
effective_kb_ids = tool_kb_ids ∩ ace_kb_ids ∩ scope_kb_ids
                   (Agent传参)  (用户ACE权限)  (Key白名单)
```

### api_keys 表新增

| 字段 | 说明 |
|------|------|
| `scope_kb_ids` | JSONB，Key 级 KB 白名单。null = 无限制（继承用户完整 ACE 权限） |

### kes_mcp/ 模块状态

| 组件 | 状态 | 说明 |
|------|------|------|
| `auth.py` | ✅ | API Key → Token 交换 + scope 缓存 + 自动续期 + 快速失败 |
| `tools.py search_chunks` | ✅ | McpQueryPreparator + execute()，支持 context_hint / focus_aspects |
| `tools.py read_document` | ✅ | 文档元数据 + 内容 + scope 检查 |
| `tools.py ask_expert` | ✅ | McpQueryPreparator + execute() + LLM 生成 + context_hint 注入 |
| `server.py` | ✅ | stdio MCP Server，3 Tools + 1 Resource + 3 Prompts（含 kb_search_strategy） |
| `retrieval/mcp_query_preparator.py` | ✅ ★ 新增 | jieba 提取 + focus_aspects 映射 + 正则实体捕获（版本号/错误码/文件名） |

### 其他关键修复

- `SystemBootstrap.java` — 首次启动 users 为空时自动创建 admin 账号
- `AdminService.batchImportUsers` — CSV 支持 `group_name` 列，导入时自动归属组
- `GroupService.addMembers` — 批量添加组成员端点
- `admin_action_logs` — space_id/target_id 改为可空（全局操作用）
- `user_groups.name` — 加 UNIQUE 约束（防 AD 同步重复）

### 测试覆盖

```
Java:   33 tests (Auth 6 + Permission 14 + AdminService 13) ✅
Python: 30 tests (Merger 20 + Pipeline Steps 10) ✅
```
