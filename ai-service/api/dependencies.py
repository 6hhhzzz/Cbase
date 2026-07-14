"""FastAPI 依赖注入模块。

声明式 Depends 函数，替代路由中手动的 ``req.app.state.xxx`` 访问。
——————————————————————————————————————————————————
路由直接声明需要的依赖类型即可，例如::

    @router.post("/v1/chat")
    async def chat(
        request: ChatRequest,
        llm: BaseLLM = Depends(get_llm),
        pgvector: PGVectorClient = Depends(get_pgvector_client),
    ):
        ...

使用 Python 3.10+ 可以用 Annotated 简写::

    async def chat(request: ChatRequest, llm: LLMDep, pgvector: PGVDep):
"""

from fastapi import Request

# -- LLM / Embedding --
from llm.base import BaseLLM, BaseEmbedding

# -- Retrieval --
from retrieval.embedding import EmbeddingWrapper
from retrieval.vector_store import PGVectorClient

# -- Context --
from core.context.history_manager import HistoryManager
from core.context.context_assembler import ContextAssembler
from core.context.summary_engine import SummaryEngine

# -- MQ --
from mq.client import MQClient


def _get_from_state(key: str, request: Request):
    """通用：从 app.state 获取指定 key 的依赖。"""
    return getattr(request.app.state, key)


# ================================================================
# 单独 get_ 函数
# ================================================================

def get_llm(request: Request) -> BaseLLM:
    return _get_from_state("llm", request)


def get_embedding(request: Request) -> BaseEmbedding:
    return _get_from_state("embedding", request)


def get_embedding_wrapper(request: Request) -> EmbeddingWrapper:
    return _get_from_state("embedding_wrapper", request)


def get_pgvector_client(request: Request) -> PGVectorClient:
    return _get_from_state("pgvector_client", request)


def get_history_manager(request: Request) -> HistoryManager:
    return _get_from_state("history_manager", request)


def get_context_assembler(request: Request) -> ContextAssembler:
    return _get_from_state("context_assembler", request)


def get_summary_engine(request: Request) -> SummaryEngine:
    return _get_from_state("summary_engine", request)


def get_mq_client(request: Request) -> MQClient:
    return _get_from_state("mq_client", request)
