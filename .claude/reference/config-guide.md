# 配置指南 & 运维参考

> 从 CLAUDE.md 提取

## Configuration

- **Python LLM config:** `ai-service/config/llm.yaml` — 旧版静态配置。v12 升级后作为紧急降级方案，当 ModelPool 完全不可用时使用。
- **★ v12 模型配置中心（文件驱动）:** 全局管理员通过前端界面配置 Provider/Model/环节映射，所有配置集中于 `ai-service/config/models.yaml` 一个文件。Python 启动时直接读本地文件，30 秒 mtime 热重载。HTTP 从 Java 拉取保留为降级路径（向后兼容）。前端通过 `GET/PUT /api/admin/models/config` API 读写配置。
- **模型供应商类型:** `openai_compatible`（API 调用）、`ollama`（本地 API）、`local`（HuggingFace 本地加载，用于 Cross-Encoder / SPLADE）
- **模型类型:** `chat`（LLM/SLM）、`embedding`（向量化）、`reranker`（Cross-Encoder 精排）、`splade`（神经稀疏检索）
- **☆ SLM 独立配置:** 新增 `slm` 环节（轻量小模型），独立于主 `chat` LLM，用于查询预处理、DAG 三维提取、Critic 决策。管理员可为其分配更便宜/快的模型（如 qwen-turbo）。
- **Java config:** `backend/src/main/resources/application.yml` — `jwt.secret`, `jwt.refresh-expiration` (7d), `jwt.context-expiration` (30m), `aiservice.base-url`, `minio.*`, `spring.data.redis.*`, `spring.rabbitmq.*`.
- **Infrastructure:** `docker-compose.yaml` — all ports, credentials, volumes. Network: `kes-net`.
- **DB Schema:** `scripts/init-pgvector.sql` — executed on first PostgreSQL start. Creates all tables with v4 ACE model.
- **Seed Data:** `scripts/init-admin.sql` — creates admin users, default Space, default KB.

### LLM Provider

v12 模型配置中心支持动态切换，所有模型通过前端 AdminDashboard → 模型管理 Tab 配置，零硬编码。

默认供应商:
- **LLM**: 任何 OpenAI 兼容 API（DashScope / vLLM / DeepSeek / Ollama）
- **Embedding**: text-embedding-v3 (1024维)
- **Reranker**: BGE-Reranker (Cross-Encoder) 或 LLM 降级

配置优先级: `models.yaml` 文件 → Java HTTP 降级 → `llm.yaml` 紧急降级 → 环境变量 `${DASHSCOPE_API_KEY}`

### ★ API Key 解析优先级 (2026-06-28 确立)

三层密钥解析，优先级从高到低：

```
1. ai-service/.secret/providers/{name}.json  → 最高优先（本地文件，不提交 git）
2. 系统环境变量 (export / systemd / /etc/environment) → 运维层面设置
3. .env 文件 (仅开发环境，start.sh 不覆盖已有环境变量)
```

Python `ModelPool._resolve_key()` 按此顺序查找。Java `AdminModelService.resolveApiKey()` 从 `System.getenv()` 读取后传给 Python `/active` 端点。
`.env` 中的 `DASHSCOPE_API_KEY` 已注释，防止覆盖系统级环境变量。

**`start.sh` 加载行为**：dev 模式逐行读取 `.env`，仅当变量未设置时才导入（`if [[ -z "${!_key}" ]]`），系统级环境变量优先。

Switch providers: change `type` in `config/llm.yaml` + register new implementation via `ModelFactory.register_llm()`.

### ★ v12.1 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KES_JAVA_URL` | (空) | Java 后端地址，ModelPool HTTP 降级时使用。不配则跳过 HTTP 降级 |
| `KES_MODEL_WATCH_INTERVAL` | `30` | models.yaml 热重载间隔（秒） |
| `KES_JWT_SECRET` | (必填) | JWT 签名密钥，至少 32 字符 |

### ★ v12.1 配置收敛

- **`models.yaml` timeout** — `model_factory.py` 从 `ModelConfig.timeout` 读取并传递给 `APIReranker`（不再硬编码 30s）
- **`SummaryConfig`** — `models/config.py` 中的 `SummaryConfig`（soft_limit/compress_target/trigger_rounds/max_failures）已接入 `SummaryEngine`，由 `app.py` 生命周期传入
- **降级路径隔离** — `model_pool.py` 仅做编排，工厂逻辑在 `model_factory.py`，热重载在 `config_watcher.py`
- **`reranker.py` 的 `_DEFAULT_CE_MODEL`** — 仅为终极 fallback（ModelPool 完全不可用时），正常路径从 `models.yaml` 读取


## Database Tables (v6~v9 新增)

| Table | Version | Description |
|-------|---------|-------------|
| `model_providers` | v6 | 模型供应商配置（DashScope/Ollama/BGE...） |
| `model_configs` | v6 | 模型实例（qwen-plus/text-embedding-v3...） |
| `model_assignments` | v6 | 环节→模型映射（chat/rewrite/embedding...） |
| `system_config` | v6 | 系统级键值配置，`model_config_version` 驱动热重载 |
| `api_keys` | v8 | MCP API 密钥 — 用户自助管理，scope_kb_ids 预留 |
| `user_identities` | v9 | 外部身份绑定 — 一个 Cbase 用户绑定多个 IdP 账号 |
| `knowledge_chunks.metadata` | v10 | JSONB — ETL MetadataEnrichStep 产出的结构化元数据（chunk_type/level/heading/page_range），MCP Resource 的权威数据源 |
| `retrieval_feedback` | v12 | ★ 检索质量全链路追踪 — Python 写入 Trace/Judge 评分，Java 读反馈，7 模块结构（query→retrieval→chunks→generation→judge→feedback→extra） |

### v7~v10 Schema 扩展

| 表 | 新增列 | 版本 | 说明 |
|----|--------|------|------|
| `users` | `email`, `status`, `source`, `must_change_password` | v7 | 用户管理增强 |
| `users` | `metadata JSONB` | v9 | 企业自定义字段（工号/部门/职级等） |
| `user_groups` | `external_id`, `source`, `metadata JSONB` | v9 | 外部组标识 + 来源 + 扩展 |
| `spaces` | `metadata JSONB` | v9 | 空间级扩展（成本中心/组织单元等） |
| `knowledge_bases` | `metadata JSONB` | v9 | KB 级扩展（分类标签等） |
| `knowledge_chunks` | `metadata JSONB` | v10 | ETL MetadataEnrichStep 写入（chunk_type/level/heading/page_range/doc_id），MCP Resource 数据源 |

---

---

## ★ Frontend UI 重构 (2026-06-28)

### 设计风格
企业级克制风格：主色 `#1677ff`，背景 `#f5f7fa`，卡片白底 `rounded-lg`，阴影仅 hover 时出现。

### 已重构页面
| 页面 | 文件 | 变更 |
|------|------|------|
| **空间选择** | `views/SpaceSwitcher.vue` | 垂直列表 → Grid 3 列卡片网格；统一淡蓝图标 (`#e6f4ff` + `#1677ff`)；创建入口为虚线占位卡片；角色 Badge 用区分配色 |
| **对话侧栏** | `components/chat/SidebarFooter.vue` | 纯文本链接 → "Space 控制台" 容器 (Grid 2 列 + MCP 跨行)；图标+标题+状态；hover 白底+阴影 |

### 角色 Badge 配色
| 角色 | 背景 | 文字 |
|------|------|------|
| Owner | `#fff7ed` | `#c2410c` |
| Admin | `#eff6ff` | `#1d4ed8` |
| Member | `#f3f4f6` | `#6b7280` |

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

### kes_mcp/ 模块状态 (v10 重构 — 2026-06-29)

**设计原则变更**：Tool 层精简为 1 个（砍掉对 LLM Agent 冗余的 ask_expert 和 read_document），Resource 层扩张为 5 个（实体索引/文档结构/时间跨度/文档元数据），所有 Resource 零 LLM，数据来自 `knowledge_chunks.metadata` JSONB（ETL 时预计算）。

| 组件 | 状态 | 说明 |
|------|------|------|
| `auth.py` | ✅ | API Key → Token 交换 + scope 缓存 + 自动续期 + 快速失败 |
| `tools.py search_chunks` | ✅ | 唯一 Tool，McpQueryPreparator + execute()，支持 time_range/context_hint/focus_aspects/doc_type，返回时间元数据 |
| `tools.py read_document` | ❌ 移除 | 降级为 `doc://{doc_id}/meta` Resource |
| `tools.py ask_expert` | ❌ 移除 | LLM Agent 自己就是 LLM，不需要另一个 LLM 生成答案 |
| `resources_def.py` | ✅ ★ 新增 | 5 个 Resource：catalog / entities / structure / time_range / doc meta |
| `prompts_def.py` | ✅ 更新 | kb_search_strategy 改为"先看地图再搜"工作流 + 时效性指导 |
| `tools_def.py` | ✅ 更新 | inputSchema 新增 time_range 参数 + query 构造指导 |
| `server.py` | ✅ | stdio MCP Server，1 Tool + 5 Resources + 3 Prompts |
| `retrieval/mcp_query_preparator.py` | ✅ | jieba 提取 + focus_aspects 映射 + 正则实体捕获 |
| `etl/steps/metadata_enrich_step.py` | ✅ ★ 新增 | ETL 步骤：提取 chunk_type/level/heading/page_range → metadata JSONB |

### 其他关键修复

- `SystemBootstrap.java` — 首次启动 users 为空时自动创建 admin 账号
- `AdminService.batchImportUsers` — CSV 支持 `group_name` 列，导入时自动归属组
- `GroupService.addMembers` — 批量添加组成员端点
- `admin_action_logs` — space_id/target_id 改为可空（全局操作用）
- `user_groups.name` — 加 UNIQUE 约束（防 AD 同步重复）

### 测试覆盖

| 层 | 测试数 | 覆盖模块 | 覆盖率 |
|----|--------|---------|--------|
| Java Backend | 71+ tests | Auth(6) + Permission(14) + PermissionQuery(10) + AdminService(13) + GroupService(4) + RoleService(14) + AceService(10) + PermissionIT | ~25% |
| Python AI Service | 226 tests | Fusion(12) + Citation(35) + QueryRewriter(13) + IntentRouter(12) + Reranker(9) + McpQueryPreparator(20) + RetrievalModels(13) + Chunking(13) + Merger(20) + PipelineSteps(14) + **QueryPlanner(44)** + **MCP Resources(6) + MCP TimeMeta(6) + RateLimiter(9) + ToolTimeout(7)** | ~41% |
| Frontend | 22 tests | Utils(8) + ChatMessage(6) + Composables(8) | ~15% |

**覆盖率工具**: JaCoCo (Java) / pytest-cov (Python) / vitest v8 (前端)
**CI 阈值**: Python `--cov-fail-under=30`
