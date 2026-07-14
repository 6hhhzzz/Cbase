# CLAUDE.md

## 架构铁律（强制）

1. **严格分层 DDD**：Controller → Service → Repository。Controller 只接收参数和返回结果，严禁业务逻辑。
2. **单向依赖**：内层（Domain/Infrastructure）禁止反向依赖外层（Application/Interfaces）。
3. **防上帝类**：单个类/函数 ≤ 300 行，提示词文件 ≤ 500 行。
4. **跨模块调用**：通过 Application Service 或事件（Event）编排，禁止直接注入其他模块的 Repository。
5. **依赖注入**：构造函数注入，禁止类内部 `new` 依赖。

## 项目定位

**KES = 企业知识中间件**，外部 AI Agent 是一等公民。

两条检索路径共享 `RetrievalOrchestrator.execute()` 执行层，但查询准备层独立：

| 路径 | 消费者 | 查询准备 | LLM 调用 |
|------|--------|---------|---------|
| Web Chat (`/v1/chat`) | 人类用户 | QueryRewriter (指代消解) + IntentRouter (意图分类) | 多次 |
| MCP (`kes_mcp/`) | 外部 AI Agent | McpQueryPreparator (jieba 实体提取, ~5ms) | **零次** |

### 检索全链路（Web Chat）

```
[0] SemanticCache (Redis 高频拦截) → 命中直接返回
[1] QueryRewriter (指代消解 + 关键词) → IntentRouter (规则→LLM 分类)
[2] ★ HyDE 术语桥接: 列举/抽象查询 → LLM 生成假答案 → 用假答案检索
[3] HybridSearch: Dense + BM25 并行 → RRF 融合 (k=60)
[4] ★ Parent 解析: child chunk → metadata.parent_content → 完整语义单元
[5] Reranker: API → Cross-Encoder (BGE-Reranker-v2-m3) → LLM → 截断
[6] ContextAssembly + Grounding 校验
[7] LLM 生成 + Citation 引用标注
[8] JudgeEvaluator: 异步 4 维评分 (faithfulness/answer_relevance/context_relevance/answer_correctness)
```

### 检索执行层（共享）

| 组件 | 文件 | 职责 |
|------|------|------|
| HybridSearch | `retrieval/hybrid_search.py` | Dense + BM25 并行 → RRF 融合 (k=60) |
| DenseRetriever | `retrieval/dense.py` | pgvector HNSW 向量检索 |
| SparseRetriever | `retrieval/sparse.py` | PostgreSQL tsvector BM25 (jieba 分词) |
| Reranker | `retrieval/reranker.py` | API → Cross-Encoder (BGE-Reranker-v2-m3) → LLM → 截断 |
| JudgeEvaluator | `retrieval/judge.py` | LLM-as-a-Judge 4 维评分 (5 档 rubric + few-shot + CoT) |
| TraceContext | `retrieval/trace_context.py` | 统一追踪 (SpanHandle/SpanSnapshot) → Langfuse span 树 + DB trace |
| RetrievalTracer | `retrieval/feedback/` | 检索质量追踪 → `retrieval_feedback` 表 (5% 采样落库, MCP 用内存缓存) |
| McpQueryPreparator | `retrieval/mcp_query_preparator.py` | jieba 实体提取 + focus_aspects 关键词映射, ~5ms 零 LLM |

## AI 原生 Space 架构

KES 通过 `space_type` 实现双轨隔离，在不影响现有功能的前提下支持 AI 原生的文档治理：

| Space 类型 | 文档入口 | ETL 管道 | 治理层 | KB 管理 |
|-----------|---------|---------|-------|--------|
| `default` | Web UI 上传 | 标准 7 步管道 | 无 | 手动创建 KB |
| `ai_native` | MCP `submit_document` | 标准 + 治理 3 步 | DocUnderstand → DocClassify → UpdateKBSummary | 自动归类/创建 |

- **Space 隔离**：`space_type` 存储在 `spaces.metadata` JSONB 中 (`{"space_type": "default"|"ai_native"}`)，Java `Space.getSpaceType()` 读取
- **KB 元数据**：`knowledge_bases.metadata` JSONB 存储 `kb_summary`（聚合主题串）和 `kb_topics`（完整主题列表），供 MCP catalog Resource 返回
- **内部调用**：Python `UpdateKBSummaryStep` 通过 `PUT /api/spaces/{spaceId}/kbs/{kbId}/metadata` + `X-Internal-Call: true` 绕过 JWT 写 KB 元数据

## 技术栈

| 层 | 技术 | 端口 |
|---|------|------|
| Frontend | Vue 3 + Vite + Element Plus + Pinia | 5173 |
| Java Backend | Spring Boot 3.3 + JPA + Security + JWT | 8080 |
| Python AI | FastAPI + asyncpg + pgvector + OpenAI SDK | 8000 |
| PostgreSQL | pgvector + HNSW 向量检索 + tsvector BM25 | 5432 |
| Redis | Session / kb_ids 权限缓存 / 对话历史 / Semantic Cache | 6379 |
| RabbitMQ | 文档异步摄取 | 5672 |
| MinIO | 文件对象存储 | 9000 |
| Langfuse | 检索全链路追踪 + Judge 评分 | self-hosted |

### ModelPool v12 — 动态模型池

支持按角色分配独立 LLM 实例，通过 `models.yaml` 配置中心管理：

| 角色 | 变量名 | 用途 |
|------|--------|------|
| chat | `llm` | 主对话生成 |
| slm | `slm` | 轻量任务 (DocUnderstand, DocClassify, Judge) |
| rewrite | `llm_rewrite` | QueryRewriter 指代消解 |
| planner | `llm_planner` | QueryPlanner DAG 分解 |
| embedding | `embedding` | 向量嵌入 |
| reranker | `reranker` | 重排序 (可选) |

初始化优先级: `models.yaml` (Java HTTP) → 降级 `llm.yaml` (所有角色复用单 LLM)。30s 自动监听配置变更。

## 安全红线

- **`filter_params` 必传**：Python 校验非空，缺失返回 400。Java 计算 `kb_ids`，Python 机械使用，不做权限决策。
- **Python 永远不写业务数据库**（users/spaces/knowledge_bases 等），不校验 JWT，不管理用户。KB 元数据 (kb_summary) 通过 Java API 写入，不直接操作 `knowledge_bases` 表。
- **Java 永远不调 pgvector / LLM / Embedding API**，不解析文档。
- **权限计算在 Java**：`PermissionQueryService.resolveAccessibleKbIds()` → Redis 缓存(5min TTL) → Python 使用。
- **DocumentService.upload()** 管理员判断必须用 `permissionService.isSpaceAdmin(spaceId, userId)`（查 DB），不能用 JWT role 字符串比对。
- **MCP submit_document** 必须校验 `space_type == "ai_native"`，传统 Space 拒绝提交。

## 关键参数速查

### 检索参数

| 参数 | 默认值 | 位置 |
|------|--------|------|
| top_k (Web Chat) | 5 | `orchestrator.py:retrieve()` |
| top_k (MCP) | 10 | `mcp_query_preparator.py:127` |
| RRF k | 60 | `fusion.py:21` |
| Reranker top_n | 5 | `reranker.py:176` |
| Citation threshold | 0.6 | `citation.py:21` |
| Critic confidence threshold | 0.5 | `critic.py:19` |
| Semantic Cache similarity | 0.95 | `semantic_cache.py:24` |
| HyDE 触发条件 | 列举/枚举/抽象术语 | `orchestrator.py:_should_use_hyde()` |

### 分块参数

| 参数 | 默认值 | 位置 |
|------|--------|------|
| ParentChildChunker parent_max_tokens | 500 | `parent_child_chunker.py:46` |
| ParentChildChunker child_target_tokens | 150 | `parent_child_chunker.py:47` |
| ParentChildChunker child_min_tokens | 40 | `parent_child_chunker.py:48` |
| merge_chunks target_tokens | 300 | `merge.py` |
| EmbedStep batch_size | 10 | `embed_step.py:13` |

### Judge 参数

| 参数 | 默认值 | 位置 |
|------|--------|------|
| MAX_CHUNKS_FOR_JUDGE | 5 | `judge.py:132` |
| MAX_CHUNK_CHARS | 300 | `judge.py:133` |
| MAX_ANSWER_CHARS | 800 | `judge.py:134` |
| 采样率 | 5% | `feedback/__init__.py:16` |

### MCP 参数

| 参数 | 默认值 | 位置 |
|------|--------|------|
| MCP top_k (search_chunks) | 10 (范围 1-30) | `tools_def.py` |
| 并发工具数限制 | 5 (Semaphore) | `tools_def.py` |
| 工具超时 | 30s | `tools_def.py` |
| 限流 | 30 token 桶, 1 token/s 填充 | `rate_limiter.py` |
| MCP Auth token TTL | 30min, 提前 5min 刷新 | `auth.py` |

## 关键参考文件

| 文档 | 内容 |
|------|------|
| [.claude/reference/architecture.md](.claude/reference/architecture.md) | ACE 权限模型、JWT 双 Token、SSE 格式、审批流、Redis 缓存 |
| [.claude/reference/code-map.md](.claude/reference/code-map.md) | 完整文件树（ai-service / backend / frontend / scripts） |
| [.claude/reference/api-endpoints.md](.claude/reference/api-endpoints.md) | 全部 REST API 端点列表 |
| [.claude/reference/config-guide.md](.claude/reference/config-guide.md) | 配置说明、环境变量、模型配置中心、DB Schema、测试覆盖 |

## 常用命令

```bash
./setup.sh && ./start.sh          # 安装依赖 + 启动全部服务
docker compose up -d              # 仅启动基础设施
cd ai-service && uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
cd backend && mvn spring-boot:run
cd frontend && npm run dev
```

## 测试

```bash
cd ai-service && uv run pytest tests/ -q     # Python: 225 tests
cd backend && mvn test                        # Java: 71 tests
cd frontend && npm run build && npm run test  # Frontend: 22 tests
```

## GitHub 上传流程

用户说"上传"时，按以下流程执行：

### 1. 前置检查

```bash
# 确认分支（必须在 main）
git branch --show-current

# 确认远程可达
git remote -v

# 检查敏感文件（.env、.pem、.key、credentials 等）
git status --porcelain | grep -E '\.(env|pem|key|secret|token)'

# 检查超大文件（>10MB）
find . -not -path './.git/*' -not -path '*/node_modules/*' \
  -not -path '*/.venv/*' -not -path '*/target/*' \
  -not -path '*/dist/*' -type f -size +10M | grep -v -f <(sed 's|^|./|' .gitignore 2>/dev/null) || true
```

报告结果给用户确认。

### 2. 检查变更范围

```bash
git status -s
git diff --stat
```

### 3. 提交并推送

```bash
git add -A
git commit -m "<描述>" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git push origin main
```

- `git add -A`：一次性提交所有变更（新增 + 修改 + 删除）
- commit message 格式：emoji 前缀 + 简短描述（如 `✨ 新增 AI 原生 Space 文档治理管道`）
- 失败处理：push 被拒（non-fast-forward）→ `git pull --rebase origin main` 再 push

### 4. 验证

确认 GitHub Actions CI 通过。

### 补充 .gitignore

发现未覆盖的应忽略文件（如 `.coverage`、临时脚本、AI 生成输出等）时，先补 `.gitignore` 再 add。

## 评估与回归测试

### 批量评估（60 条 × 6 批）

```bash
cd ai-service && uv run python ../scripts/batch_eval.py          # 全量
cd ai-service && uv run python ../scripts/batch_eval.py --batch 1  # 仅第 1 批
```

输出：`docs/batch_results/batch_1~6.json` + `docs/eval_report.html`

### 测试集审计（对比 expected_answer 与文档实际内容）

```bash
# 生成 docs/audit_results.json + docs/audit_report.html
cd ai-service && uv run python /tmp/audit_testset.py
```

### 版本对比

```bash
cd scripts && ./judge_eval.py eval --version v1-baseline --kb-id <UUID>
./judge_eval.py eval --version v2-optimized --kb-id <UUID>
./judge_eval.py compare --report-a <v1.json> --report-b <v2.json>
```

测试集: `docs/qa_testset_ali_handbook.json` (60 QA pairs: 45 正向 + 15 负向/拒答)

**注意**：分块策略变更后需删旧文档重入库，再跑评估。

### Trace 调试

```bash
cd scripts && ./langfuse_fetch_trace.py <trace_id>
./langfuse_fetch_trace.py --last 3          # 最近 3 条
./langfuse_fetch_trace.py <trace_id> --json  # JSON 格式
```

## 文档摄取流水线（9 步）

```
DownloadStep → ParseStepV5 → SanitizeStep → ChunkStepV5
  → DocUnderstandStep → DocClassifyStep → EmbedStep
  → IndexStep → UpdateKBSummaryStep
```

- **ParseStepV5**: ParseOrchestrator 按 MIME 路由 → PdfParser / DocxParser / XlsxParser / PptxParser / HtmlParser / MarkdownParser / TextParser
- **DocxParser**: 提取顶层段落 + 表格单元格内段落 + 表格 HTML 结构
- **ChunkStepV5**: ChunkOrchestrator auto 策略 → ParentChildChunker（默认，两级分块）
- **ParentChildChunker**: 按 `\n\n` 分组 Parent (~500t) → 标点切 Child (~150t) → Child 带 parent 前缀 → 检索用 Child，回答用 Parent
- **DocUnderstandStep**: SLM 通读文档前 5000 字符 → 产出 `summary`(100-200 字)、`doc_type`(policy/manual/report/guide/specification)、`topics`(3-8 主题词)、`key_entities`、`not_covered` → 注入 chunk metadata
- **DocClassifyStep**: SLM 对比已有 KB summaries → Jaccard 规则匹配 (≥0.3 自动归入, 0 自动新建) → 中间值 LLM 决定 → 产出 `target_kb_id` + `kb_action`(existing/create)
- **UpdateKBSummaryStep**: 聚合 KB 下所有 `doc_topics` → 去重取前 6 → 调用 Java `PUT /kbs/{kbId}/metadata` 写入 `kb_summary` + `kb_topics`

## MCP 知识服务

为外部 AI Agent 提供三类接口：3 个 Tool + 2 个 Resource + 3 个 Prompt。

### Tools（写/检索操作）

| Tool | 描述 | 关键参数 |
|------|------|---------|
| `search_chunks` | 混合检索（Dense + BM25）→ RRF → Reranker，返回原始 chunks 无 LLM 答案 | `query`(必填), `kb_ids`, `top_k`(1-30), `focus_aspects`, `doc_type`, `time_range` |
| `report_quality` | Agent 反馈检索质量（like/dislike + 原因），trace_id 10min TTL | `trace_id`(必填), `rating`(必填), `reason` |
| `submit_document` | AI 原生 Space 文档提交，触发完整治理管道 | `doc_title`(必填), `content`(必填), `summary`(必填), `keywords`(必填), `doc_type`(必填), `kb_id`(可选) |

### Resources（只读感知）

| Resource URI | 内容 |
|-------------|------|
| `doc://catalog` | 所有可访问 KB 列表，含 `kb_summary`(聚合 top-6 主题)、`doc_count`、`space_type` |
| `doc://kb/{kb_id}/docs` | KB 内文档列表，含 `summary`、`doc_type`、`topics`、`not_covered`、`status`、`version` |

Agent 典型使用流程：`catalog` → 了解有哪些 KB → `kb/{id}/docs` → 了解文档内容 → `search_chunks` 精准检索。

### Prompts（检索策略模板）

| Prompt | 用途 |
|--------|------|
| `kb_search_strategy` | 教 Agent 如何构造查询、选择 top_k、判断时效性 |
| `qa_template` | 标准 RAG 模板 — 基于 chunks 回答 + 引用标注 |
| `document_analysis` | 结构化文档分析 — 提取要点、风险、行动项 |

### MCP Auth 与限流

- **认证**：API Key → `POST /api/auth/mcp/exchange` → context_token (30min TTL, 提前 5min 刷新)。支持 `KES_API_KEY` 环境变量或 `~/.kes/mcp.json`
- **限流**：TokenBucket (30 token 容量, 1 token/s 填充, 稳态 60 req/min)
- **并发**：`asyncio.Semaphore(5)` 保护 pgvector 连接池
- **文件**：`kes_mcp/auth.py`, `kes_mcp/rate_limiter.py`, `kes_mcp/server.py`

## 关键设计决策

1. **两级分块 (Parent-Child)**：Child (~150t) 嵌入检索保证精度，Parent (~500t) 完整语义单元保证 LLM 上下文完整。列表/枚举类内容不再被拆散。Parent 内容存在 child 的 `metadata.parent_content` 中，检索侧通过 `_resolve_parents()` 在检索后自动展开。
2. **HyDE 简单路径术语桥接**：列举/枚举/抽象术语类查询自动触发 HyDE — LLM 生成假答案 → 用假答案检索 → 桥接用户术语与文档用语的 embedding 差异。触发条件：`_should_use_hyde()` 检测 `包含哪些/有哪些/列出/哪几个` 等模式。
3. **Judge 替代 RAGAS**：RAGAS 依赖 OpenAI SDK 格式，与 DashScope Embedding API 不兼容（已移除依赖，释放 35 个包）。Judge 单次 LLM 调用产出 4 维分数。
4. **TraceContext 双输出**：SpanSnapshot 树 → 同时生成 Langfuse span 树和 DB trace dict，不重复记录。
5. **HyDE 反幻觉约束**：禁止编造版本号、表单编号、条款号、系统名称，仅使用用户问题中已出现的概念。
6. **MCP 零 LLM 查询准备**：jieba 实体提取 + focus_aspects 关键词映射，~5ms 延迟，给外部 Agent 最快响应，复用共享检索执行层。
7. **评估体系三层**：batch_eval（全量 60 条）→ audit（文档覆盖度）→ judge_eval（版本对比），Langfuse trace 全量可追溯。
8. **AI 原生 Space 双轨隔离**：通过 `space_type` JSONB 字段隔离开传统 Space 和新治理行为。AI 原生 Space 自动进行文档理解、分类、KB 摘要维护，传统 Space 完全不受影响。
9. **文档治理管道**：DocUnderstand（LLM 理解内容 → topics/summary/type）→ DocClassify（Jaccard + LLM → 归入已有 KB 或创建新 KB）→ UpdateKBSummary（聚合 topics → 写 KB 元数据）。外部 Agent 只需按规范提交文档，内部 KES 自动处理分类和 KB 管理。
10. **MCP Resource 极简设计**：2 个 Resource（catalog + docs），Agent 不需要术语表、时间范围、单文档元数据细节 — 只需知道有哪些 KB 和每个 KB 有什么文档，然后用 `search_chunks` 精准检索。
