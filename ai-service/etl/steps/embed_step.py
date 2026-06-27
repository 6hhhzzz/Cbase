"""Embedding 向量化步骤。"""

from common import get_logger
from retrieval.embedding import EmbeddingWrapper
from .base import PipelineStep

logger = get_logger(__name__)


class EmbedStep(PipelineStep):
    """对文档块文本进行向量化，将向量存入 ctx。"""

    def __init__(self, embedding_wrapper: EmbeddingWrapper, batch_size: int = 100):
        self._embedding = embedding_wrapper
        self._batch_size = batch_size

    async def execute(self, ctx: dict) -> dict:
        chunks = ctx["chunks"]
        texts = [c.chunk_text for c in chunks]

        vectors = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            batch_vectors = await self._embedding.embed_chunks(batch)
            vectors.extend(batch_vectors)

        ctx["vectors"] = vectors
        logger.info(f"向量化完成: doc_id={ctx['msg'].doc_id}, count={len(vectors)}")
        return ctx
