<p align="center">
  <h1 align="center">CBase</h1>
  <p align="center"><strong>面向 AI Agent 的企业知识库中间件</strong></p>
  <p align="center">
    <img src="https://img.shields.io/badge/Java-17-orange?logo=openjdk" alt="Java 17">
    <img src="https://img.shields.io/badge/Python-3.13-blue?logo=python" alt="Python 3.13">
    <img src="https://img.shields.io/badge/Vue-3-green?logo=vuedotjs" alt="Vue 3">
    <img src="https://img.shields.io/badge/PostgreSQL-16%2Bpgvector-blue?logo=postgresql" alt="PostgreSQL">
    <img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker" alt="Docker">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </p>
</p>

---

## 这是什么

CBase 是一个**知识库中间件**——它不仅提供面向人类用户的 RAG 问答界面，更重要的是为 **外部 AI Agent** 提供结构化的知识检索服务。它把企业文档（PDF/Word/Excel/PPT/Markdown 等）经过解析、分块、向量化后存入数据库，对外提供语义检索和智能问答。

**核心场景**：企业内部知识管理，员工通过聊天界面查文档，AI Agent 通过 MCP 协议查询知识库。

---

## 架构

```
                       ┌────────────────────────────────┐
                       │         Frontend (Vue 3)        │
                       │     Chat · Documents · Admin    │
                       └──────────────┬─────────────────┘
                                      │ HTTP/SSE (Nginx)
                 ┌────────────────────┴────────────────────┐
                 │            Java Backend (:8080)          │
                 │   Spring Boot · JWT · ACE 权限 · DDD    │
                 └────────┬───────────────────────┬────────┘
                          │                       │
              ┌───────────┴───────┐   ┌───────────┴───────┐
              │   Python AI (:8000)│   │   基础设施           │
              │   FastAPI · pgvector│   │   PostgreSQL+pgvector│
              │   HybridSearch     │   │   Redis · RabbitMQ  │
              │   Rerank · LLM     │   │   MinIO 对象存储     │
              └────────────────────┘   └────────────────────┘
```

**两条检索路径**：

| 场景 | 消费者 | 特征 |
|------|--------|------|
| Web Chat (`/v1/chat`) | 人类用户 | 对话式、QueryRewrite 消解指代、LLM 生成答案 |
| MCP (`kes_mcp/`) | 外部 AI Agent | 结构化、零 LLM 预处理、协议层约束查询质量 |

---

## 快速开始

```bash
# 1. 克隆项目
git clone <repo-url> && cd cbase

# 2. 配置 LLM API Key
echo "DASHSCOPE_API_KEY=sk-your-key-here" >> .env

# 3. 一键启动
docker compose up -d

# 4. 打开浏览器
# http://localhost       → 前端界面
# http://localhost:8080  → Java 后端
# http://localhost:15672 → RabbitMQ 管理面板
```

首次启动会自动创建数据库表、初始化管理员账号（admin / 随机密码，查看启动日志）。

---

## 核心功能

| 模块 | 功能 |
|------|------|
| 🔍 **混合检索** | 语义向量 (HNSW) + 关键词 (BM25) → RRF 融合 → Cross-Encoder 重排序 |
| 🤖 **MCP 知识服务** | 标准 MCP 协议，3 个 Tool + 1 个 Resource + 3 个 Prompt，Agent 可自主检索 |
| 🔐 **ACE 权限模型** | 用户组 → Space → KB 三级，支持 ACE 矩阵、角色自定义、组嵌套继承 |
| 📄 **文档管理** | 上传 → 深度解析（PDF/Office/HTML/Markdown）→ 语义分块 → 向量入库 |
| 💬 **RAG 问答** | 多轮对话、流式 SSE 响应、引用标注、Query 改写、意图路由 |
| 👥 **企业管理** | 用户管理、CSV 批量导入、审计日志、KB 回收站 |

---

## 技术亮点

### DDD 分层架构
Controller → Service → Repository 严格分层。跨模块通信通过 Spring Events 解耦，禁止直接注入其他模块的 Repository。每个类 ≤ 300 行。

### 统一错误码体系
45 个 ErrorCode 枚举，Java/Python/前端三层一致。响应格式：`{"error_code": "DOC_NOT_FOUND", "message": "文档不存在"}`。字符串错误码自描述，调试不需要查表。

### 双 Token 认证
`refresh_token`(7天) + `context_token`(30分钟)。切换 Space 签出上下文 Token，细粒度 Space/KB 权限隔离。支持 MCP API Key → JWT Token 交换。

### 权限注解
```java
@RequireSpaceAdmin   // 声明式权限校验，AOP 切面自动拦截
@RequireGlobalAdmin
public ApiResponse<?> deleteSpace(...) { ... }
```

### MCP 协议支持
对外部 AI Agent 暴露标准 MCP stdio 接口。Claude Desktop / Cursor / 其他 MCP 客户端可直接连接 CBase 作为知识源。search_chunks 零 LLM 调用，纯本地 ~5ms 预处理。

### 事件驱动解耦
软删除 KB → 发布 `KbSoftDeletedEvent` → Document 模块监听 → 级联软删除文档 → AI 模块监听 → 同步向量数据库。各模块独立演进，互不污染。

---

## 项目结构

```
cbase/
├── frontend/          Vue 3 + Element Plus + Pinia
│   ├── src/views/     11 个页面 (Chat/Documents/Settings/Admin)
│   ├── src/components/ 17 个组件 (chat/documents/settings)
│   └── src/composables/ 8 个共享逻辑 composable
│
├── backend/           Spring Boot 3.3 + JPA + Security
│   └── src/main/java/com/kes/
│       ├── auth/       认证 · 权限 · Space · KB · ACE · 用户组
│       ├── document/   文档 CRUD · 审批 · MinIO 存储
│       ├── rag/        问答 · SSE 中继 · Python 客户端
│       ├── conversation/  会话管理
│       └── common/     异常 · DTO · 事件 · 注解 · 工具
│
├── ai-service/        FastAPI + pgvector + OpenAI SDK
│   ├── api/           REST 端点 (chat/health/documents)
│   ├── retrieval/     检索执行层 (HybridSearch/Reranker/Citation)
│   ├── parsing/       文档解析引擎 (PDF/Office/HTML/Markdown)
│   ├── chunking/      语义分块引擎 (Token/Title/Semantic)
│   ├── llm/           LLM 调用 · 模型池 · Prompt 管理
│   ├── kes_mcp/       MCP stdio Server (3 Tools + 1 Resource + 3 Prompts)
│   └── mq/            RabbitMQ 消费端 (ETL 管道)
│
├── scripts/           SQL 迁移脚本 · 种子数据 · 测试文档
└── docs/              架构决策记录 (ADR) · 参考资料 · 报告
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 (Composition API) · Vite · Element Plus · Pinia · Axios · marked |
| Java 后端 | Spring Boot 3.3 · Spring Security · JPA · JWT · RabbitMQ · Redis |
| Python AI | FastAPI · asyncpg · pgvector · OpenAI SDK · jieba · MCP SDK |
| 数据库 | PostgreSQL 16 + pgvector (HNSW 索引 + tsvector 全文) |
| 中间件 | Redis 7 · RabbitMQ 3 · MinIO |
| 部署 | Docker Compose 一键部署 · 多阶段构建 |

---

## 工程化

- **Docker 一键部署** — `docker compose up -d`
- **统一错误码** — 45 个 ErrorCode 枚举，Java/Python/前端三层一致
- **CI 流水线** — GitHub Actions 自动编译 + 测试 (33 Java + 30 Python)
- **DDD 分层** — Controller/Service/Repository 严格分层，事件驱动跨模块解耦
- **代码规范** — 单类 ≤ 300 行 · 构造函数注入 · 统一代码风格

---

## 文档

| 文档 | 说明 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | 完整架构文档（服务职责、源码索引、API 端点） |
| [docs/adr/](docs/adr/) | 架构决策记录 |
| [docs/reports/](docs/reports/) | 工程审计报告 |

---

## License

MIT
