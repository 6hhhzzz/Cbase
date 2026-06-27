"""GET /v1/health — 健康检查接口。

检查 pgvector、LLM、Embedding、RabbitMQ 各组件的连通性。
"""

from fastapi import APIRouter, Depends

from common import get_logger
from llm.base import BaseLLM, BaseEmbedding
from models.health import HealthResponse
from mq.client import MQClient
from retrieval.vector_store import PGVectorClient
from .dependencies import (
    get_llm, get_embedding, get_pgvector_client, get_mq_client,
)

logger = get_logger(__name__)

router = APIRouter()


@router.get("/v1/health", response_model=HealthResponse)
async def health(
    pgvector_client: PGVectorClient = Depends(get_pgvector_client),
    llm: BaseLLM = Depends(get_llm),
    embedding: BaseEmbedding = Depends(get_embedding),
    mq_client: MQClient = Depends(get_mq_client),
):
    """检查各组件连通性，返回整体和组件级状态。"""

    components = {}
    overall = "healthy"

    # pgvector (PostgreSQL)
    try:
        if await pgvector_client.ping():
            components["pgvector"] = "healthy"
        else:
            components["pgvector"] = "unhealthy"
            overall = "degraded"
    except Exception as e:
        logger.warning(f"pgvector 健康检查失败: {e}")
        components["pgvector"] = "unhealthy"
        overall = "degraded"

    # LLM — 发送最小 ping 请求
    try:
        await llm.generate_content("ping", max_tokens=1)
        components["llm"] = "healthy"
    except Exception as e:
        logger.warning(f"LLM 健康检查失败: {e}")
        components["llm"] = "unhealthy"
        overall = "degraded"

    # Embedding
    try:
        await embedding.embed_query("ping")
        components["embedding"] = "healthy"
    except Exception as e:
        logger.warning(f"Embedding 健康检查失败: {e}")
        components["embedding"] = "unhealthy"
        overall = "degraded"

    # RabbitMQ
    try:
        if mq_client and await mq_client.ping():
            components["rabbitmq"] = "healthy"
        else:
            components["rabbitmq"] = "unhealthy"
            overall = "degraded"
    except Exception as e:
        logger.warning(f"RabbitMQ 健康检查失败: {e}")
        components["rabbitmq"] = "unhealthy"
        overall = "degraded"

    return HealthResponse(status=overall, components=components)
