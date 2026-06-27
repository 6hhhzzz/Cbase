# 项目测试补全计划

## Context

项目功能完成度很高（v9 + MCP 生产化），但测试覆盖严重不足：

| 层 | 现有测试 | 覆盖类 | 覆盖率 |
|----|---------|--------|--------|
| Java | 3 文件 598 行 | 3/44 | ~7% |
| Python | 2 文件 607 行 | 8/94 | ~9% |
| 前端 | 0 | 0/42 | 0% |

**核心问题：** 所有测试都是纯单元测试（Mockito/unittest.mock），无集成测试、无 Controller/API 端点测试、无 Repository 测试、无 MCP 鉴权测试。

---

## 分阶段补全策略

按"影响面 × 风险等级"排序，每阶段独立可验证：

### 阶段 1: Java 高价值 Service（最频繁改动的核心业务）

| 优先级 | 目标类 | 原因 | 方法数 | 建议测试数 |
|--------|-------|------|--------|-----------|
| P0 | `ApiKeyService` | MCP 核心，最近改动最多，含鉴权+审计+续期+scope 校验 | 8 | 12+ |
| P0 | `PermissionQueryService` | v4 ACE 权限解析核心算法，影响所有 KB 访问 | 2 | 8+ |
| P1 | `KbService` | KB 生命周期 + 软删除/恢复 + 级联事件 | 8 | 10+ |
| P1 | `SpaceService` | Space 管理 + admin/group 操作 | 9 | 10+ |
| P1 | `DocumentService` | 483 行上帝类，文档 CRUD + 审批 + 生命周期 | 15 | 15+ |
| P1 | `AceService` | ACE 矩阵 CRUD | 4 | 5+ |
| P2 | `JwtUtil` | Token 生成/解析/校验，安全红线 | 9 | 10+ |
| P2 | `ControllerAuthHelper` | 新增的鉴权工具，需覆盖 SecurityContext + JWT 回退 | 2 | 5+ |
| P2 | `GroupService` | 用户组 CRUD + 层级展开 BFS | 22 | 12+ |

**策略：** 纯 Mockito 单元测试，不启 Spring Context。测试正常路径 + 异常路径（null 输入、权限不足、资源不存在）。

### 阶段 2: Python 高价值模块（安全红线 + 核心链路）

| 优先级 | 目标模块 | 原因 | 建议测试数 |
|--------|---------|------|-----------|
| P0 | `kes_mcp/auth.py` | MCP 鉴权核心：token 交换/刷新/失效/异常处理，**安全红线** | 15+ |
| P0 | `kes_mcp/tools.py` | MCP 3 个 Tool 实现 + 鉴权解析 + kb_ids 交集 | 12+ |
| P1 | `retrieval/reranker.py` | 3 级降级链：Cross-Encoder → LLM → 截断 | 8+ |
| P1 | `retrieval/query_rewriter.py` | Query 改写 + 缓存 + 短路 | 8+ |
| P1 | `retrieval/intent_router.py` | 意图分类：规则前置 + LLM 兜底 | 6+ |
| P1 | `retrieval/citation.py` | 引用标注 + 位置单调约束 | 8+ |
| P2 | `llm/model_pool.py` | 模型池初始化和热重载 | 8+ |
| P2 | `core/context/context_assembler.py` | 上下文组装 + token 预算 | 6+ |
| P2 | `chunking/token_chunker.py` | 语义分块策略 | 6+ |

**策略：** pytest + pytest-asyncio，关键外部依赖（httpx, openai）用 `unittest.mock.AsyncMock`。

### 阶段 3: Java Controller 层（API 行为验证）

| 优先级 | 目标 Controller | 原因 |
|--------|----------------|------|
| P1 | `ApiKeyController` | 7 端点：CRUD + extend + scope + exchange |
| P1 | `AuthController` | 8 端点：login/register/refresh/spaces/switch-space |
| P2 | `SpaceController` | 17 端点：admin/groups/ACEs/KBs/trash/audit |
| P2 | `DocumentController` | 12 端点：upload/approval/lifecycle |

**策略：** `@WebMvcTest` + `MockMvc`，Mock Service 层。验证请求参数校验、响应格式、HTTP 状态码、鉴权拦截。

### 阶段 4: Java Repository + 事件 + 基础设施

| 目标 | 策略 |
|------|------|
| `PermissionQueryService` 集成 | `@DataJpaTest` 验证 SQL 查询正确性 |
| `DocumentMetaRepository` 自定义查询 | 同上 |
| `AceRepository` 自定义查询 | 同上 |
| `AuditEventListeners` | 纯单元：验证事件 → AdminActionLog 持久化 |
| `KbCleanupEventListeners` | 同上 |
| `DocumentEventListeners` | 同上 |
| `JwtFilter` | `MockMvc` + token 过期/无效/缺 token |
| `GlobalExceptionHandler` | `MockMvc` 触发生成验证错误响应格式 |

### 阶段 5: 前端

| 步骤 | 内容 |
|------|------|
| 1 | 安装 `vitest` + `@vue/test-utils` + `jsdom` |
| 2 | 配置 `vitest.config.js` |
| 3 | 测试 `utils/datetime.js`、`utils/idgen.js`、`utils/constants.js`（无 DOM） |
| 4 | 测试 `stores/auth.js`（Pinia store 逻辑） |
| 5 | 测试 `composables/`（useConfirmAction、usePagination 等） |
| 6 | 测试 `api/index.js`（axios 拦截器、token 刷新逻辑） |
| 7 | 组件冒烟测试（关键组件能 mount 不崩溃） |

---

## 估算

| 阶段 | 新增测试文件 | 预计测试行数 | 覆盖率提升 |
|------|------------|-------------|-----------|
| 1: Java Service | 9 | ~2000 | 7% → ~30% |
| 2: Python 高价值 | 9 | ~1500 | 9% → ~25% |
| 3: Java Controller | 4 | ~1200 | ~45% |
| 4: Java Repo + 事件 | 8 | ~1000 | ~55% |
| 5: 前端 | 8 | ~800 | 0% → ~30% |
| **合计** | **38** | **~6500** | |

---

## 不改的内容

- **不追求覆盖率数字** — 目标是关键业务路径有测试，不是追求 X%
- **不做 E2E 测试** — 需要真实 DB/MinIO/Redis/RabbitMQ 环境，收益/成本比太低
- **不做 PDF 解析器全覆盖测试** — 解析器逻辑复杂且依赖外部模型（ONNX/PaddleOCR），做全量测试成本过高

## 验证策略

每阶段完成后执行：
1. `mvn test` — Java 全套
2. `uv run pytest` — Python 全套
3. 确保已有测试不退化
