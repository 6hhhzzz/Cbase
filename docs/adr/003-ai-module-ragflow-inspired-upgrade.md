# ADR 002: AI 模块借鉴 RAGFlow 架构升级

**日期**: 2026-06-22  
**状态**: 已接受  
**决策者**: 项目组

## 背景

当前 AI 模块采用基础的 ETL + pgvector 向量检索架构：

- PDF 解析：仅 `pypdf` 提取纯文本，无布局分析/OCR/表格结构识别
- 分块：固定长度字符切分（512 字符 + 50 重叠）
- 检索：纯向量余弦相似度，IVFFlat 索引
- 缺少：混合检索、Reranker、Query 改写、引用标注

RAGFlow 是 InfiniFlow 开源的生产级 RAG 系统，在文档解析（DeepDOC）、混合检索（BM25 + Dense + RRF）、分块策略等领域积累了大量工程实践。

## 决策

**借鉴 RAGFlow 的设计思路，参考而非复制代码，重写/增强 AI 模块。**

### 架构变更

废弃 `etl/` 线性管道，新建三个核心模块：

```
ai-service/
├── parsing/          # 文档解析引擎（RAGFlow deepdoc 思路）
├── chunking/         # 语义分块引擎（RAGFlow TokenChunker + TitleChunker 思路）
├── retrieval/        # 混合检索引擎（RAGFlow Dealer 思路）
```

### 不做/延后的能力

| 能力 | 决定 | 理由 |
|------|------|------|
| 简历/论文/法律/说明书解析 | 不做 | 垂直场景，开源通用项目不需要 |
| MinerU/Docling/TCADP PDF 后端 | 不做 | 只保留 1-2 种（DeepDOC + PaddleOCR） |
| 30+ 数据源连接器 | 不做 | 社区插件机制，File + MinIO + Git 够用 |
| RAPTOR 递归摘要树 | 不做 | 太重，混合检索已满足需要 |
| Agent/Canvas 编排 | 不做 | MCP 编排在外部处理 |
| GraphRAG 知识图谱 | 延后 | 成本高，作为未来可选项 |

### 关键技术决策

1. **SparseRetriever**: 使用 pgvector 自带的 `tsvector` + `ts_query` + GIN 索引实现 BM25，不引入 Elasticsearch
2. **向量索引**: IVFFlat → HNSW（更高召回率，无需训练）
3. **检索融合**: RRF（Reciprocal Rank Fusion）替代固定权重
4. **意图路由**: 规则前置 + LLM 兜底
5. **Query 改写**: 缓存 + 短路机制 + 关键词提取
6. **引用标注**: 位置单调约束，防止 LLM 交叉乱标

## 后果

### 正面

- 文档解析质量大幅提升（PDF 布局分析、表格结构、OCR）
- 检索召回率大幅提升（混合检索 + Reranker）
- 新增 PPTX 格式支持
- 引用标注提升答案可信度

### 负面

- 需引入 PaddleOCR ONNX 模型（存储成本增加）
- 检索延迟可能增加（Dense + Sparse 并行 + Reranker 串联）
- 旧 `etl/` 模块需要废弃重构

### 中性

- Markdown 解析器语法清理策略变更（保留标题层级 vs 完全去除）
- 需要适配 MQ handler 和 chat API 的接口
