"""pgvector 索引写入步骤。"""

from common import get_logger
from .base import PipelineStep

logger = get_logger(__name__)


class IndexStep(PipelineStep):
    """将文档块写入 pgvector。"""

    def __init__(self, pgvector_client):
        self._pgvector = pgvector_client

    async def execute(self, ctx: dict) -> dict:
        chunks = ctx["chunks"]
        vectors = ctx.get("vectors")  # 由 EmbedStep 预计算
        inserted = await self._pgvector.insert_chunks(chunks, vectors)
        ctx["inserted_count"] = inserted
        logger.info(f"pgvector 写入完成: doc_id={ctx['msg'].doc_id}, chunks={inserted}")
        return ctx
