# RAGFlow 文档处理模块源码拆解

> 通过阅读源代码，从架构设计、数据流向、关键代码实现三个层面拆解 RAGFlow 的文档处理模块，为构建企业知识助手提供可复用的设计经验。

---

## 一、整体架构概览

RAGFlow 的文档处理分为**两条执行路径**，共存于代码库中：

| 路径 | 入口 | 适用场景 | 调度方式 |
|------|------|----------|----------|
| **传统路径**（`task_executor.py`） | 文档上传 → Redis Stream → `do_handle_task()` | 常规文档解析 + 基础切片 | Worker 进程按 FIFO 取 Redis 消息 |
| **Pipeline 路径**（可编排数据管道） | `rag/flow/pipeline.py` 的 `Pipeline.run()` | 用户自定义 DAG 流程 | 在 `run_dataflow()` 中被调用，按拓扑序执行组件 |

### 1.1 任务调度入口

```
用户上传文档
    │
    ▼
api/apps/  ──写入MySQL──▶  Task 表 (待处理任务)
    │                       │
    │                       ▼
    │              Redis Streams (队列名: te.{idx}.common)
    │                       │
    │                       ▼ Consumer Group 负载分发
    │              rag/svr/task_executor.py
    │                  collect()  ← 从 Redis 拉取消息
    │                      │
    │                      ▼
    │              do_handle_task(task)   ← 任务分发
    │                /        |         \
    │          dataflow    raptor    graphrag   standard
    │              │                              │
    │              ▼                              ▼
    │     run_dataflow()                   build_chunks()
    │              │                              │
    │              ▼                              ▼
    │     Pipeline.run()              chunk() + embedding()
    │                                        │
    │                                        ▼
    │                                 insert_chunks()
    │                                        │
    └────────────────────────────────────────┘
                                         │
                                         ▼
                              Elasticsearch / Infinity
```

**关键源码文件**：

- [task_executor.py:1357](rag/svr/task_executor.py#L1357) — `do_handle_task()`，任务分发入口
- [task_executor.py:199](rag/svr/task_executor.py#L199) — `collect()`，从 Redis Stream 拉取任务消息
- [task_executor.py:270](rag/svr/task_executor.py#L270) — `build_chunks()`，传统路径的核心处理函数
- [task_executor.py:731](rag/svr/task_executor.py#L731) — `run_dataflow()`，Pipeline 路径
- [task_executor.py:1850](rag/svr/task_executor.py#L1850) — `main()`，Worker 进程主循环

### 1.2 两条路径的核心区别

**传统路径**（`do_handle_task` → `build_chunks`）：
- 固定流程：解析文件 → 切片 → 关键词/问题/元数据 LLM 增强 → 向量化 → 入库
- 调用 [rag/app/naive.py](rag/app/naive.py) 中的 `chunk()` 函数
- 适合常规文档处理的默认路径

**Pipeline 路径**（`run_dataflow` → `Pipeline.run()`）：
- 用户通过 UI 画布自建 DAG 流程
- 组件可自由编排：File → Parser → TokenChunker → Tokenizer → Extractor → ...
- DSL 由 JSON 描述，存储于 `UserCanvasService` 或 `PipelineOperationLogService`
- `Pipeline` 类继承自 `agent.canvas.Graph`，复用 Agent 系统的 DAG 执行引擎

---

## 二、传统路径详解：`build_chunks()` → `chunk()` 全链路

### 2.1 整体流程

```
build_chunks(task)                          [task_executor.py:270]
    │
    ├─ 1. 文件大小检查 (> DOC_MAXIMUM_SIZE 直接拒绝)
    │
    ├─ 2. 从 MinIO 拉取文件二进制 (File2DocumentService.get_storage_address)
    │
    ├─ 3. 合并 KB 级别 parser_config (merge_table_parser_config_from_kb)
    │
    ├─ 4. 调用 chunker.chunk() ──── 即 rag/app/*.py 的 chunk()
    │       │                          [naive.py:814]
    │       ├─ 文件类型路由 (PDF/DOCX/XLSX/MD/...)
    │       ├─ 调用对应 DeepDoc Parser
    │       ├─ naive_merge() 文本合并
    │       ├─ tokenize_chunks() 分词 + 生成 chunk dict
    │       └─ 返回 [{"id": ..., "content_with_weight": ..., "docnm_kwd": ...}, ...]
    │
    ├─ 5. 为每个 chunk 生成唯一 ID (xxhash)
    ├─ 6. 图片上传 MinIO (image2id)
    │
    ├─ 7. LLM 增强 (可选，并行执行):
    │       ├─ auto_keywords    → keyword_extraction()
    │       ├─ auto_questions   → question_proposal()
    │       ├─ enable_metadata  → gen_metadata()
    │       └─ tag_kb_ids       → content_tagging()
    │
    ├─ 8. embedding() ──── 标题 + 正文向量加权融合
    │
    ├─ 9. insert_chunks() ──── 批量写入 ES/Infinity
    │
    └─ 10. build_TOC() ──── LLM 生成目录 (可选)
```

### 2.2 chunk() 函数：文件类型路由 + 解析 + 切片

`chunk()` 是所有传统路径解析器的**统一入口**，位于 [rag/app/naive.py:814](rag/app/naive.py#L814)：

```python
def chunk(filename, binary=None, from_page=0, to_page=MAXIMUM_PAGE_NUMBER,
          lang="Chinese", callback=None, **kwargs):
    parser_config = kwargs.get("parser_config", ...)
```

它按文件扩展名路由到不同的解析逻辑：

```
文件扩展名匹配 (顺序判断):
    .docx          → Docx() 解析 + naive_merge_docx()
    .pdf           → PARSERS[layout_recognizer]() 解析 + tokenize_table()
    .csv/.xlsx     → ExcelParser() 解析
    .txt/py/js/... → TxtParser() 解析
    .md/.markdown  → Markdown() 解析
    .html/.htm     → HtmlParser() 解析
    .epub          → EpubParser() 解析
    .json/.jsonl   → JsonParser() 解析
    .doc           → Apache Tika 解析
    其他           → NotImplementedError
```

**解析器工厂表** `PARSERS`（[naive.py:338](rag/app/naive.py#L338)）将 PDF 解析方法映射到具体函数：

```python
PARSERS = {
    "deepdoc":        by_deepdoc,       # 自研视觉解析 (OCR + 版面 + 表格)
    "mineru":         by_mineru,        # MinerU 解析器
    "docling":        by_docling,       # IBM Docling 解析器
    "opendataloader": by_opendataloader, # OpenDataLoader
    "tcadp parser":   by_tcadp,         # 腾讯云文档解析
    "paddleocr":      by_paddleocr,     # PaddleOCR
    "plaintext":      by_plaintext,     # 纯文本 (PlainParser 或 VisionParser)
}
```

**PDF 解析派发逻辑**（[naive.py:905](rag/app/naive.py#L905)）：
```python
elif re.search(r"\.pdf$", filename, re.IGNORECASE):
    layout_recognizer, parser_model_name = normalize_layout_recognizer(
        parser_config.get("layout_recognize", "DeepDOC"))
    ...
    name = layout_recognizer.strip().lower()
    parser = PARSERS.get(name, by_plaintext)
    sections, tables, pdf_parser = parser(filename, binary, ...)
```

### 2.3 解析后处理：文本合并与分词

**naive_merge()**（[rag/nlp/__init__.py](rag/nlp/__init__.py)）将解析后的 sections 按分隔符切成片再按 token 数量合并：
- 先用分隔符（默认 `\n!?。；！？`）拆分成小段
- 再按 `chunk_token_num`（默认 128/512 Token）合并
- 支持 `overlapped_percent` 重叠

**tokenize_chunks()** 为每个合并后的文本段生成完整的 chunk dict：
```python
# 返回格式:
{
    "id": "xxhash(...)",                    # 唯一 ID
    "content_with_weight": "文本内容",        # 存储+检索用正文
    "docnm_kwd": "文件名",
    "title_tks": "文件名 Token 序列",         # 标题 Token
    "content_ltks": "全文 Token 序列",        # 粗粒度 Token
    "content_sm_ltks": "细粒度 Token 序列",   # 双字切分 Token (中文)
    "important_kwd": [...],                 # 关键词 (LLM 生成)
    "question_kwd": [...],                  # 关联问题 (LLM 生成)
    "image": PIL.Image,                     # 关联图片
    "doc_type_kwd": "text/table/image",     # 内容类型
    "position_int": [...],                  # 位置信息
    "page_num_int": [...],                  # 页码
    "q_768_vec": [...],                     # Embedding 向量
    "mom": "父块文本",                        # 父块引用
    "mom_id": "xxhash(mom)",
    "available_int": 0/1,                   # 是否可检索
}
```

---

## 三、Pipeline 路径详解：可编排 DAG 流程

### 3.1 架构设计

Pipeline 路径复用 Agent 系统的 DAG 执行引擎：

```
Pipeline (rag/flow/pipeline.py)  extends  Graph (agent/canvas.py)
    │
    ├─ __init__(dsl, tenant_id, doc_id):  解析 DSL 构建组件 DAG
    │
    └─ run(**kwargs):  按拓扑序执行组件
         │
         ├─ File          → 获取文件名/存储地址
         ├─ Parser        → 解析文档 (rag/flow/parser/parser.py)
         ├─ TokenChunker  → 文本切片 (rag/flow/chunker/token_chunker.py)
         ├─ Tokenizer     → 分词 + 向量化 (rag/flow/tokenizer/tokenizer.py)
         └─ Extractor     → LLM 增强抽取 (rag/flow/extractor/extractor.py)
```

**Graph 执行引擎核心机制**（`agent/canvas.py`）：
- `Graph.path`：维护当前执行路径
- `get_downstream()`：获取当前组件的下游节点
- 按拓扑序遍历：`idx` 递增 + `path.extend(cpn_obj.get_downstream())`
- 每个组件从上一组件的 `output()` 中读取输入

[Pipeline.run()](rag/flow/pipeline.py#L117) 的核心实现：

```python
async def run(self, **kwargs):
    # 1. 设置日志 key
    REDIS_CONN.set_obj(log_key, [], 60 * 10)

    # 2. 从 File 组件开始
    if not self.path:
        self.path.append("File")
        cpn_obj = self.get_component_obj(self.path[0])
        await cpn_obj.invoke(**kwargs)

    # 3. 按拓扑序遍历
    idx = len(self.path) - 1
    cpn_obj = self.get_component_obj(self.path[idx])
    idx += 1
    self.path.extend(cpn_obj.get_downstream())

    while idx < len(self.path) and not self.error:
        last_cpn = self.get_component_obj(self.path[idx - 1])
        cpn_obj = self.get_component_obj(self.path[idx])
        await cpn_obj.invoke(**last_cpn.output())   # 上游输出 → 下游输入
        idx += 1
        self.path.extend(cpn_obj.get_downstream())

    # 4. 返回最终输出
    return self.get_component_obj(self.path[-1]).output()
```

### 3.2 组件实现细节

#### File 组件（[rag/flow/file.py](rag/flow/file.py)）

最简组件：从数据库或上游获取文件名，输出 `{"name": doc.name}`。

#### Parser 组件（[rag/flow/parser/parser.py](rag/flow/parser/parser.py)）

Pipeline 路径中功能最丰富的组件。支持 13 种文件类型的解析，每种类型独立配置：

```python
class Parser(ProcessBase):
    component_name = "Parser"

    async def _invoke(self, **kwargs):
        # 1. 根据文件后缀匹配 parser 类型
        function_map = {
            "pdf":         self._pdf,
            "markdown":    self._markdown,
            "text&code":   self._code,
            "html":        self._html,
            "spreadsheet": self._spreadsheet,
            "slides":      self._slides,
            "doc":         self._doc,
            "docx":        self._docx,
            "image":       self._image,
            "audio":       self._audio,
            "video":       self._video,
            "email":       self._email,
            "epub":        self._epub,
        }
        ...
        # 2. 从 MinIO/FileService 拉取二进制
        blob = settings.STORAGE_IMPL.get(b, n)
        # 3. 调用对应解析函数
        await thread_pool_exec(function_map[p_type], name, blob, **call_kwargs)
```

**PDF 解析分支**（`_pdf` 方法）是最复杂的部分，展示了多解析器的策略模式：

```
_pdf():
    ├─ deepdoc         → RAGFlowPdfParser.parse_into_bboxes()
    ├─ plain_text      → PlainParser()
    ├─ mineru          → LLMBundle(MinerU).parse_pdf()
    ├─ docling         → DoclingParser.parse_pdf()
    ├─ opendataloader  → OpenDataLoader.parse_pdf()
    ├─ tcadp_parser    → TCADPParser.parse_pdf()
    ├─ paddleocr       → PaddleOCR.parse_pdf()
    └─ VLM (default)   → VisionParser (多模态大模型)
         │
         └─ 输出统一为 bboxes = [{
                "text": "...",
                "layout_type": "text/title/table/figure/...",
                "page_number": 1,
                "x0/x1/top/bottom": ...,
                "image": PIL.Image,      # 截图
                "doc_type_kwd": "text/table/image",
                "positions": [[page, x0, x1, top, bottom], ...]
            }]
```

**输出格式**（可配置 `output_format`）：
- `json`：结构化的 bboxes 列表，保留位置/类型信息 → 供下游 TokenChunker 精确处理
- `markdown`：Markdown 格式文本
- `html`：HTML（仅电子表格）

#### TokenChunker 组件（[rag/flow/chunker/token_chunker.py](rag/flow/chunker/token_chunker.py)）

这是 Pipeline 路径的**切片核心**，展示了更精细的切片策略：

```python
class TokenChunker(ProcessBase):
    component_name = "TokenChunker"

    async def _invoke(self, **kwargs):
        # 1. 从上游获取数据
        from_upstream = TokenChunkerFromUpstream.model_validate(kwargs)

        # 2. 处理三种输入模式 (delimiter_mode):
        #    - "one":        所有内容合并为一个 chunk
        #    - "delimiter":  按分隔符切分 (默认 "\n")
        #    - "token_size": 按 Token 数量合并

        # 3. 结构化 JSON 输入的特殊处理:
        if from_upstream.output_format == "json":
            chunks = _build_json_chunks(json_result, delimiter_pattern)
            #       └─ 将 Parser 输出的 bboxes 转为内部 chunks

            _attach_context_to_media_chunks(chunks, table_ctx, image_ctx)
            #       └─ 为表格/图片 chunk 附加上下文文本

            if not delimiter_pattern:
                chunks = _merge_text_chunks_by_token_size(chunks, size, overlap)
            #       └─ 相邻纯文本 chunk 按 token 预算合并

            cks = _finalize_json_chunks(chunks)
            #       └─ 将内部 chunk 转为最终输出格式
```

**关键设计**：
1. **`_build_json_chunks()`**：将 Parser 输出的 `{"text": ..., "layout_type": "table"}` 转为带 `ck_type` 的内部结构，区分 text/table/image
2. **`_attach_context_to_media_chunks()`**：为表格/图片 chunk 自动附加上下文文本（双向扫描前后 chunk 直到满足 token 预算）
3. **`_merge_text_chunks_by_token_size()`**：仅合并相邻纯文本 chunk，保留表格/图片独立
4. **`_split_chunk_docs_by_children()`**：支持二级分隔符（`children_delimiters`），记录父子关系（`mom` 字段）

#### Tokenizer 组件（[rag/flow/tokenizer/tokenizer.py](rag/flow/tokenizer/tokenizer.py)）

Pipeline 路径的分词 + 向量化：

```python
class Tokenizer(ProcessBase):
    component_name = "Tokenizer"

    async def _invoke(self, **kwargs):
        # 1. "full_text" 模式: 分词
        for i, ck in enumerate(chunks):
            ck["title_tks"] = rag_tokenizer.tokenize(name)
            ck["title_sm_tks"] = rag_tokenizer.fine_grained_tokenize(ck["title_tks"])
            ck["content_ltks"] = rag_tokenizer.tokenize(ck["text"])
            ck["content_sm_ltks"] = rag_tokenizer.fine_grained_tokenize(ck["content_ltks"])

        # 2. "embedding" 模式: 向量化
        if "embedding" in self._param.search_method:
            # 标题向量 + 正文向量加权融合
            vts = embedding_model.encode([name])
            cnts = embedding_model.encode(texts)
            vects = title_w * tts + (1 - title_w) * cnts
            ck["q_768_vec"] = v.tolist()
```

#### Extractor 组件（[rag/flow/extractor/extractor.py](rag/flow/extractor/extractor.py)）

LLM 增强抽取，支持 TOC 生成、关键词提取、问题生成等：

```python
class Extractor(ProcessBase, LLM):  # 多重继承 - 复用 LLM 组件能力
    component_name = "Extractor"

    async def _invoke(self, **kwargs):
        # 对每个 chunk 调用 LLM
        for i, ck in enumerate(chunks):
            msg, sys_prompt = self._sys_prompt_and_msg([], args)
            ck[self._param.field_name] = await self._generate_async(msg)
```

---

## 四、DeepDoc 深度文档理解模块

DeepDoc 是 RAGFlow **最核心的技术壁垒**，位于 [deepdoc/](deepdoc/) 目录：

```
deepdoc/
├── vision/
│   ├── ocr.py                       # OCR 引擎 (PaddleOCR)
│   ├── recognizer.py                # 版面识别 (LayoutRecognition)
│   ├── layout_recognizer.py         # YOLOv10 版面检测
│   └── table_structure_recognizer.py # 表格结构识别 (TSR)
│
├── parser/
│   ├── pdf_parser.py                # PDF 解析核心
│   │   ├── RAGFlowPdfParser         # Pipeline 路径新版解析器
│   │   ├── PlainParser              # 纯文本提取
│   │   └── VisionParser             # VLM 多模态解析
│   ├── docx_parser.py               # DOCX 解析
│   ├── excel_parser.py              # Excel 解析
│   ├── ppt_parser.py                # PPT 解析
│   ├── html_parser.py               # HTML 解析
│   ├── markdown_parser.py           # Markdown 解析
│   ├── figure_parser.py             # 图片描述生成 (VisionFigureParser)
│   ├── mineru_parser.py             # MinerU 集成
│   ├── docling_parser.py            # Docling 集成
│   ├── paddleocr_parser.py          # PaddleOCR 集成
│   ├── tcadp_parser.py              # 腾讯云文档解析集成
│   └── ...
```

### 4.1 PDF 解析核心流程

以 DeepDOC 自研解析器为例（`by_deepdoc` → `Pdf.__call__`，[naive.py:621](rag/app/naive.py#L621)）：

```
Pdf.__call__(filename/binary, from_page, to_page):
    │
    ├─ 1. __images__()
    │      pdfplumber 将 PDF 每页渲染为高分辨率图片 (zoomin=3 → 216 DPI)
    │
    ├─ 2. _layouts_rec(zoomin)
    │      LayoutRecognizer (YOLOv10) 检测 10 种版面元素:
    │      text / title / figure / figure_caption / table /
    │      table_caption / header / footer / reference / equation
    │
    ├─ 3. _table_transformer_job(zoomin)
    │      TableStructureRecognizer 识别表格行列结构
    │
    ├─ 4. _text_merge(zoomin)
    │      OCR 提取文字 + 版面信息融合 → self.boxes
    │
    ├─ 5. _extract_table_figure()
    │      分离表格/图片，生成 HTML 表格或截图
    │
    ├─ 6. _naive_vertical_merge()
    │      垂直方向文本合并
    │
    ├─ 7. _concat_downward()
    │      按阅读顺序排列
    │
    └─ 输出:
        sections = [(text, position_tag), ...]   # 文本块列表
        tables   = [((image, html), pos), ...]   # 表格列表
```

### 4.2 统一数据归一化

所有解析器（不管是 DeepDOC 还是 MinerU/Docling/PaddleOCR）的输出都归一化为统一格式：

**传统路径**中：
```python
sections = [(text, image, table_html), ...]   # 或 (text, position_tag)
tables = [((image, html_content), [(page, x0, x1, top, bottom)]), ...]
```

**Pipeline 路径**中（`Parser._pdf` 方法）：
```python
bboxes = [{
    "text": "段落文本",
    "layout_type": "text",          # 版面类型
    "page_number": 1,               # 页码
    "x0": 100.0, "x1": 500.0,      # 水平坐标
    "top": 200.0, "bottom": 220.0,  # 垂直坐标
    "image": PIL.Image,             # 段落截图（可用于 VLM 增强）
    "positions": [[page, x0,x1,top,bottom], ...],
    "doc_type_kwd": "text",         # 内容分类
}]
```

### 4.3 图片/表格的 VLM 增强

解析出的图片和表格截图可以通过**多模态大模型**生成文字描述（[naive.py:114](rag/app/naive.py#L114)）：

```python
tables = vision_figure_parser_pdf_wrapper(
    tbls=tables,
    sections=sections,
    callback=callback,
    **kwargs,
)
```

`VisionFigureParser` 对每个图片调用 VLM 生成描述文本，增强检索效果。

---

## 五、向量化与检索引擎

### 5.1 向量化策略

传统路径中的 `embedding()` 函数（[task_executor.py:677](rag/svr/task_executor.py#L677)）：

```python
async def embedding(docs, mdl, parser_config=None, callback=None):
    tts, cnts = [], []
    for d in docs:
        tts.append(d.get("docnm_kwd", "Title"))      # 标题
        c = "\n".join(d.get("question_kwd", []))       # LLM 生成的问题
        if not c:
            c = d["content_with_weight"]               # Fallback: 正文
        cnts.append(c)

    # 标题向量 + 正文向量加权融合
    vts, _ = mdl.encode(tts[0:1])
    tts = np.tile(vts[0], (len(cnts), 1))
    vts, _ = mdl.encode(cnts)
    # 最终向量 = title_weight * 标题向量 + (1-title_weight) * 正文向量
    vects = title_w * tts + (1 - title_w) * cnts
```

**设计要点**：
- 标题向量与正文向量加权融合（默认 `filename_embd_weight = 0.1`）
- 优先用 LLM 生成的 `question_kwd` 作为 embedding 输入（问题与查询的语言风格更接近）
- 支持批量编码优化（`EMBEDDING_BATCH_SIZE`）

### 5.2 写入检索引擎

`insert_chunks()`（[task_executor.py:1241](rag/svr/task_executor.py#L1241)）：

```python
async def insert_chunks(task_id, tenant_id, dataset_id, chunks, progress_callback):
    # 1. 处理 mom (父块引用)：生成仅有 meta 字段的 mom chunk
    mothers = [...]
    settings.docStoreConn.insert(mothers, index_name, dataset_id)

    # 2. 批量写入主 chunks
    for b in range(0, len(chunks), DOC_BULK_SIZE):
        settings.docStoreConn.insert(chunks[b : b + DOC_BULK_SIZE], index_name, dataset_id)

        # 3. 同步 chunk_ids 到 Task 记录 (用于取消时的回滚)
        TaskService.update_chunk_ids(task_id, chunk_ids)
```

**索引键设计**（ES Mapping）：
```
chunk_id               # xxhash 生成的唯一 ID
content_with_weight    # 带权重的正文（用于 BM25 检索）
title_tks / content_ltks / content_sm_ltks  # 分词后的 token
important_kwd / important_tks              # LLM 关键词
question_kwd / question_tks                # LLM 问题
q_768_vec / q_1024_vec / ...              # Embedding 向量
doc_id / kb_id                             # 文档/知识库关联
page_num_int / position_int                # 位置信息
doc_type_kwd                               # text/table/image
mom_id                                     # 父 chunk 引用
available_int                              # 是否参与检索 (0=不可检索)
raptor_kwd                                 # RAPTOR 摘要标记
```

---

## 六、LLM 增强层：自动化知识加工

`build_chunks()` 在切片完成后，支持四种并行的 LLM 增强（全部通过 `asyncio.gather` 并发执行）：

### 6.1 auto_keywords（关键词提取）

[task_executor.py:411](rag/svr/task_executor.py#L411)：

```python
if task["parser_config"].get("auto_keywords", 0):
    chat_mdl = LLMBundle(tenant_id, chat_model_config, lang=task["language"])

    async def doc_keyword_extraction(chat_mdl, d, topn):
        # 1. 先查 LLM 缓存 (Redis)
        cached = get_llm_cache(chat_mdl.llm_name, d["content_with_weight"], "keywords", ...)
        if not cached:
            # 2. 调用 LLM 生成关键词
            async with chat_limiter:  # 并发限流
                cached = await keyword_extraction(chat_mdl, d["content_with_weight"], topn)
            # 3. 写入缓存
            set_llm_cache(chat_mdl.llm_name, d["content_with_weight"], cached, "keywords", ...)
        # 4. 分词 + 写入 chunk
        d["important_kwd"] = [k for k in re.split(r"[,，;；、\r\n]+", cached) if k.strip()]
        d["important_tks"] = rag_tokenizer.tokenize(" ".join(d["important_kwd"]))
```

### 6.2 auto_questions（问题生成）

[task_executor.py:448](rag/svr/task_executor.py#L448)：

对每个 chunk 生成 N 个可能被用户问到的关联问题。这些问题的向量会比正文向量更接近实际的查询语句，**显著提升检索命中率**。

### 6.3 enable_metadata（元数据提取）

[task_executor.py:484](rag/svr/task_executor.py#L484)：

用户自定义元数据 schema（JSON Schema 格式），LLM 按 schema 从 chunk 中抽取结构化信息。提取后的元数据合并到文档级 metadata。

### 6.4 content_tagging（内容标签）

[task_executor.py:546](rag/svr/task_executor.py#L546)：

跨知识库的标签体系。先用标签向量做粗筛，再用 LLM 做精细标注：

```python
# 1. 从目标 KB 获取所有标签
all_tags = settings.retriever.all_tags_in_portion(tenant_id, kb_ids, S)

# 2. 向量相似度初筛（匹配到的直接打标）
if settings.retriever.tag_content(tenant_id, kb_ids, d, all_tags, ...):
    examples.append(d)   # 作为 LLM few-shot 示例

# 3. LLM 精细标注（未匹配到的）
cached = await content_tagging(chat_mdl, d["content_with_weight"], all_tags, picked_examples, topn_tags)
```

### 6.5 TOC 生成（目录提取）

[task_executor.py:622](rag/svr/task_executor.py#L622)：

在所有 chunk 入库后，LLM 阅读全文内容生成层级目录结构（TOC），作为一个特殊的 `toc_kwd` chunk 写入。

---

## 七、对企业知识助手的可复用经验

### 7.1 架构设计

| 经验 | RAGFlow 的做法 | 适用场景 |
|------|---------------|----------|
| **两条处理路径共存** | 传统路径（固定流程，简单可靠） + Pipeline 路径（可编排，灵活强大） | 初期用固定流程快速上线，成熟后开放可编排能力 |
| **解析器策略模式** | `PARSERS` 字典 + `layout_recognizer` 配置项实现运行时切换 | 支持多种文档格式和多种解析引擎的任意组合 |
| **DAG 执行引擎复用** | Pipeline 继承 `agent.canvas.Graph`，与 Agent 工作流共享 DAG 引擎 | 将文档处理视为一种特殊的工作流 |
| **Pydantic 数据契约** | 每个 Pipeline 组件使用 `*FromUpstream` schema 校验输入 | 组件间数据传递的类型安全 |
| **异步 + 线程池混合** | API 用 async/await，CPU 密集解析用 `thread_pool_exec` 转到线程池 | 避免阻塞事件循环 |

### 7.2 文档解析

| 经验 | RAGFlow 的做法 | 适用场景 |
|------|---------------|----------|
| **多引擎可插拔** | DeepDOC/MinerU/Docling/PaddleOCR/TCADP 五套引擎可选 | 对精度要求高用自研，对成本敏感用开源/第三方 |
| **统一归一化层** | 所有解析器输出归一化为 `(text, layout_type, positions, image)` | 屏蔽底层差异，下游组件无感知 |
| **视觉 + 文本双通路** | PDF 既做 OCR 又做版面分析又做表格识别 | 复杂排版文档不会丢失结构信息 |
| **VLM 图片增强** | 表格截图/图片通过多模态大模型生成文字描述 | 图表中的信息也能被检索到 |
| **版式元素分类** | 10 种版面类型精确区分，支持去页眉页脚/去目录 | 避免噪音内容进入检索 |

### 7.3 切片策略

| 经验 | RAGFlow 的做法 | 适用场景 |
|------|---------------|----------|
| **多模式切片** | `one` (整体) / `delimiter` (按分隔符) / `token_size` (按 Token) | 不同文档类型适配不同策略 |
| **版面感知切片** | 基于 layout_type 区分 text/table/image，表格和图片不参与文本合并 | 保持表格/图片的完整性 |
| **上下文附加** | 为表格/图片 chunk 自动附加前后文本上下文 | 被检索到的表格/图片有足够信息判断相关性 |
| **二级分隔 + 父子引用** | children_delimiters 切分子块，`mom` 字段记录父块 | 支持精确检索到更小粒度，又能恢复完整上下文 |
| **重叠控制** | `overlapped_percent` 参数控制相邻 chunk 重叠比例 | 避免关键信息在切片边界被截断 |

### 7.4 向量化

| 经验 | RAGFlow 的做法 | 适用场景 |
|------|---------------|----------|
| **标题 + 正文加权融合** | `title_weight * title_vec + (1-title_weight) * content_vec` | 标题信息有助于语义匹配 |
| **问题优先 embedding** | 如果 LLM 生成了 question_kwd，优先用它做 embedding | 问题语句与用户查询更接近 |
| **双粒度分词** | 粗粒度 (word_tokenize) + 细粒度 (双字切分) | 中文混合检索需要 |

### 7.5 LLM 增强

| 经验 | RAGFlow 的做法 | 适用场景 |
|------|---------------|----------|
| **LLM 缓存** | Redis 缓存 LLM 生成结果 (key = llm_name + content + task_type) | 相同内容不重复调用 LLM |
| **并发限流** | `chat_limiter` 信号量控制 LLM 并发调用 | 防止打爆 LLM API |
| **问题生成 > 关键词** | 生成关联问题的检索效果通常优于关键词标注 | Q&A 场景的核心优化 |
| **标签粗筛 + LLM 精标** | 向量相似度完成 80% 标签，LLM 处理 20% 疑难 | 成本与效果的平衡 |

---

## 八、关键文件索引

```
任务调度层:
  rag/svr/task_executor.py          # Worker 主入口，任务调度、build_chunks/embedding/insert_chunks
  rag/svr/task_executor_refactor/   # 新版 Task Executor 重构代码

传统解析路径:
  rag/app/naive.py                  # chunk() 通用解析入口，Pdf/Docx/Markdown 类
  rag/app/paper.py                  # 论文专用解析 (标题/作者/摘要提取)
  rag/app/book.py                   # 书籍专用解析
  rag/app/presentation.py           # PPT 解析
  rag/app/table.py                  # 表格解析
  rag/nlp/__init__.py               # naive_merge/tokenize_chunks/tokenize_table

Pipeline 解析路径:
  rag/flow/pipeline.py              # Pipeline 类 (DAG 执行器)
  rag/flow/base.py                  # ProcessBase 基类
  rag/flow/file.py                  # File 组件
  rag/flow/parser/parser.py         # Parser 组件 (13种文件类型)
  rag/flow/chunker/token_chunker.py # TokenChunker 组件
  rag/flow/tokenizer/tokenizer.py   # Tokenizer 组件
  rag/flow/extractor/extractor.py   # Extractor 组件

DeepDoc 视觉引擎:
  deepdoc/vision/ocr.py             # OCR 引擎
  deepdoc/vision/recognizer.py      # 版面识别
  deepdoc/vision/layout_recognizer.py # YOLOv10 版面检测模型
  deepdoc/vision/table_structure_recognizer.py # 表格结构识别

DeepDoc 解析器:
  deepdoc/parser/pdf_parser.py      # PDF 解析核心
  deepdoc/parser/figure_parser.py   # VisionFigureParser (VLM图片增强)
  deepdoc/parser/docx_parser.py     # DOCX 解析

LLM 增强:
  rag/prompts/generator.py          # keyword_extraction/question_proposal/gen_metadata/run_toc_from_text
  rag/llm/chat_model.py             # Chat 模型工厂 (30+ 提供商)
  rag/llm/embedding_model.py        # Embedding 模型工厂

Agent 系统 (Pipeline 复用的基础设施):
  agent/canvas.py                   # Graph DAG 执行引擎
  agent/component/base.py           # ComponentBase 基类
  agent/component/llm.py            # LLM 组件 (Extractor 复用了它)
```

---

## 九、总结

RAGFlow 的文档处理模块展示了一套**生产级 RAG 文档管道的完整设计思路**：

1. **分层解耦**：任务调度 → 解析 → 切片 → 分词 → 向量化 → 入库，每层独立演进
2. **策略模式**：同一种文件类型支持多种解析引擎（DeepDOC/MinerU/Docling/...），运行时切换
3. **归一化中间层**：所有解析器输出统一为 `bboxes` / `sections` 格式，下游统一消费
4. **两条腿走路**：固定流程（简单可靠）和可编排管道（灵活强大）共存，适应不同场景
5. **LLM 锦上添花**：关键词/问题/元数据/标签/TOC 五大 LLM 增强，全部可选、可并发、可缓存
6. **视觉不可丢弃**：DeepDoc 的版面分析 + 表格识别 + VLM 图片描述，确保非文本信息不被遗漏

这些设计模式可以直接应用于企业知识助手的文档处理链路建设中。
