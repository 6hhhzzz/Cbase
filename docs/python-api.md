# Python AI 服务接口文档

> 基于 `ai-service/api/` 代码提取，共 **8 个端点**。服务端口 `8000`。

## 架构说明

Python AI 服务定位为检索+生成引擎，**不处理认证授权**。所有业务请求来自 Java 后端代理（已鉴权），内部端点仅供 Java 调用。

### 四层异常处理

| 异常类型 | HTTP 状态码 | 响应格式 |
|---------|-----------|---------|
| `RequestValidationError` | 400 | `{"error": "validation_error", "message": "..."}` |
| `AppException(error_code)` | 按前缀映射 | `{"code": int, "error_code": "...", "message": "..."}` |
| `Exception`（通用） | 500 | `{"code": 500, "error_code": "INTERNAL_ERROR", "message": "服务器内部错误"}` |

**error_code → HTTP 状态码映射**：`MISSING/INVALID/UNSUPPORTED` → 400，`AUTH` → 401，`ACCESS_DENIED` → 403，`NOT_FOUND` → 404，`SERVICE_UNAVAILABLE` → 503。

### 依赖注入

| `Depends()` 函数 | 返回类型 | `app.state` 键 |
|-----------------|---------|----------------|
| `get_llm()` | `BaseLLM` | `llm` |
| `get_embedding()` | `BaseEmbedding` | `embedding` |
| `get_embedding_wrapper()` | `EmbeddingWrapper` | `embedding_wrapper` |
| `get_pgvector_client()` | `PGVectorClient` | `pgvector_client` |
| `get_history_manager()` | `HistoryManager` | `history_manager` |
| `get_context_assembler()` | `ContextAssembler` | `context_assembler` |
| `get_summary_engine()` | `SummaryEngine` | `summary_engine` |
| `get_mq_client()` | `MQClient` | `mq_client` |

所有服务在 `lifespan` 启动时创建并注入到 `app.state`，端点通过 `Depends` 获取。

---

## 1. POST /v1/chat — RAG 问答（SSE 流式）

**文件**: `api/chat.py:58`
**认证**: 无（Java 代理已鉴权），强制要求 `filter_params`

### 请求体 — `ChatRequest`

```json
{
  "query": "string (1-4096字符，必填)",
  "filter_params": {
    "kb_ids": ["uuid"],
    "doc_ids": ["uuid"]        // 可选，排除特定文档
  },
  "conversation_id": "uuid (必填)",
  "history_messages": [        // 可选，Java 转发自 PG
    {
      "role": "user|assistant|system|context",
      "content": "string",
      "metadata": {}
    }
  ],
  "top_k": 5                   // 1-20，默认5
}
```

### 安全红线 — `filter_params`

```
filter_params 为空 → HTTP 400 {"error_code": "PARAM_MISSING", "message": "filter_params ..."}
```

Python 机械构建 `WHERE kb_id = ANY($1)`，不做权限判断。`kb_ids` 列表由 Java 的 ACE 权限解析算法计算。

### 响应 — SSE 流

**Headers**: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`

**Token chunk**:
```
data: {"token": "文本片段", "done": false}
```

**最终 chunk**:
```
data: {"token": "", "done": true, "sources": [...], "citations": [...], "trace": {...}}
```

### 处理流水线

```
Query → Stage 0: Semantic Cache (Redis, ~5ms)
     → Stage 1: QueryPreprocessor (三合一 SLM)
     → Stage 2: QueryPlanner (DAG 拆解)
     → Stage 3: DAG Execution (HyDE + 三维提取 + 三路混合检索)
     → Stage 4: Reranker (API → Cross-Encoder → LLM 降级)
     → Stage 5: Critic Agent (置信度 + 知识验证 + 补充检索)
     → Stage 6: Context Assembly (分组 + Grounding + 预算)
     → Stage 7: LLM 生成 (流式, 110s 超时)
     → Citation 插入 + Trace 落库
```

### 错误处理

LLM 调用异常被分为 5 类并在流内返回中文错误 token：

| 异常类型 | 返回消息 |
|---------|---------|
| 认证失败 | "抱歉，AI 模型认证失败，请联系管理员检查 API Key 配置。" |
| 模型不存在 | "抱歉，配置的 AI 模型不可用..." |
| 超时 | "抱歉，AI 服务响应超时，请稍后重试。" |
| 连接失败 | "抱歉，AI 服务连接失败..." |
| 通用错误 | 实际异常消息（截断至 100 字符） |

`finally` 块确保即使 LLM 异常，sources 也不丢失，在最终 chunk 中返回。

---

## 2. GET /v1/health — 健康检查

**文件**: `api/health.py:22`
**认证**: 无（公开端点）

### 响应 — `HealthResponse`

```json
{
  "status": "healthy|degraded",
  "components": {
    "pgvector": "healthy|unhealthy",
    "llm": "healthy|unhealthy",
    "embedding": "healthy|unhealthy",
    "rabbitmq": "healthy|unhealthy"
  }
}
```

### 检查逻辑

| 组件 | 检查方式 | 超时 |
|------|---------|------|
| `pgvector` | `pgvector_client.ping()` → 连接池探活 | — |
| `llm` | `llm.generate_content("ping", max_tokens=1)` | — |
| `embedding` | `embedding.embed_query("ping")` → 嵌入向量 | — |
| `rabbitmq` | `mq_client.ping()` → 连接状态 | — |

任一 unhealthy → 整体 `status = "degraded"`。

---

## 3. POST /v1/documents/status — 文档状态同步

**文件**: `api/documents.py:20`
**认证**: 无（内网调用，Java 触发）

### 请求体 — `DocumentStatusRequest`

```json
{
  "doc_id": "string (文档 UUID)",
  "status": "active|soft_deleted"
}
```

### 响应

```json
{ "ok": true, "updated": 15 }
```

`updated`: `knowledge_chunks` 表中状态被更新的行数。

### 用途

Java 软删除/恢复文档时，同步更新 pgvector 中所有关联 chunk 的 `status` 字段。`soft_deleted` 状态的 chunk 在检索时自动被 `WHERE status = 'active'` 过滤掉。

---

## 4. DELETE /v1/documents/{doc_id}/chunks — 删除文档向量

**文件**: `api/documents.py:31`
**认证**: 无（内网调用，Java 触发）

### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `doc_id` | `str` | 文档 ID（代码为纯字符串，无 UUID 校验） |

### 响应

```json
{ "ok": true, "deleted": 20 }
```

`deleted`: 从 `knowledge_chunks` 表中物理删除的 chunk 数。

### 用途

Java 永久删除文档时调用，清空该文档在 pgvector 中的所有向量数据。

---

## 5. POST /v1/admin/models/discover — 模型发现

**文件**: `api/admin_models.py:32`
**认证**: 无（Java `@RequireGlobalAdmin` 代理）

### 请求体 — `DiscoverRequest`

```json
{
  "provider_type": "openai_compatible|ollama",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key": "sk-xxx",
  "model_type_filter": "chat|embedding"   // 可选，当前未使用
}
```

### 响应

```json
{
  "models": [
    {"id": "qwen-plus", "owned_by": "dashscope"},
    {"id": "text-embedding-v3", "owned_by": "dashscope"}
  ],
  "total": 2
}
```

### 实现逻辑

| provider_type | 方式 | 超时 |
|--------------|------|------|
| `openai_compatible` | `AsyncOpenAI().models.list()` | — |
| `ollama` | `GET {base_url}/api/tags` (httpx) | 10s |

---

## 6. POST /v1/admin/models/test — 连通性测试

**文件**: `api/admin_models.py:47`
**认证**: 无（Java `@RequireGlobalAdmin` 代理）

### 请求体 — `TestRequest`

```json
{
  "provider_type": "openai_compatible|ollama",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "api_key": "sk-xxx",
  "model_name": "qwen-plus"              // 可选，当前未使用
}
```

### 响应

```json
// 成功
{ "success": true, "latency_ms": 123.4 }

// 失败
{ "success": false, "error": "connection refused" }
```

---

## 7. GET /v1/admin/models/config — 读取模型配置

**文件**: `api/admin_models.py:119`
**认证**: 无（Java `@RequireGlobalAdmin` 代理）

### 响应

```json
{
  "providers": {
    "dashscope": {
      "type": "openai_compatible",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "api_key": "sk-****",            // 脱敏：仅显示前4+后4
      "description": "阿里云 DashScope"
    }
  },
  "models": {
    "qwen-plus": {
      "provider": "dashscope",
      "model_name": "qwen-plus",
      "model_type": "chat",
      "max_tokens": 131072,
      "params": { "temperature": 0.3, "max_tokens": 2048 }
    }
  },
  "assignments": {
    "chat": {
      "model": "qwen-plus",
      "fallback": "slm",
      "description": "主 LLM — RAG 问答生成",
      "fallback_chain": ["qwen-plus", "qwen-turbo"]
    }
  },
  "version": 2,
  "config_path": "/app/config/models.yaml"
}
```

文件不存在时返回空数据 + `"error": "配置文件不存在"`。

---

## 8. PUT /v1/admin/models/config — 更新模型配置

**文件**: `api/admin_models.py:151`
**认证**: 无（Java `@RequireGlobalAdmin` 代理）

### 请求体 — `ConfigUpdateRequest`

```json
{
  "config_json": { ... },          // JSON 对象（前端推荐）
  "yaml_content": "version: 2\n..." // YAML 字符串（兼容）
}
```

两者至少提供一个。优先使用 `config_json`。

### 校验流程

```
yaml_content 存在 → yaml.safe_load() 解析
config_json 存在 → 直接使用
         ↓
Pydantic ModelsConfig(**raw) 校验
         ↓
_validate_references() 交叉引用检查（provider/model 必须存在）
         ↓
save_models_config() 原子写入 YAML 文件（写临时文件 → rename）
         ↓
Python 30s 内通过 mtime 检测到变更 → 热重载
```

### 响应

```json
// 成功
{ "success": true, "message": "配置已保存" }

// 校验失败 (400)
{ "detail": "配置校验失败: provider 'xxx' not found for model 'yyy'" }

// 写入失败 (500)
{ "detail": "写入失败: Permission denied" }
```

---

## 端点总览

| 方法 | 路径 | 用途 | 调用方 |
|------|------|------|--------|
| POST | `/v1/chat` | RAG 问答（SSE 流式） | Java ChatController 代理 |
| GET | `/v1/health` | 组件健康检查 | Docker/K8s 探针 |
| POST | `/v1/documents/status` | 文档状态同步 | Java DocumentService |
| DELETE | `/v1/documents/{doc_id}/chunks` | 删除文档向量 | Java DocumentService |
| POST | `/v1/admin/models/discover` | 模型发现 | Java AdminModelController |
| POST | `/v1/admin/models/test` | 连通性测试 | Java AdminModelController |
| GET | `/v1/admin/models/config` | 读取 models.yaml | Java AdminModelController |
| PUT | `/v1/admin/models/config` | 更新 models.yaml | Java AdminModelController |

## 关键 Pydantic 模型

| 模型 | 文件 | 用途 |
|------|------|------|
| `ChatRequest` | `models/chat.py` | POST /v1/chat 请求体 |
| `ChatMessage` | `models/chat.py` | 历史消息项 |
| `ChatTokenChunk` | `models/chat.py` | SSE 响应块 |
| `FilterParams` | `models/retrieval.py` | 权限过滤参数（安全红线） |
| `SearchResult` | `models/retrieval.py` | 单条检索结果（含 chunk_id） |
| `DocumentStatusRequest` | `models/lifecycle.py` | 文档状态同步请求 |
| `HealthResponse` | `models/health.py` | 健康检查响应 |
| `ConfigUpdateRequest` | `api/admin_models.py` | 配置更新请求（双格式） |
