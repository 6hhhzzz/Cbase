# 代码重构计划

> **创建日期**: 2026-06-22
> **状态**: 进行中
> **目标**: 降低耦合度，提升可测试性和可扩展性，为后续功能迭代扫清障碍

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Frontend (Vue 3 :5173)                         │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌─────────────┐  │
│  │ Chat.vue │ │Docs.vue  │ │Settings.vue│ │Groups.vue│ │AceConfig.vue│  │
│  │ (296行)  │ │(357行)   │ │(331行)     │ │(329行)   │ │(287行)      │  │
│  └────┬─────┘ └────┬─────┘ └─────┬──────┘ └────┬─────┘ └──────┬──────┘  │
│       └─────────────┴─────────────┴─────────────┴──────────────┘         │
│                         │ api/index.js (376行)                            │
│                         │ auth.js store (89行)                            │
│              components/ hooks/ services/ utils/ — 全空                   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │ HTTP/SSE
┌────────────────────────────┴────────────────────────────────────────────┐
│                     Java Backend (Spring Boot :8080)                     │
│                                                                          │
│  ┌─────────────────── Controller Layer ──────────────────────────┐      │
│  │ AuthCtrl  SpaceCtrl(424行)  DocCtrl  ChatCtrl  GroupCtrl  ... │      │
│  └────────────────────────┬──────────────────────────────────────┘      │
│                           │                                              │
│  ┌─────────────────── Service Layer ─────────────────────────────┐      │
│  │  ┌──────────────────────┐  ┌──────────────┐  ┌───────────────┐      │
│  │  │  AuthService (926行) │  │ DocumentSvc  │  │ConversationSvc│      │
│  │  │  ★ 上帝类,16个依赖   │─→│  (495行)     │  │  (97行)       │      │
│  │  │  8+职责混合           │  │              │  │               │      │
│  │  └─────────┬────────────┘  └──────┬───────┘  └───────────────┘      │
│  │            │                      │                                   │
│  │  ┌─────────┴──────────┐  ┌───────┴────────┐  ┌───────────────┐      │
│  │  │ PermissionService  │  │ MinioStorage   │  │ GroupService  │      │
│  │  │ (244行)            │  │ Service(99行)  │  │ (315行)       │      │
│  │  └────────────────────┘  └────────────────┘  └───────────────┘      │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐       │
│  │  │ KbPermCache   │  │ RoleService  │  │ IngestCallback       │       │
│  │  │ (123行)       │  │ (115行)      │  │ Consumer (99行)      │       │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘       │
│  └─────────────────────────────────────────────────────────────────────┘      │
│                           │                                              │
│  ┌─────────────────── Repository Layer (18 JPA repos) ────────────┐     │
│  └───────────────┬──────────────────────────────────┬──────────────┘     │
│                  │                                  │                    │
│            PostgreSQL :5432                    Redis :6379               │
│         (业务数据+向量搜索)               (session/kb_ids缓存)            │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │ HTTP / RabbitMQ
┌──────────────────────────┴──────────────────────────────────────────────┐
│                    Python AI Service (FastAPI :8000)                     │
│                                                                          │
│  ┌─ API ────────┐ ┌─ Core ────────────┐ ┌─ ETL (994行) ───────────┐    │
│  │ chat.py(168) │ │ ContextAssembler  │ │ Pipeline ★上帝类(196行)  │    │
│  │ documents.py │ │ SummaryEngine     │ │  parsers/ (6个解析器)     │    │
│  │ health.py    │ │ HistoryManager    │ │  chunkers/, sanitizers/   │    │
│  └──────┬───────┘ └────────┬──────────┘ └───────────┬──────────────┘    │
│         │                  │                        │                    │
│  ┌──────┴──────────────────┴────────────────────────┴──────────────┐    │
│  │  LLM (559行)                 Retrieval (405行)    MQ (196行)     │    │
│  │  BaseLLM/BaseEmbedding ABC  PGVectorClient(244行) RabbitMQ Client│    │
│  │  OpenAI-compatible适配器    EmbeddingWrapper      IngestHandler   │    │
│  │  ModelFactory(注册表)       Reranker(no-op桩)                    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│              pgvector :5432    RabbitMQ :5672    MinIO :9000            │
└──────────────────────────────────────────────────────────────────────────┘
```

### 数据流（RAG 问答）

```
用户输入 → Vue Chat.vue → fetch SSE → Java ChatController
  → AuthService.resolveAccessibleKbIds() → AiServiceClient(WebClient)
  → Python /v1/chat → Embedding → PGVector search → Context Assembly
  → LLM stream → SSE tokens → Java relay → 前端渲染
  → 完成后: Java saveMessage → Python cache to Redis
```

### 数据流（文档摄入）

```
用户上传 → Java DocumentService → MinIO + DocumentMeta
  → RabbitMQ document.ingest → Python ETL Pipeline
  → MinIO下载 → 解析 → 清洗 → 分块 → Embedding → pgvector插入
  → RabbitMQ document.ingest.callback → Java IngestCallbackConsumer
```

---

## 重构条目

### 🔴 P0 — 严重问题（阻塞性，优先处理）

- [x] **1. AuthService 上帝类拆分** ✅ 已完成 — 2026-06-22
  - **文件**: `backend/src/main/java/com/kes/auth/service/AuthService.java`（926行）
  - **问题**: 16个依赖注入、30+公共方法、8种以上职责混合（认证/空间管理/KB管理/ACE管理/权限解析/回收站/审计/全局管理），跨 auth/document/rag 三个包引入依赖
  - **方案**: 拆分为 5 个独立 Service：
    - `AuthService` — 仅保留认证相关（register/login/refresh/switchSpace/changePassword）
    - `SpaceService` — 空间管理（createSpace/archiveSpace/getSpaceAdmins/addSpaceAdmin/removeSpaceAdmin/transferOwnership/getSpaceGroups/addSpaceGroup/removeSpaceGroup）
    - `KbService` — KB 全生命周期（createKb/listKbs/updateKb/softDeleteKb/restoreKb/permanentDeleteKb）
    - `AceService` — ACE 矩阵管理（getAces/createAce/updateAce/deleteAce）
    - `AdminService` — 全局管理员操作（getAllSpaces/globalArchiveSpace/globalDeleteSpace/globalRestoreSpace/listAllUsers/setGlobalAdmin）
  - **新文件**: `backend/src/main/java/com/kes/auth/service/SpaceService.java`, `KbService.java`, `AceService.java`, `AdminService.java`
  - **Controller 调整**: `SpaceController` 中的端点分别委托给对应的新 Service

- [x] **2. 前端组件与 Composable 提取** ✅ 已完成 — 2026-06-22
  - **文件**: `frontend/src/views/*.vue`（10个视图文件，components/hooks/services/utils 全部为空）
  - **问题**: 零组件分解、零复用、零可测试性。3个文件超过300行，5个超过200行
  - **方案**:
    - **Composables 提取**:
      - `useChatSSE.js` — SSE 流式连接管理（从 Chat.vue 提取）
      - `useDocuments.js` — 文档 CRUD 操作（从 Documents.vue 提取）
      - `useKbFilter.js` — KB 列表获取与筛选（从 Chat/Documents/Approvals 提取，消除重复调用 `authApi.getAccessibleKBs()`）
      - `useConversations.js` — 会话列表管理
    - **UI 组件提取**:
      - `ChatSidebar.vue` — 聊天侧边栏（会话列表 + KB选择器）
      - `ChatMessage.vue` — 单条消息渲染
      - `UploadDialog.vue` — 文档上传对话框
      - `KbSelector.vue` — KB 下拉选择器
      - `MemberList.vue` — 成员列表（SpaceSettings + GroupManagement 共享）
    - **工具函数提取**:
      - `utils/datetime.js` — `fmtTime()` 统一时间格式化
      - `utils/constants.js` — 角色映射、状态映射等常量
  - **创建目录文件**: `frontend/src/composables/`, `frontend/src/components/`, `frontend/src/utils/`

- [x] **3. Java 跨模块依赖解耦** ✅ 已完成 — 2026-06-22
  - **文件**: `backend/src/main/java/com/kes/auth/service/AuthService.java`, `backend/src/main/java/com/kes/document/service/DocumentService.java`
  - **问题**: `auth` 包导入 `DocumentMetaRepository`（document 包）和 `AiServiceClient`（rag 包）；`document` 包导入 `AceRepository`（auth 包）和 `AiServiceClient`（rag 包）。三个包互相引用
  - **方案**:
    - 引入 Application Service 层（`com.kes.application.*`）专门做跨模块编排，模块内部的 Service 只依赖本模块的 Repository
    - 或使用 Spring `ApplicationEventPublisher` 发布领域事件，各模块订阅事件解耦
    - 具体解耦点：
      - KB 删除时同步 Python 文档状态 → 发布 `KbDeletedEvent`，由 rag 模块的监听器处理
      - KB 永久删除时清理文件 → 发布 `KbPermanentDeletedEvent`，由 document 模块的监听器处理
      - 文档永久删除时清理 ACE 条目 → 发布 `DocumentPermanentDeletedEvent`，由 auth 模块的监听器处理

- [x] **4. Python ETL Pipeline 步骤拆分** ✅ 已完成 — 2026-06-22
  - **文件**: `ai-service/etl/pipeline.py`（196行）
  - **问题**: 单个类处理下载→解析→OCR→清洗→分块→元数据注入→pgvector写入共7个步骤
  - **方案**: 拆分为独立 Step 类，通过 Pipeline Builder 组合：
    - `DownloadStep` — MinIO 文件下载
    - `ParseStep` — 解析器选择与调用
    - `SanitizeStep` — PII 清洗
    - `ChunkStep` — 文本分块
    - `EmbedStep` — 向量化
    - `IndexStep` — pgvector 写入
    - `ETLPipeline` 变为轻量编排器，按顺序调用 Step
  - **创建文件**: `ai-service/etl/steps/__init__.py`, `download.py`, `parse.py`, `sanitize.py`, `chunk.py`, `embed.py`, `index.py`

- [x] **5. Python 依赖注入规范化** ✅ 已完成 — 2026-06-22
  - **文件**: `ai-service/api/app.py`（205行）
  - **问题**: `lifespan` 函数中 50+ 行手动创建所有依赖实例，新增依赖必须修改此文件
  - **方案**: 使用 FastAPI `Depends` 或 `dependency-injector` 库做声明式 DI
    - 每个模块提供 `get_*` 工厂函数
    - `app.py` 的 lifespan 简化为读取配置 + 初始化连接池
    - 路由函数通过 `Depends(get_llm_client)` 等获取依赖
  - **注意**: 需要考虑异步资源生命周期管理（pgvector pool、RabbitMQ connection）

- [x] **6. 补充核心路径测试** ✅ 已完成 — 2026-06-22
  - **文件**: 全局 — Java `src/test/` 空，Python `tests/` 空，前端无测试文件
  - **问题**: 零测试覆盖，重构无安全网
  - **方案**: 至少覆盖以下核心路径：
    - **Java**: `AuthService.resolveAccessibleKbIds()` 单元测试、`PermissionService` 三层权限校验测试
    - **Python**: ETL Pipeline 端到端测试（PDF→chunks→pgvector）、`/v1/chat` SSE 流集成测试
    - **前端**: `chatSSE()` 函数单元测试（mock fetch）、auth store 状态转换测试

---

### 🟡 P1 — 中等问题（规划后逐个处理）

- [x] **7. SpaceController 拆分**
  - **文件**: `backend/src/main/java/com/kes/auth/controller/SpaceController.java`（424行）
  - **问题**: 20+端点全部在一个 Controller，路由定义不清晰
  - **方案**: 拆分为 `SpaceController`（空间管理）、`KbController`（KB CRUD）、`AceController`（ACE 矩阵）
  - **新建文件**: `backend/src/main/java/com/kes/auth/controller/KbController.java`, `AceController.java`

- [x] **8. DocumentService 职责分离**
  - **文件**: `backend/src/main/java/com/kes/document/service/DocumentService.java`（495行）
  - **问题**: 混合文件验证、MinIO操作、审批状态机、MQ发布、审计日志
  - **方案**: 拆出 `ApprovalService`（审批状态机 + 审批列表）、`DocumentIndexService`（MQ发布 + IngestCallback 处理）

- [x] **9. 引入 DTO 映射层** ✅ 已完成 — 2026-06-22
  - **文件**: 所有 Controller 类
  - **问题**: 每个 Controller 手动 `new HashMap<>()` 构建 API 响应，相同模式出现 ~40 次。手动映射容易拼写错误，无编译检查
  - **方案**:
    - 为每个实体创建对应的 DTO 类（record）
    - 使用 MapStruct 接口做 Entity → DTO 转换
    - Controller 返回强类型 DTO 而非 Map
  - **依赖**: 添加 `mapstruct` 和 `mapstruct-processor` 到 `pom.xml`

- [x] **10. 审计日志统一**
  - **文件**: `AuthService.java:logAction()`, `DocumentService.java:logAction()`
  - **问题**: 两个服务中有几乎相同的审计日志记录方法
  - **方案**: 提取 `AuditLogger` 服务类，通过 Spring 事件 `@EventListener` 统一记录
  - **新建文件**: `backend/src/main/java/com/kes/common/service/AuditLogger.java`

- [x] **11. 前端重复工具函数提取**
  - **文件**: `frontend/src/views/Chat.vue`, `Documents.vue`, `Approvals.vue`, `SpaceSettings.vue`, `SpaceSwitcher.vue`
  - **问题**: `fmtTime`、角色映射 `{owner:'拥有者', admin:'管理员', member:'成员'}`、KB 获取在 3+ 视图复制
  - **方案**:
    - `utils/datetime.js` — 统一 `fmtTime(ts)`
    - `utils/constants.js` — `ROLE_LABEL_MAP`、`KB_VISIBILITY_LABELS` 等常量
    - `composables/useKbList.js` — 统一 KB 列表获取 + 缓存

- [x] **12+13. Python 解析器错误处理模板 + 表格去重** ✅ 已完成 — 2026-06-22
  - **文件**: `ai-service/etl/parsers/*.py`（6个解析器）
  - **问题**: 每个解析器有相同的 `ImportError → return空` 和 `Exception → log + return空` 样板代码，每个约15行重复
  - **方案**: 在 `BaseParser` 中增加 `_safe_parse()` 模板方法或 `@handle_parse_errors` 装饰器

- [x] **13. Python 表格转 Markdown 去重**
  - **文件**: `ai-service/etl/parsers/docx.py:_table_to_markdown()`, `xlsx.py:_rows_to_markdown()`
  - **问题**: 两个函数功能相同但实现有细微差异（列宽计算方式不同）
  - **方案**: 提取到 `ai-service/etl/common/table_utils.py` 作为统一函数

- [x] **14. PGVectorClient 移除内部 embedding 调用** ✅ 已完成 — 2026-06-22
  - **文件**: `ai-service/retrieval/vector_store.py`（244行）
  - **问题**: `insert_chunks()` 内部调用 embedding，而 Pipeline 也有 embedding 实例。双重调用点导致行为不一致
  - **方案**: 由 Pipeline 在调用 `insert_chunks()` 之前完成 embedding，`PGVectorClient` 只负责存储和检索

- [x] **15. 前端统一错误处理策略** ✅ 已完成 — 2026-06-22
  - **文件**: `frontend/src/api/index.js`, `frontend/src/views/*.vue`
  - **问题**: 三种错误处理模式混杂：静默 `catch {}`、仅依赖拦截器、视图级 `ElMessage.error`
  - **方案**: 统一为三层策略：
    - API 层（axios 拦截器）→ 全局错误通知 + 标准化错误对象
    - Composable 层 → 业务错误转换
    - UI 层 → 仅处理需要特定 UI 反馈的错误

- [x] **16. ChatController SSE 流消费方式统一** ✅ 已完成 — 2026-06-22
  - **文件**: `backend/src/main/java/com/kes/rag/controller/ChatController.java`
  - **问题**: `AiServiceClient.chat()` 返回 `Flux<String>`（响应式），但通过 `.subscribe()` 阻塞消费。响应式与命令式混用
  - **方案**: 统一使用 Spring MVC 的 `SseEmitter` 或全部使用 WebFlux 响应式链

- [x] **17. SummaryEngine 方法拆分 + 配置化** ✅ 已完成 — 2026-06-22
  - **文件**: `ai-service/core/context/summary_engine.py`（150行）
  - **问题**: `maybe_update_summary()` 单方法 82 行，混合锁管理/轮次计数/溢出检测/LLM生成/压缩/失败追踪
  - **方案**: 拆分为 `_check_trigger()`, `_detect_overflow()`, `_generate_summary()`, `_compress_summary()`

---

### 🟢 P2 — 轻微问题（低优先级，渐进改善）

- [x] **18. Python 硬编码配置迁移**
  - **文件**: 散布在 `ai-service/etl/`, `api/chat.py`, `core/context/`, `retrieval/` 中
  - **问题**: 15+ 处硬编码值（`chunk_size=512`, `chunk_overlap=50`, `STREAM_TOTAL_TIMEOUT=110.0`, `SUMMARY_SOFT_LIMIT=1500`, `COMPRESS_TARGET=800`, `SUMMARIZE_TRIGGER_ROUNDS=10`, `batch_size=8/100`, `_max_retries=1`, `VECTOR(1024)`, `lists=1024`, `DEFAULT_TTL=604800`）
  - **方案**: 全部迁移到 `config/llm.yaml` + `Settings` 模型，通过 `get_settings()` 访问

- [x] **19. 清理 v3 遗留实体**
  - **文件**: `backend/src/main/java/com/kes/auth/model/SpaceMember.java`, `KBMember.java`
  - **对应仓库**: `SpaceMemberRepository.java`, `KBMemberRepository.java`
  - **问题**: 实体和仓库存在但无任何运行时代码引用（v3 遗留，已被 space_admins + space_groups 替代）
  - **方案**: 确认无引用后删除 4 个文件，添加数据库迁移脚本记录

- [x] **20. Reranker 实现或标注为桩**
  - **文件**: `ai-service/retrieval/reranker.py`（43行）
  - **问题**: `rerank()` 直接返回输入不变，是 no-op。外部调用者无法判断是否真正做了重排序
  - **方案**: 选项A — 集成 bge-reranker 或 Cohere Rerank API；选项B — 明确标注为桩，日志输出 warning

- [x] **21. 前端 SSE 取消功能**
  - **文件**: `frontend/src/views/Chat.vue`（第180行）, `frontend/src/api/index.js:chatSSE()`
  - **问题**: `chatSSE()` 返回取消函数但 Chat.vue 丢弃了，用户无法中断流式响应
  - **方案**: 存储 `cancel` 函数引用，在路由导航守卫和"停止生成"按钮中调用

- [x] **22. Chat.vue v-html XSS 风险**
  - **文件**: `frontend/src/views/Chat.vue:56` — `v-html="formatContent(msg.content)"`
  - **问题**: LLM 返回的内容直接用 `v-html` 渲染，仅有 `\n → <br>` 替换
  - **方案**: 使用 DOMPurify 或仅保留 `<br>` 标签的严格白名单净化

- [x] **23. ViewUrl 令牌暴露修复**
  - **文件**: `frontend/src/api/index.js:189` — `documentsApi.viewUrl()`
  - **问题**: `context_token` 以查询参数形式暴露在文档预览 URL，会出现在浏览器历史/服务器日志/书签中
  - **方案**: 后端改用短期签名 URL（预签名 MinIO URL），前端不再传递 token

- [x] **24. Python 缺少 Sanitizer/Chunker ABC**
  - **文件**: `ai-service/etl/sanitizers/presidio_sanitizer.py`, `ai-service/etl/chunkers/text_chunker.py`
  - **问题**: 解析器有 `BaseParser` ABC，但清洗器和分块器没有对应的抽象基类
  - **方案**: 定义 `BaseSanitizer` ABC（`sanitize(text) -> str`）和 `BaseChunker` ABC（`chunk(text, metadata) -> list[DocumentChunk]`）
  - **新建文件**: `ai-service/etl/sanitizers/base.py`, `ai-service/etl/chunkers/base.py`

- [x] **25. PGVector 维度动态生成**
  - **文件**: `ai-service/retrieval/vector_store.py:74` — DDL `VECTOR(1024)` 硬编码
  - **问题**: 如果配置中 embedding dimension 改为其他值（如 768），DDL 与配置不一致会导致 SQL 错误
  - **方案**: 使用 `self._config.dimension` 动态生成 DDL

- [x] **26. Javadoc 与实际类名不一致**
  - **文件**: `backend/src/main/java/com/kes/common/annotation/RequireSpaceAdmin.java`, `RequireGlobalAdmin.java`
  - **问题**: 注解的 Javadoc 引用 `PermissionAspect`，但实际 AOP 类是 `AdminGuard`
  - **方案**: 更新 Javadoc 引用为 `AdminGuard`

- [x] **27. 前端 localStorage 防御性解析**
  - **文件**: `frontend/src/stores/auth.js`
  - **问题**: `JSON.parse(localStorage.getItem(...))` 在数据损坏时抛出运行时异常，用户白屏
  - **方案**: 包装为 try-catch，失败时降级到默认值并清除损坏数据

---

## 重构执行记录

| 日期 | 条目 | 状态 | 备注 |
|------|------|------|------|
| 2026-06-22 | 全部 | 📋 待开始 | 初始分析完成，共27个重构条目 |
| 2026-06-22 | #1 | ✅ 已完成 | AuthService 拆分为 7 个独立 Service，926行→236行 |
| 2026-06-22 | #17 | ✅ 已完成 | SummaryEngine 82行方法→7个方法 + 4参数配置化 |

---

## 重构原则

1. **每次只做一个条目**，完成后验证系统功能正常再继续
2. **每个条目在独立分支上完成**，通过验证后合并
3. **先写测试（如果可以）**，确保重构前后行为一致
4. **重要条目完成后更新相关文档**（CLAUDE.md、init-pgvector.sql、注释）
5. **遇阻先记录**，不强行推进可能破坏现有功能的改动
