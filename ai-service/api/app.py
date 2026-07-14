"""FastAPI 应用入口。

在 lifespan 中完成所有依赖的创建和注入：
    - 加载配置 → 创建 LLM / Embedding 实例
    - 创建 PGVectorClient、HistoryManager、SummaryEngine、ContextAssembler
    - 创建 MQClient + ETLPipeline，启动文档入库消息消费

启动命令:
    uv run uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from common import get_logger, setup_logging
from common.exceptions import AppException
from core.config import load_settings
from core.context import ContextAssembler, HistoryManager, SummaryEngine
from etl import ETLPipeline
from etl.sanitizers.presidio_sanitizer import PresidioSanitizer
from etl.steps import DownloadStep, SanitizeStep, EmbedStep, IndexStep
from etl.steps import ParseStepV5, ChunkStepV5
from etl.steps.doc_understand_step import DocUnderstandStep
from etl.steps.doc_classify_step import DocClassifyStep
from etl.steps.kb_summary_step import UpdateKBSummaryStep
from parsing.orchestrator import ParseOrchestrator
from parsing.registry import ParserRegistry as NewParserRegistry
from chunking.orchestrator import ChunkOrchestrator
from llm.factory import ModelFactory
from llm.model_pool import ModelPool
from minio import Minio
from mq.client import MQClient
from retrieval import EmbeddingWrapper, PGVectorClient
from retrieval.reranker import create_reranker
from retrieval.dense import DenseRetriever
from retrieval.sparse import SparseRetriever
from retrieval.fusion import Fusion
from retrieval.hybrid_search import HybridSearch
from retrieval.query_rewriter import QueryRewriter
from retrieval.query_planner import QueryPlanner
from retrieval.query_preprocessor import QueryPreprocessor
from retrieval.citation import CitationInserter
from retrieval.orchestrator import RetrievalOrchestrator
from retrieval.feedback import RetrievalTracer
from retrieval.judge import JudgeEvaluator

from .chat import router as chat_router
from .documents import router as documents_router
from .health import router as health_router
from .admin_models import router as admin_models_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时创建所有服务实例，关闭时清理资源。"""
    # ========== 启动阶段 ==========
    setup_logging()
    logger.info("AI Service 启动中...")

    # 加载配置
    settings = load_settings()
    logger.info(f"配置加载完成: LLM model={settings.llm.model}")

    # ---- v12: 动态模型池（优先 models.yaml，降级 Java HTTP，兜底 llm.yaml）----
    java_url = os.environ.get("KES_JAVA_URL", "")
    model_pool = ModelPool(java_base_url=java_url)
    slm = None  # SLM 可能在 fallback 中未创建
    try:
        await model_pool.initialize()
        llm = model_pool.get_llm("chat")
        slm = model_pool.get_slm()
        llm_rewrite = model_pool.get_llm("rewrite")
        llm_planner = model_pool.get_llm("planner")
        embedding = model_pool.get_embedding()
        logger.info(f"ModelPool 加载成功: chat={llm.get_model_name()}, "
                     f"slm={slm.get_model_name() if slm else 'N/A'}, "
                     f"embedding_dim={model_pool.embedding_dimension}")
        watch_interval = int(os.environ.get("KES_MODEL_WATCH_INTERVAL", "30"))
        await model_pool.start_watch(watch_interval)
    except Exception as e:
        logger.warning(f"ModelPool 加载失败 ({e})，降级使用 llm.yaml 配置")
        llm = ModelFactory.create_llm(settings.llm)
        embedding = ModelFactory.create_embedding(settings.embedding)
        # 所有特殊环节降级复用主 LLM
        from llm.factory import ModelFactory as MF
        try:
            slm = MF.create_llm(settings.llm)
        except Exception:
            slm = llm
        llm_rewrite = llm
        llm_planner = llm

    logger.info(f"LLM 实例: {llm.get_model_name()}, "
                f"SLM 实例: {slm.get_model_name() if slm else 'N/A'}, "
                f"Embedding 维度: {embedding.get_dimension()}")

    # 创建 Embedding 封装（批量拆分 + 重试）
    embedding_wrapper = EmbeddingWrapper(embedding)

    # 创建 PGVector 客户端并初始化表
    pgvector_client = PGVectorClient(settings.pgvector, embedding)
    try:
        await pgvector_client.ensure_collection()
        logger.info("PostgreSQL+pgvector 连接成功")
    except Exception as e:
        logger.warning(f"PostgreSQL+pgvector 连接失败（服务仍可启动，检索功能不可用）: {e}")

    # 创建上下文管理组件（仅 Redis 缓存，不连接业务数据库）
    history_manager = HistoryManager(settings.redis)
    await history_manager.initialize()
    logger.info("HistoryManager 初始化完成（仅 Redis）")

    summary_engine = SummaryEngine(
        llm, history_manager,
        soft_limit=settings.summary.soft_limit,
        compress_target=settings.summary.compress_target,
        trigger_rounds=settings.summary.trigger_rounds,
        max_failures=settings.summary.max_failures,
    )
    context_assembler = ContextAssembler(history_manager)

    # 创建 Reranker（从 models.yaml 配置中心获取: DashScope API → 本地 Cross-Encoder → LLM 降级）
    reranker = model_pool.get_reranker()
    if reranker is None:
        logger.warning("ModelPool 未配置 Reranker，降级使用 create_reranker")
        reranker = create_reranker(llm=llm)

    # ---- v5: 新建混合检索引擎组件 ----
    # SparseRetriever 复用 PGVector 连接池
    sparse_retriever = SparseRetriever(pgvector_client.pool) if pgvector_client.pool else None
    dense_retriever = DenseRetriever(pgvector_client, embedding)
    fusion = Fusion()
    hybrid_search = HybridSearch(dense_retriever, sparse_retriever, fusion) if sparse_retriever else None
    # v12: 各环节独立 LLM 注入（前端可分别配置）
    query_preprocessor = QueryPreprocessor(slm) if slm else None
    query_rewriter = QueryRewriter(llm_rewrite)
    query_planner = QueryPlanner(llm_planner)
    citation = CitationInserter(embedding)
    retrieval_orchestrator = RetrievalOrchestrator(
        hybrid_search=hybrid_search,
        reranker=reranker,
        llm=llm,
        embedding=embedding,
        rewriter=query_rewriter,
        query_planner=query_planner,
        query_preprocessor=query_preprocessor,
        citation=citation,
    ) if hybrid_search else None
    logger.info("v5 混合检索引擎组件已创建" if retrieval_orchestrator else "v5 混合检索未启用（缺少连接池）")

    # ---- v12: 检索质量反馈追踪 + Judge 评估器 ----
    tracer = RetrievalTracer(pool=pgvector_client.pool) if pgvector_client.pool else None
    judge = JudgeEvaluator(slm) if slm else None
    logger.info("检索质量追踪组件已创建" if tracer else "检索质量追踪未启用（缺少连接池）")

    # ---- v8: MCP 知识服务组件注入 ----
    if retrieval_orchestrator:
        from kes_mcp.server import init_components
        init_components(retrieval_orchestrator, context_assembler, llm, embedding)
        logger.info("MCP Server 组件已注入")

    # ---- v5 ETL 管道组件（使用新 parsing/ + chunking/） ----
    parse_orchestrator = ParseOrchestrator(NewParserRegistry())
    chunk_orchestrator = ChunkOrchestrator()
    sanitizer = PresidioSanitizer()

    # 创建 MinIO 客户端
    minio_client = Minio(
        endpoint=settings.minio.endpoint,
        access_key=settings.minio.access_key,
        secret_key=settings.minio.secret_key,
        secure=settings.minio.secure,
    )
    logger.info(f"MinIO 客户端就绪: endpoint={settings.minio.endpoint}, bucket={settings.minio.bucket}")

    # v5 ETL 步骤链：新解析 + 脱敏 + 新分块 + 嵌入 + 索引
    steps = [
        DownloadStep(minio_client, settings.minio.bucket),
        ParseStepV5(parse_orchestrator),
        SanitizeStep(sanitizer, security_level=2),
        ChunkStepV5(chunk_orchestrator),
        DocUnderstandStep(slm=slm),
        DocClassifyStep(slm=slm),
        EmbedStep(embedding_wrapper),
        IndexStep(pgvector_client),
        UpdateKBSummaryStep(),
    ]
    etl_pipeline = ETLPipeline(steps)

    # 创建 MQClient 并启动文档入库消费
    mq_client = MQClient(settings.rabbitmq)
    _mq_task: asyncio.Task | None = None
    try:
        await mq_client.connect()
        if mq_client._connected:
            _mq_task = asyncio.create_task(mq_client.consume_ingest(etl_pipeline))
            logger.info("MQ 文档入库消费已启动")
    except Exception as e:
        logger.warning(f"MQ 连接失败，文档入库功能不可用: {e}")

    # 注入到 app.state，供路由通过 Request.app.state 访问
    app.state.llm = llm
    app.state.embedding = embedding
    app.state.embedding_wrapper = embedding_wrapper
    app.state.pgvector_client = pgvector_client
    app.state.history_manager = history_manager
    app.state.summary_engine = summary_engine
    app.state.context_assembler = context_assembler
    app.state.reranker = reranker
    app.state.retrieval_orchestrator = retrieval_orchestrator
    app.state.tracer = tracer
    app.state.judge = judge
    app.state.mq_client = mq_client
    app.state.settings = settings

    logger.info("AI Service 启动完成，等待请求...")
    yield

    # ========== 关闭阶段 ==========
    logger.info("AI Service 关闭中...")
    if _mq_task is not None:
        _mq_task.cancel()
        try:
            await _mq_task
        except asyncio.CancelledError:
            pass
    await mq_client.close()
    await history_manager.close()
    logger.info("AI Service 已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="企业知识助手 AI Service",
    version="1.0.0",
    description="Python AI Service — RAG 问答与文档入库",
    lifespan=lifespan,
)

# 注册路由
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(health_router)
app.include_router(admin_models_router)


# ---- 全局异常处理 ----

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 校验失败 → 400（而非默认的 422）。

    对应《核心接口契约文档》§8 关键验证规则。
    """
    errors = exc.errors()
    messages = [f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors]
    return JSONResponse(
        status_code=400,
        content={
            "error": "validation_error",
            "message": "; ".join(messages),
        },
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """将 AppException 子类转换为统一的 JSON 错误响应，格式与 Java 端对齐。

    响应: {"code": <http_status>, "error_code": "DOC_NOT_FOUND", "message": "..."}
    """
    # 根据 error_code 前缀推断 HTTP 状态码
    code = exc.error_code or ""
    if "MISSING" in code or "INVALID" in code or "UNSUPPORTED" in code:
        http_status = 400
    elif "AUTH" in code:
        http_status = 401
    elif "ACCESS_DENIED" in code:
        http_status = 403
    elif "NOT_FOUND" in code:
        http_status = 404
    elif "SERVICE_UNAVAILABLE" in code:
        http_status = 503
    elif "INGEST" in code or "INTERNAL" in code:
        http_status = 500
    else:
        http_status = 500
    return JSONResponse(
        status_code=http_status,
        content={
            "code": http_status,
            "error_code": exc.error_code,
            "message": exc.message,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """兜底异常处理，避免堆栈信息泄露到客户端。"""
    logger.error(f"未捕获的异常: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "error_code": "INTERNAL_ERROR",
            "message": "服务器内部错误",
        },
    )
