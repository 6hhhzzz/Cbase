# 企业知识助手 (Enterprise Knowledge Assistant)

> 可嵌入企业现有权限体系的、高度可定制的文档 AI 工作流基座。
>
> 不是又一个知识库问答工具，而是一套让企业把「散落的文档 + 既有的权限 + 自己的流程」变成 AI 可用上下文的基础设施。

## 定位

让组织把文档知识融入 AI 工作流，同时不破坏文档原有的权限边界。企业可以自定义角色、字段、检索策略，把系统适配成自己公司的形状。

核心差异化：
- **企业级权限**：ACE 模型 — 用户组 (Group) 管"人"，Space 管"资产"，ACE 矩阵配置 Group ↔ KB ↔ Role
- **文档级权限隔离**：99% 文档继承 KB 权限，1% 敏感文档可阻断继承单独授权
- **可定制**：自定义角色 (permissions JSONB)、自定义字段、可插拔检索策略
- **MCP 就绪**：文档检索能力可以嵌入外部 AI Agent 的工作流

## 架构决策

详见 `adr/` 目录。当前关键决策：

| 决策 | 文档 |
|------|------|
| Space/KB 权限模型 | [ADR-001](adr/001-space-kb-permission-model.md) |
| ACE 企业级权限模型 (Group↔KB↔Role) | [ADR-002](adr/002-ace-permission-model.md) |
| 产品边界 = L1 问答 + MCP 服务 | 同上 |

## 核心功能

| 模块 | 说明 |
|------|------|
| 文档解析 | 6 种格式（PDF/DOCX/XLSX/MD/HTML/TXT），PII 脱敏，智能分块 |
| RAG 问答 | 跨 KB 联合检索，SSE 流式，来源引用 |
| 权限隔离 | ACE 矩阵 (Group↔KB↔Role) + 文档级阻断继承 + Deny 覆盖 Allow |
| 用户组管理 | 全局可嵌套用户组 + Group 管理员 (管人) / Space 管理员 (管资产) 解耦 |
| 文档生命周期 | 上传 → 审批 → 生效 → 失效/归档，完整版本回溯 |
| 多 Space | 扁平 Space 模型，支持部门/项目/客户等多种映射方式 |
| 跨 KB 检索 | 默认搜索全部有权限 KB，支持排除特定 KB + 文档级过滤 |
| 回收站 | 软删除 + 可恢复，AI 链路彻底隔离 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Vite + Element Plus + Pinia |
| 后端 | Spring Boot 3.3 + JPA + Security + JWT |
| AI 服务 | FastAPI + asyncpg + pgvector + OpenAI SDK |
| 数据库 | PostgreSQL 16 + pgvector |
| 缓存 | Redis 7 |
| 消息队列 | RabbitMQ 3 |
| 对象存储 | MinIO |
| LLM | DashScope (通义千问) |

## 文档结构

```
docs/
├── adr/          # 架构决策记录（不可变）
├── plans/        # 功能实施计划
├── reference/    # 参考资料
├── reports/      # 一次性报告
└── PROJECT.md    # 本文件
```

## 路线图

- ✅ **已完成**：v4 ACE 企业级权限模型（用户组、ACE 矩阵、文档级权限、Group/Space 管理解耦）
- ✅ **已完成**：自定义角色、全局管理员管理、Group 管理员、修改密码
- ✅ **已完成**：v5 混合检索引擎（HNSW + BM25 + RRF + Query Rewriting + Citation）
- ✅ **已完成**：v5 文档解析引擎（6 格式深度解析 + 语义分块）
- ✅ **已完成**：v6 动态模型配置中心（Provider/Model/Assignment 热重载）
- 🟡 **下一步**：批量导入用户、用户自助申请入组
- 🔜 **里程碑**：MCP 服务

---

## 当前状态总览（2026-06-23）

对照项目四个核心愿景维度的完成度：

| 愿景维度 | 完成度 | 状态 |
|----------|--------|------|
| **1. 细致灵活的权限管理体系** | 🟢 90% | v4 ACE 模型已落地，覆盖用户组嵌套、Space 管理解耦、ACE 矩阵、文档级权限 |
| **2. 企业标准审计与合规** | 🟢 85% | 审计日志完整、软删除/回收站完备、操作全追踪 |
| **3. 文档解析与 RAG 检索** | 🟡 75% | 解析/分块/检索引擎已重构，部分高级功能延后（语义分块、PDF 深度解析依赖） |
| **4. MCP 知识服务** | 🔴 10% | 架构设计已完成（ADR-003），接口候选已识别，代码零实现 |

---

## 一、权限管理体系

### 1.1 v4 ACE 企业级权限模型 ✅

**核心原则**：「成员归属于用户组，文档归属于 KB，管理员配置用户组与 KB 之间的关系（带上角色）」

```
user_groups (全局可嵌套)           roles (可自定义权限套餐)
       │                                  │
       ├── space_groups ──→ Space ←── space_admins (owner/admin)
       │                                  │
       └── ACE ──→ KB (visibility: space_wide | restricted)
                          │
                          └── Document (inherit_permissions)
```

**三层身份模型**：

| 身份 | 判定方式 | 权限范围 |
|------|---------|---------|
| 全局超级管理员 | `users.is_global_admin` 或所属组 `is_system_admin=true` | 所有 Space 的所有 KB |
| Space 管理员 | `space_admins` 表直接关联 User（owner/admin 两级） | Space 管理权 + 全部 KB 可见 |
| Space 普通成员 | 通过 `space_groups` 关联的全局用户组（含嵌套展开） | KB 访问权由 ACE 决定 |

**权限解析算法**（`PermissionQueryService.resolveAccessibleKbIds`）：
1. 全局管理员 → 全量返回
2. 展开用户有效组（含嵌套上溯 parent_group_id 链）
3. 计算 Space 身份
4. Space admin → 所有 KB 可见
5. space_wide KBs → 自动加入
6. 查询 ACE：allow → 加入，deny → 移除（deny 始终覆盖 allow）
7. Redis 缓存（5min TTL）

**已实现功能**：
- ✅ 全局可嵌套用户组（`user_groups.parent_group_id`）+ 层级展开
- ✅ Space 管理员双级（owner/admin）+ owner 转让
- ✅ ACE 矩阵：用户组/用户 → KB → 角色 → allow/deny
- ✅ 自定义角色：`roles.permissions JSONB`，预置 Admin/Editor/Viewer/Deny 四种系统角色
- ✅ KB 可见性：`space_wide`（全体 Space 成员自动可见）vs `restricted`（ACE 控制）
- ✅ 文档级权限：`inherit_permissions` 字段，Phase 3 可阻断继承
- ✅ Redis kb_ids 权限缓存（5min TTL，变更即时失效）
- ✅ 跨模块权限校验：`PermissionService.requireSpaceMember/requireSpaceAdmin/requireSpaceOwner`
- ✅ 注解驱动粗粒度入口守卫：`@RequireSpaceAdmin`、`@RequireGlobalAdmin`
- ✅ AuthService 已拆分为 7 个独立 Service（Auth/Space/Kb/Ace/PermissionQuery/Admin/Permission + Group/Role）

**待实现**：
- 🟡 批量导入用户
- 🟡 用户自助申请入组
- 🔜 文档级权限阻断继承（`inherit_permissions = false`）

### 1.2 关键设计决策

| 决策 | 说明 |
|------|------|
| 组成员管人，ACE 管权限 | 入组 = 获得潜在访问资格，实际权限由 ACE 裁定 |
| Deny 覆盖 Allow | 安全优先：一条 deny 即可撤销所有 allow 授权 |
| admin 管资产，owner 管 Space | admin 可管理 KB/准入组但不能删 Space，owner 独有转让/删除权 |
| 审计日志不可变 | `admin_action_logs` 只增不删，完整记录所有管理操作 |

---

## 二、审计与合规

### 2.1 审计日志 ✅

**`admin_action_logs` 表** — 统一审计日志，记录所有管理操作：

| 字段 | 说明 |
|------|------|
| `actor_id` | 操作者用户 ID |
| `space_id` | 操作所属 Space |
| `action` | 操作类型（CREATE_SPACE, ADD_ADMIN, CREATE_ACE, SOFT_DELETE_KB 等） |
| `target_type` | 目标类型（space, kb, document, user, group, role, ace） |
| `target_id` | 目标 ID |
| `detail` | JSON 详情（变更前后对比） |
| `created_at` | 操作时间 |

**实现方式**：Spring Event 解耦 — 业务代码发布 `AuditLogEvent`，`AuditEventListeners` 异步持久化。

### 2.2 软删除与回收站 ✅

| 实体 | 软删除 | 恢复 | 永久删除 | 级联 |
|------|--------|------|----------|------|
| Space | ✅ `deleted_at` | ✅ restore | ✅ permanent | 级联 KB + 文档 |
| KB | ✅ `deleted_at` | ✅ restore | ✅ permanent | 级联文档 + 清理 ACE |
| Document | ✅ `deleted_at` | ✅ restore | ✅ permanent | 清理 MinIO + pgvector chunks |

回收站 API：`GET /api/spaces/{spaceId}/trash` — 管理员可查看并恢复/永久删除。

### 2.3 AI 链路隔离 ✅

软删除后的文档在 AI 链路中完全不可见：
- Python `knowledge_chunks` 表同步更新 `status` 字段（active/soft_deleted）
- 检索时自动过滤 `status = 'active'`
- Java 通过 HTTP POST `/v1/documents/status` 同步状态变更

---

## 三、文档解析与 RAG 检索

### 3.1 文档解析引擎 ✅

**7 种文件格式**，基于 MIME 路由的分发式架构：

| 格式 | 解析器 | 状态 | 能力 |
|------|--------|------|------|
| PDF | `PdfParser` | ✅ | 智能路由（文本流/视觉流）+ KMeans 列检测 + 表格提取 |
| DOCX | `DocxParser` | ✅ | 保留标题层级 + 表格 |
| XLSX | `XlsxParser` | ✅ | Sheet → TableBlock |
| PPTX | `PptxParser` | ✅ | 新增支持 |
| HTML | `HtmlParser` | ✅ | 保留标题/表格 |
| Markdown | `MarkdownParser` | ✅ | 保留标题层级 |
| Plain Text | `TextParser` | ✅ | UTF-8/GBK 自动检测 |

**PDF 深度解析**（Phase 1b）：
- ✅ `PdfParser` — 逐页智能路由（文本流 pdfplumber / 视觉流 OCR+Layout）
- ✅ `LayoutAnalyzer` — ONNX YOLO 布局识别（10 类区域：标题/正文/表格/图片/公式等）
- ✅ `OcrEngine` — DBNet + CRNN ONNX 模型
- ✅ `TableStructureRecognizer` — ONNX 表格结构 → HTML
- ✅ `TextMerger` — KMeans + Silhouette 列检测 + 阅读顺序重排
- ⚠️ PDF 深度解析依赖（pdfplumber/onnxruntime/sklearn/huggingface_hub/opencv）声明在 `pyproject.toml` 可选依赖 `[pdf]` 中，需手动安装

### 3.2 语义分块引擎 ✅

| 分块器 | 状态 | 能力 |
|--------|------|------|
| `TokenChunker` | ✅ | token 感知 + 分隔符优先级 + 短 chunk 合并 |
| `TitleChunker` | ✅ | 标题层级 + 父子关系 |
| `ContextEnricher` | ✅ | 表格/图片上下文注入 |
| `merge_chunks` | ✅ | RAGFlow naive_merge 移植：跨 block 短 chunk 贪婪合并 |
| `SemanticChunker` | 🔜 | Phase 2 — 代码存根，类已注释 |

### 3.3 混合检索引擎 ✅

借鉴 RAGFlow Dealer 架构，全流程编排：

```
Query → QueryRewriter (缓存+短路+关键词) → IntentRouter (规则+LLM)
      → HybridSearch (Dense ∥ Sparse → RRF fusion)
      → Reranker (Cross-Encoder → LLM 降级)
      → CitationInserter (引用标注 + 位置单调约束)
      → LLM Response (SSE streaming)
```

| 组件 | 状态 | 能力 |
|------|------|------|
| `DenseRetriever` | ✅ | pgvector HNSW 向量检索 |
| `SparseRetriever` | ✅ | tsvector BM25 关键词检索 |
| `RRF Fusion` | ✅ | k=60 排名融合 |
| `Reranker` | ✅ | Cross-Encoder 主路径 + LLM 降级 |
| `QueryRewriter` | ✅ | Redis 缓存 + 短路 + 关键词提取 |
| `IntentRouter` | ✅ | 规则前置 + LLM 兜底 |
| `CitationInserter` | ✅ | 引用标注 + 位置单调约束 |

### 3.4 模型配置中心 ✅ (v6)

动态模型管理，支持热重载：

- `model_providers` — 供应商配置（DashScope/Ollama/vLLM...）
- `model_configs` — 模型实例（qwen-plus/text-embedding-v3...）
- `model_assignments` — 环节→模型映射（chat/rewrite/embedding/rerank...）
- Python `ModelPool` 启动时从 Java 拉取，30s 热重载
- 前端 `ModelManagement.vue` 提供完整 CRUD + 自动发现 + 连通性测试

---

## 四、MCP 知识服务

### 4.1 当前状态 🔴

**MCP 服务尚未实现。** 架构设计和产品边界已在 ADR 中明确：

> 「产品核心 = 文档检索基础设施。L1 问答是自带的人机交互界面。MCP 服务是给外部 AI Agent 的编程接口。L2-L5（摘要、嵌入流程、主动推送等）由外部 Agent 通过 MCP 消费，不在产品范围内。」
> — ADR-001

### 4.2 候选 MCP 端点

当前 Python AI Service 的以下端点可直接包装为 MCP Tools：

| 候选 MCP Tool | 现有端点 | 功能 |
|---------------|----------|------|
| `search_documents` | `POST /v1/chat` (非流式变体) | 基于权限的文档检索 + LLM 问答 |
| `list_accessible_kbs` | Java `GET /api/auth/accessible-kbs` | 列出当前用户有权限的 KB |
| `get_document` | Java `GET /api/documents/{id}` | 获取单个文档详情 |
| `health_check` | `GET /v1/health` | 组件健康检查 |

### 4.3 MCP 集成路径（规划）

```
外部 AI Agent
    │
    ├── MCP Protocol (JSON-RPC over stdio/SSE)
    │
    └── KES MCP Server (新增 Python 模块 mcp/server.py)
            │
            ├── 权限校验 ← Java JWT context_token
            ├── 检索代理 → Python RetrievalOrchestrator
            └── 文档代理 → Java HTTP API
```

**关键约束**：MCP 服务必须复用现有权限体系（JWT context_token → kb_ids 过滤），确保外部 Agent 只能访问其授权范围内的知识。

### 4.4 MCP 实现待办

1. 安装 MCP SDK（`mcp` Python 包或自实现 JSON-RPC）
2. 创建 `ai-service/mcp/server.py` — MCP Server 主体
3. 实现 Tool 定义：`search_documents`（参数：query, space_id, top_k）
4. 权限集成：从 context_token 解析 kb_ids，注入 filter_params
5. 传输层：stdio（本地 Agent）或 SSE（远程 Agent）
6. 在 `api/app.py` lifespan 中启动 MCP Server

---

## 五、技术债务与已知差距

### 5.1 测试覆盖

| 模块 | 测试文件 | 测试数 |
|------|----------|--------|
| Java AuthService | `AuthServiceTest.java` | 6 |
| Java PermissionService | `PermissionServiceTest.java` | 14 |
| Python ETL Steps | `test_pipeline_steps.py` | 10 |
| Python TextMerger | `test_merger.py` | 20 |
| **合计** | **4 个文件** | **50 个测试** |

**零测试覆盖的模块**：api/、retrieval/、llm/、chunking/orchestrator、parsing/orchestrator、mq/、core/context/、前端。

### 5.2 技术债务清单

| 项目 | 严重度 | 说明 |
|------|--------|------|
| `etl/` 模块待清理 | 中 | 旧 ETL 管道与新 parsing/chunking/retrieval 并存，`api/app.py` 仍引用 etl/ |
| `chunking/semantic_chunker.py` 死存根 | 低 | 类完全注释掉，Phase 2 实现或应删除 |
| `core/security/` 目录缺失 | 低 | CLAUDE.md 提到但未创建，无代码引用 |
| pyproject.toml 缺 build-system | 低 | 无 `[build-system]` 和 `[project.scripts]` |
| PDF 深度解析可选依赖 | 中 | 5 个包未预装，PDF 解析在依赖缺失时静默降级 |

### 5.3 已知功能差距

| 功能 | 状态 | 备注 |
|------|------|------|
| 批量导入用户 | 🟡 下一步 | ADR 已规划 |
| 用户自助申请入组 | 🟡 下一步 | ADR 已规划 |
| 语义分块 (SemanticChunker) | 🔜 Phase 2 | 代码存根 |
| MCP 服务 | 🔜 里程碑 | 零实现 |
| 前端测试 | ❌ 未开始 | — |
| E2E 集成测试 | ❌ 未开始 | — |

---

## 六、版本历史

| 版本 | 日期 | 关键变更 |
|------|------|----------|
| **v4 ACE** | 2026-06-18 | 企业级权限模型：用户组嵌套、ACE 矩阵、Space 管理解耦、自定义角色、文档级权限、审计日志、跨模块事件通信 |
| **v5 RAGFlow** | 2026-06-22 | 文档解析引擎重构（7 格式 + PDF 深度解析）、语义分块引擎、混合检索引擎（HNSW + BM25 + RRF + Query Rewriting + Citation）、前端组件化重构 |
| **v6 模型中心** | 2026-06-23 | 动态模型配置中心（Provider/Model/Assignment 三表 + 热重载）、前端模型管理界面、Python ModelPool |

### v5→v6 架构演进

```
v4 之前:  Java (auth+CRUD) ←→ Python (单体 ETL + 简单 RAG)

v5:       Java (auth+CRUD+事件) ←→ Python (parsing/ + chunking/ + retrieval/)
               ↑ 职责清晰分离，事件驱动解耦

v6:       + ModelPool 动态配置，模型可从管理界面热切换
```
