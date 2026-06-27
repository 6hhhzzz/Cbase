# KES 工程化审计报告 — 问题跟踪

> 📅 2026-06-27 | 基于 improve-codebase-architecture 技能全面扫描
> 完整 HTML 报告: `/tmp/architecture-review-20260627.html`

## 修复进度

| 状态 | 计数 |
|------|------|
| ✅ 已修复 | 14 |
| 📋 待讨论/待修复 | 19 |

---

## 一、快速修复 (低投入高回报) — 本轮已完成

### 🔴 安全相关

- [x] **1.1 CI 掩盖 Python 测试失败** — `ci.yml:43` `|| echo "⚠️ 测试文件待补充"` 使测试永远通过
  - 修复: 删除 `|| echo ...`

- [ ] **1.2 已提交的 API Key 泄漏** — `.claude/settings.json:14` 包含有效 MCP 密钥
  - 修复: 轮换密钥，用环境变量 `${KES_API_KEY}` 替代 **(需人工操作)**

- [x] **1.3 JWT 弱密钥填充** — `JwtUtil.java:52-55` 用 `'0'` 字符填充短密钥
  - 修复: 要求密钥 ≥32 字符，不足时启动失败并给出明确 `IllegalArgumentException`

- [x] **1.4 Admin 密码打印到日志** — `SystemBootstrap.java:51-58`
  - 修复: 优先使用 `KES_INIT_ADMIN_PASSWORD` 环境变量；直接打印时附带安全警告

- [x] **1.5 viewUrl Token 泄漏** — 前端 `api/index.js:192-195`
  - 修复: 添加安全待办注释（Phase 2 需要后端短期签名 URL 机制）

- [x] **1.6 ChatMessage v-html XSS 风险** — `ChatMessage.vue:9`
  - 修复: 安装 DOMPurify，`marked.parse()` 后 `DOMPurify.sanitize()` 白名单过滤

### 🟡 代码质量

- [x] **1.7 MinIO `:latest` 标签** — `docker-compose.yaml:90`
  - 修复: 固定到 `minio/minio:RELEASE.2024-08-17T01-24-10Z`

- [x] **1.8 删除空文件 semantic_chunker.py** — 29 行全是注释和 TODO
  - 修复: 删除文件，确认无引用

- [x] **1.9 CitationInserter._text_overlap 返回常量** — 永远返回 0.45
  - 修复: 改为传递句子文本，实现基于 bigram Jaccard 系数的真实文本重叠度计算

- [x] **1.10 前端全局图标注册阻止 tree-shaking** — `main.js:17-20`
  - 修复: 移除 200+ 图标全局注册（仅 InfoFilled 实际使用，已按需引入）

### 🔵 工程化

- [x] **1.11 缺少 `.env.example`** — 无环境变量文档
  - 修复: 创建 `.env.example` 列出所有环境变量及说明

- [x] **1.12 前端 SSE 缺少 onUnmounted 清理** — `Chat.vue`
  - 修复: 添加 `onUnmounted(() => cancelStreaming())` 清理定时器和 AbortController

- [x] **1.13 GroupManagement.vue 用户搜索重复实现**
  - 修复: 移除本地 `searchUsers`，改用 `useUserSearch()` composable

- [x] **1.14 3 个静态 ObjectMapper 绕过 Spring 配置**
  - 修复: `PermissionService.java`, `ChatController.java`, `IngestCallbackConsumer.java` 改为构造函数注入 Spring 管理的 ObjectMapper
  - 同步更新 `PermissionServiceTest.java` 适配新构造函数

---

## 二、中等修复 (需要进一步讨论方案)

### 🔴 错误码体系 (待讨论)

- [ ] **2.1 创建 ErrorCode 枚举** — 统一所有错误码
  - 当前: HTTP 404/400/403/500 与业务码 1001-4003 混用，AdminModelService 的 4001-4005 与 Conversation 冲突
  - 方案选项: (A) 数字分段 `AABBCC` (模块-子模块-序号) vs (B) 字符串枚举 `AUTH-TOKEN-EXPIRED`

- [ ] **2.2 Python 端同步错误码**

- [ ] **2.3 前端根据业务错误码做精确处理**

### 🟡 DDD 分层修复 (已完成 ✅ 2026-06-27)

- [x] **2.4 SpaceController 移除 Repository 注入** — 移除 `UserRepository` / `UserGroupRepository` / `DocumentService`
  - `getAdmins()` → `SpaceService.getAdminsWithUserInfo()`
  - `getGroups()` → `SpaceService.getGroupsWithName()`
  - `getAuditLogs()` → `AdminService.getAuditLogsWithOperatorNames()`
  - `getTrash()` → `KbService.getTrashData()`
- [x] **2.5 AuthController 移除 KB Repository 注入** — 移除 `KnowledgeBaseRepository` / `UserRepository`
  - `getAccessibleKBs()` → `PermissionQueryService.resolveAccessibleKbInfoList()`
  - `searchUsers()` → `AuthService.searchUsers()`
- [x] **2.6 KbService 移除 DocumentMetaRepository** — 事件精简，监听器自行查询
- [x] **2.7 PermissionQueryService 移除 DocumentMetaRepository** — 新建 `DocumentPermissionService` 门面

### 🔵 其他

- [ ] **2.6 `.claude/settings.json` API Key 泄漏** — 需轮换密钥 + 改为环境变量

---

## 三、大型重构 (需规划设计，待讨论)

### 测试覆盖

- [ ] **3.1 Java 集成测试** — TestContainers + 权限关键路径
- [ ] **3.2 Python 核心链路测试** — retrieval orchestrator + MCP tools + chat endpoint
- [ ] **3.3 前端测试基础设施** — vitest + vue-test-utils 搭建
- [ ] **3.4 CI 添加覆盖率阈值门禁** — JaCoCo + pytest-cov

### 大文件拆分 (>300行)

- [ ] **3.5 DocumentService.java (482行)**
- [ ] **3.6 AdminService.java (383行)**
- [ ] **3.7 kes_mcp/server.py (528行)**
- [ ] **3.8 ApiKeyManager.vue (394行)**
- [ ] **3.9 GroupManagement.vue (330行)**

### Python 架构

- [ ] **3.10 双解析器清理** — 移除 `etl/parsers/`
- [ ] **3.11 kes_mcp/server.py 全局状态消除**
- [ ] **3.12 PGVectorClient 拆分**
- [ ] **3.13 MQ 死信队列**

### 基础设施

- [ ] **3.14 Docker 资源限制**
- [ ] **3.15 Flyway 迁移管理**
- [ ] **3.16 CI 添加 lint/安全扫描/依赖审计**
- [ ] **3.17 根目录 README.md**

---

## 本轮修复总结

| 类别 | 修复数 | 文件数 |
|------|--------|--------|
| Java 后端 | 4 | 7 文件 |
| Python AI Service | 2 | 2 文件 |
| Vue 前端 | 5 | 5 文件 |
| 基础设施/CI | 3 | 4 文件 |

**验证状态:**
- ✅ Java 33 tests passed
- ✅ Python 30 tests passed
- ✅ Frontend build succeeded
- ⚠️ `.claude/settings.json` API Key 需人工轮换
