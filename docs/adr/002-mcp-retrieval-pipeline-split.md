# ADR-002: MCP 检索链路拆分 — Agent 一等公民架构

> 状态: **已接受** | 日期: 2026-06-27 | 决策者: 项目作者

## 背景

系统最初有两套知识消费路径：

1. **Web Chat** (`/v1/chat`)：人类用户通过 Web 前端发起多轮 RAG 对话，Java 转发对话历史，Python 做检索+生成
2. **MCP** (`kes_mcp/`)：外部 AI Agent 通过 MCP stdio 协议调用三个 Tool（`search_chunks` / `read_document` / `ask_expert`）

两者共用同一套 `RetrievalOrchestrator.retrieve()` 检索链路。该链路原为多轮对话的人设计——`QueryRewriter` 消解指代、`IntentRouter` 意图分类、`ContextAssembler` 组装历史摘要。

MCP 场景无对话历史，导致 `QueryRewriter` 每次都短路（`history_len=0 → return False`），`keywords` 始终为空，BM25 稀疏检索缺少关键信号，整条链路处于退化运行状态。

## 问题本质

两种场景的查询准备层解决的是**相反的问题**：

| | Web Chat | MCP |
|------|----------|-----|
| 输入特征 | 口语化、省略、指代依赖历史 | 精炼、结构化、单轮自包含 |
| 查询准备目标 | **语义收敛**（模糊→精确） | **语义扩展**（精确→丰富） |
| 核心手段 | LLM 消解指代 + 补全术语 | jieba 实体提取 + 关键词扩展 |
| 延迟成本 | +500ms（LLM 1~2 次） | +5ms（纯本地） |

**根本问题**：同一个 `retrieve()` 接口强行服务两种相反语义，MCP 被视为 Web Chat 的"无历史退化版本"而非独立场景。

## 决策

### 1. 拆分查询准备层，共享检索执行层

```
                    ┌──────────────────────────────┐
                    │      检索执行层 (共享)         │
                    │  RetrievalOrchestrator.execute│
                    │  HybridSearch ∥ Reranker      │
                    └──────────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
 ┌────────────┴────────────┐               ┌────────────┴───────────┐
 │  Web Chat 查询准备       │               │  MCP 查询准备            │
 │  retrieve()             │               │  McpQueryPreparator    │
 │  QueryRewriter (LLM)    │               │  + execute()           │
 │  IntentRouter (LLM 兜底) │               │  jieba 提取 + 协议约束  │
 └─────────────────────────┘               └────────────────────────┘
```

- `RetrievalOrchestrator.execute(query, kb_ids, keywords, top_k)` — 纯检索执行，不关心 query 来源
- `RetrievalOrchestrator.retrieve(query, kb_ids, history_messages, top_k)` — Web Chat 完整流程（保留向后兼容）
- `McpQueryPreparator.prepare(query, context_hint, focus_aspects, ...)` — MCP 专用查询准备

### 2. MCP 协议层作为质量保障第一关

**原则**：不为 MCP 场景在服务端做语义理解（Agent 自己就是 LLM），而是通过 MCP 协议层的 Tool description / inputSchema / Prompt 指导 Agent 构造高质量输入。

具体措施：
- Tool description 增加场景选择指导（何时用 `search_chunks` vs `ask_expert`）和 query 构造示例
- inputSchema 新增 `context_hint`、`focus_aspects`、`doc_type` 等 Agent 上下文透传参数
- 新增 `kb_search_strategy` 行为指导 Prompt（教 Agent 如何提取实体、选择 Tool、构造 query）

### 3. MCP 检索阶段零 LLM 调用

`McpQueryPreparator` 仅做本地处理：
- jieba 分词 + 停用词过滤 + 词长过滤 → 关键词列表
- 正则捕获实体模式（版本号、错误码、文件名）
- `focus_aspects` 到中文关键词的静态映射

## 后果

### 正面
- MCP 检索延迟从 ~500ms 降至 ~5ms（跳过 LLM 改写+意图分类）
- BM25 不再空跑——关键词从 jieba 提取而非依赖 QueryRewriter
- 协议层为 Agent 提供明确的使用指导，降低"垃圾进垃圾出"的风险
- Web Chat 路径行为完全不变，零回归风险
- 两条路径职责清晰，未来各自独立演进不互相影响

### 负面
- 新增一个模块（`mcp_query_preparator.py`），增加维护面
- 依赖 `jieba` 分词库（从 optional 提升为直接依赖）
- 短 query 场景下（如 `"报错"`），jieba 提取的关键词数量有限，效果弱于 LLM 扩展

### 风险与缓解
- **风险**：Agent 不遵守协议层指导，仍然传低质量 query → **缓解**：`kb_search_strategy` Prompt 主动指导；`context_hint` 提供补救通道
- **风险**：`focus_aspects` 的静态映射表覆盖不全 → **缓解**：关注方面枚举值有限，随业务需求扩展即可

## 备选方案

**方案 B：保留 LLM 改写，为 MCP 场景新增"零历史改写"模式** — 让 QueryRewriter 在 `history_len=0` 时不短路，改为做关键词提取 + query 扩展。被拒绝的原因：(1) 仍需要 LLM 调用，增加延迟和成本；(2) Agent 场景的 LLM 改写价值有限（Agent 已经做了语义理解）；(3) 与"Agent 一等公民"原则冲突——不应该用服务端 LLM 重复 Agent 已完成的工作。

**方案 C：完全拆分两套检索链路** — 不只是查询准备层，连 HybridSearch 和 Reranker 也做两套。被拒绝的原因：(1) 检索执行层逻辑相同，拆分无意义；(2) 增加维护负担；(3) 配置同步问题。

## 参考资料

- `docs/plans/mcp-vivid-seahorse.md` — 实施计划
- `ai-service/retrieval/orchestrator.py` — 重构前/后的检索编排器
- `ai-service/retrieval/mcp_query_preparator.py` — 新建的 MCP 查询准备器
- `ai-service/kes_mcp/server.py` — 协议层重写
- `ai-service/kes_mcp/tools.py` — 工具实现重构
