# 代码地图

完整的 Key Source Locations 文件树，覆盖 ai-service、backend、frontend、scripts。

> 从 CLAUDE.md 提取，原始行范围: L387-L674

## Key Source Locations

```
ai-service/
├── api/
│   ├── app.py              # FastAPI app factory, lifespan DI（★ v12.1: SummaryConfig 接入 SummaryEngine）
│   ├── chat.py             # POST /v1/chat (SSE RAG endpoint, Depends 注入)
│   ├── chat_errors.py      # ★ v12.1: 错误消息映射 — 异常→中文提示（从 chat.py 提取）
│   ├── admin_models.py     # ★ v6: POST /v1/admin/models/{discover,test} (供 Java 代理)
│   ├── dependencies.py     # 声明式 Depends 函数（get_llm, get_pgvector_client 等 8 个）
│   ├── documents.py        # POST /v1/documents/status, DELETE /v1/documents/{doc_id}/chunks
│   └── health.py           # GET /v1/health (component health check, Depends 注入)
├── core/
│   ├── config/settings.py      # YAML + env var config loading
│   ├── config/models.yaml       # ★ v12: 模型配置中心 — providers/models/assignments 统一配置
│   ├── config/models_config.py  # ★ v12: Pydantic 模型 + YAML 加载器 + 原子写入 + 校验
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
├── chunking/               # ★ v5: 语义分块引擎
│   ├── orchestrator.py         # ChunkOrchestrator — 策略选择 + 上下文注入（auto 默认 ParentChildChunker）
│   ├── base.py                 # BaseChunker ABC
│   ├── models.py               # Chunk, ChunkRelation（parent_id/children_ids/prev_id/next_id）
│   ├── parent_child_chunker.py # ★ ParentChildChunker — 两级分块（Parent ~500t → Child ~150t）
│   ├── token_chunker.py        # TokenChunker — token 感知 + 分隔符优先级
│   ├── title_chunker.py        # TitleChunker — 标题层级分块 + 父子关系
│   ├── merge.py                # merge_chunks — 跨 block 合并 + 保留 parent 信息
│   └── enrich.py               # ContextEnricher — 表格/图片上下文注入
├── llm/
│   ├── base.py
│   ├── factory.py
│   ├── model_pool.py           # ★ v12: 动态模型池（从 models.yaml 读配置, 文件热重载, 降级到 Java HTTP）
│   ├── model_factory.py        # ★ v12.1: 模型实例工厂（LLM/Embedding/Reranker/OCR + HTTP 降级工厂）
│   ├── config_watcher.py       # ★ v12.1: 配置热重载 — mtime 监控 + 异步回调
│   ├── openai_compatible.py
│   ├── rerank_llm.py           # ★ v5: LLM 降级 Reranker
│   └── prompts/
│       ├── rag.py              # RAG 问答 prompt
│       ├── summary.py          # 摘要 prompt
│       ├── rewrite.py          # ★ v5: Query 改写 prompt
│       ├── intent.py           # ★ v5: 意图分类 prompt
│       ├── rerank.py           # ★ v5: LLM rerank 降级 prompt
│       ├── hyde.py             # ★ v12: HyDE 假答案生成 prompt
│       ├── query_plan.py       # ★ v12: DAG 拆解 + 三维提取 prompt
│       ├── preprocess.py       # ★ v12: 三合一预处理 prompt
│       └── metadata.py         # ★ v10: 元数据提取 prompt（ETL LlmMetadataEnrichStep 用）
├── retrieval/              # ★ v5: 混合检索引擎（借鉴 RAGFlow Dealer）
│   ├── orchestrator.py         # RetrievalOrchestrator — 纯编排层，委托给 DAGExecutor/CriticAgent/QueryPlanner（★ v12.1 精简至 485 行）
│   ├── dag_executor.py         # ★ v12.1: DAGExecutor — DAG 执行 + 3D 提取 + HyDE + 简单检索路径（从 orchestrator 提取）
│   ├── routing.py              # ★ v12.1: 查询路由 — 闲聊检测 + Planner 触发规则（纯函数，从 orchestrator 提取）
│   ├── circuit_breaker.py      # ★ v12.1: DAG 熔断器（独立类，从 orchestrator 提取）
│   ├── dedup.py                # ★ v12.1: 三层去重 — chunk_id / 内容 / 文档 + 相邻合并（纯函数，从 orchestrator 提取）
│   ├── context_assembler.py    # ★ v12.1: 上下文组装 + Grounding 校验（从 orchestrator 提取）
│   ├── mcp_query_preparator.py # ★ MCP 查询准备器 — jieba 实体提取 + focus_aspects 映射（零 LLM，~5ms）
│   ├── models.py               # ScoredChunk, IntentResult, RewriteResult, RetrievalContext
│   ├── hybrid_search.py        # HybridSearch — Dense ∥ Sparse → RRF
│   ├── dense.py                # DenseRetriever — HNSW 向量检索
│   ├── sparse.py               # SparseRetriever — tsvector BM25 + SPLADE 神经词扩展（★ v12 三路检索）
│   ├── splade_model.py          # ★ v12: SPLADE 神经稀疏检索模型 — query 端词扩展，填补 Dense/BM25 间隙
│   ├── fusion.py               # RRF 排名融合（k=60, v12 三路融合）
│   ├── reranker.py             # Reranker — API Reranker (DashScope gte-rerank) → Cross-Encoder (BGE-Reranker-v2-m3) → LLM 降级 → 截断
│   ├── query_rewriter.py       # QueryRewriter — 缓存 + 短路 + 关键词提取（v12 降级为 fallback）
│   ├── query_preprocessor.py   # ★ v12: QueryPreprocessor — 三合一 SLM 预处理（指代+省略+语义）
│   ├── query_planner.py        # ★ v12: QueryPlanner — LLM 驱动 DAG 拆解 + 三维提取 + 证据锚点校验
│   ├── intent_router.py        # IntentRouter — 规则前置 + LLM 兜底（向后兼容层）
│   ├── critic.py               # ★ v12: Critic Agent — 置信度检查 + 知识验证 + 补充检索 + 兜底反问
│   ├── semantic_cache.py       # ★ v12: Semantic Cache — 高频查询拦截，50ms 响应
│   ├── citation.py             # CitationInserter — 引用标注 + 位置单调约束（文档原始位置）
│   ├── feedback/               # ★ v12.1: 检索质量追踪子包（从 feedback.py 拆分）
│   │   ├── __init__.py          #   RetrievalTracer — 组合 facade（builder + repository + cache）
│   │   ├── builder.py           #   TraceBuilder — 纯数据转换，从检索上下文构建 7 模块 trace dict
│   │   ├── repository.py        #   FeedbackRepository — asyncpg INSERT/UPDATE 数据库操作
│   │   └── cache.py             #   TraceCache — MCP 内存缓存，TTL 自动过期
│   ├── judge.py                # ★ v12: JudgeEvaluator — LLM-as-a-Judge 四维评估（忠实度/答案相关性/上下文相关性/答案正确性，5 档 rubric + few-shot + CoT）
│   ├── trace_context.py        # ★ v12.1: TraceContext — 统一追踪（SpanHandle/SpanSnapshot → Langfuse span 树 + DB trace dict）
│   └── vector_store/           # ★ v12.1: PG 向量存储子包（从 vector_store.py 拆分）
│       ├── __init__.py          #   PGVectorClient — 组合 facade（connection + search + repository）
│       ├── connection.py        #   PGConnectionManager — 连接池 + DDL + 索引管理
│       ├── search.py            #   VectorSearchService — HNSW 向量检索 + kb_id 权限过滤
│       └── repository.py        #   ChunkRepository — 批量写入 + 删除 + 状态更新
├── mq/                     # 消息队列消费
│   ├── handler.py              # IngestMessageHandler 接口
│   └── client.py               # MQClient — RabbitMQ 连接管理
├── etl/
│   └── steps/
│       ├── metadata_enrich_step.py      # ★ v10: MetadataEnrichStep — ETL 步骤，提取标题/层级/类型 → metadata JSONB
│       └── llm_metadata_enrich_step.py  # ★ v10: LlmMetadataEnrichStep — LLM 增强元数据提取（标题 chunks 批量 LLM 调用）
├── kes_mcp/                # ★ v8: MCP 知识服务（Agent 一等公民）
│   ├── auth.py                 # API Key → context_token 交换 + 自动续期 + scope 缓存
│   ├── tools.py + tools_def.py # search_chunks（唯一 Tool）+ report_quality（反馈上报）+ inputSchema 含 query 指导/时间过滤/focus_aspects
│   ├── resources_def.py        # 5 个 Resource: catalog / entities / structure / time_range / doc meta
│   ├── prompts_def.py          # kb_search_strategy（先看地图再搜 + 时效性指导）+ qa_template + document_analysis
│   ├── rate_limiter.py         # ★ TokenBucket 限流器 — MCP Tool/Resource 调用速率控制（30容量, 1/s填充, 信号量5并发）
│   └── server.py               # MCP stdio Server — 1 Tool + 5 Resources + 3 Prompts
├── models/
│   ├── chat.py, document.py, retrieval.py, config.py, llm.py
│   └── ...
├── common/                 # 共享工具（logging, exceptions, utils, tokenize_chinese）
└── tests/
    ├── conftest.py              # pytest fixtures（共享 LLM/Embedding mock）
    ├── unit/
    │   ├── test_pipeline_steps.py     # ETL pipeline step 测试 (14)
    │   ├── test_merger.py             # TextMerger 列检测 + 合并测试 (20)
    │   ├── test_chunking.py           # Chunking 测试 (13)
    │   ├── test_fusion.py             # RRF 融合测试 (12)
    │   ├── test_citation.py           # 引用标注测试 (35)
    │   ├── test_reranker.py           # Reranker 降级链测试 (9)
    │   ├── test_query_rewriter.py     # Query 改写测试 (16)
    │   ├── test_query_planner.py      # ★ DAG 拆解测试 (44)
    │   ├── test_intent_router.py      # 意图路由测试 (12)
    │   ├── test_retrieval_models.py   # 检索模型测试 (13)
    │   ├── test_mcp_query_preparator.py # MCP 查询准备测试 (20)
    │   ├── test_mcp_resources.py      # MCP Resource 测试 (6)
    │   ├── test_mcp_time_metadata.py  # MCP 时间元数据测试 (6)
    │   ├── test_rate_limiter.py       # 限流器测试 (9)
    │   └── test_tool_timeout.py       # 工具超时测试 (7)
    └── integration/

注：旧 etl/chunkers/、etl/common/、etl/parsers/、etl/steps/chunk_step.py、etl/steps/parse_step.py 已清理移除，统一使用 parsing/ + chunking/ 模块。

docs/
└── qa_testset_ali_handbook.json   # ★ 评估测试集 — 20 QA pairs（阿里员工手册，easy/medium/hard 三级）

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
│   ├── service/GroupService.java         # 用户组 CRUD + 成员管理（★ v12.1: 层级遍历提取到 GroupHierarchyService）
│   ├── service/GroupHierarchyService.java # ★ v12.1: 用户组层级 — BFS/DFS 遍历 + 嵌套路径创建（从 GroupService 提取）
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
│   ├── controller/DocumentController.java   # /api/documents CRUD + approvals + batch delete (soft/permanent) + space-wide listing
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
    ├── service/FeedbackService.java       # ★ v12: 检索反馈查询（JdbcTemplate 读 retrieval_feedback 表）
    ├── dto/FeedbackDtos.java              # ★ v12: FeedbackItem record — Trace 全量快照 DTO
    ├── model/ApiResponse.java
    ├── exception/BusinessException.java, GlobalExceptionHandler.java
    └── util/JwtUtil.java

backend/src/test/java/com/kes/auth/service/
├── AuthServiceTest.java             # AuthService 单元测试（6 tests）
├── PermissionServiceTest.java       # PermissionService 单元测试（14 tests）
├── PermissionServiceIT.java         # PermissionService 集成测试
├── PermissionQueryServiceTest.java  # ★ 权限查询测试（10 tests）
├── AdminServiceTest.java            # ★ v7: AdminService 用户管理测试（13 tests）
├── GroupServiceTest.java            # ★ GroupService 单元测试（4 tests）
├── RoleServiceTest.java             # ★ RoleService 单元测试（14 tests）
└── AceServiceTest.java              # ★ AceService 单元测试（10 tests）

frontend/src/
├── main.js               # Vue app setup (Pinia + Router + ElementPlus)
├── App.vue               # Root component
├── api/                   # ★ v12.1: 按领域拆分为独立文件
│   ├── client.js          #   Axios 实例 + 拦截器 + Token 刷新队列（共享基础）
│   ├── index.js           #   统一导出入口（向后兼容）
│   ├── auth.js            #   authApi + userApi
│   ├── documents.js       #   documentsApi — upload/list/delete/batchDelete/batchPermanentDelete + viewUrl
│   ├── chat.js            #   chatSSE + submitFeedback
│   ├── conversations.js   #   conversationsApi
│   ├── spaces.js          #   spaceApi
│   ├── groups.js          #   groupsApi
│   ├── roles.js           #   rolesApi
│   └── admin.js           #   adminApi + modelAdminApi
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
│   ├── AdminDashboard.vue # 全局管理面板（含 v7 用户管理 + v12 检索反馈 Tab）
│   ├── ModelManagement.vue # ★ v6: 模型配置管理（Provider/Model/Assignment CRUD + 发现 + 测试）
│   ├── FeedbackDashboard.vue # ★ v12: 检索反馈面板 — Web Chat/MCP 双栏 Trace 详情
│   ├── Chat.vue           # ★ 组件编排（130行，原296行）
│   ├── Documents.vue      # ★ 组件编排（170行）— 多选 checkbox + 批量删除 + KB 标签列 + space 全量文档列表
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
├── migration-v10-knowledge-chunks-metadata.sql # ★ v10: knowledge_chunks 添加 metadata JSONB 列
├── seed-permission-test.sql       # v4: 权限验证测试数据 (3 用户, 1 Space, 2 KB)
├── generate_test_docs.py          # LLM-powered test document generator
├── upload_test_docs.py            # Upload test docs via API
├── render_iwms_docs.py            # Generate IWMS project test documents (md → docx/xlsx/pdf/html)
├── verify_permissions_v3.py       # v3: 自动化权限验证脚本 (HTTP API)
├── verify_permissions_v4.py       # v4: ACE 权限模型验证脚本
├── langfuse_fetch_trace.py        # ★ Langfuse Trace 全量拉取 — 按 trace_id 输出节点树
├── judge_eval.py                  # ★ 端到端评估 — Judge 4 维评分 + 版本对比 + Langfuse 推送
├── batch_eval.py                  # ★ 批量评估 — 6 批 × 10 条 + Trace + Judge + HTML 报告
├── NotoSansSC.ttf                 # Chinese font for PDF generation
└── test_docs/                     # Test document corpus (iwms: 20 documents, source/ + output/)

```


