"""Embedding 调用封装。对 BaseEmbedding 的薄封装，增加批量拆分和重试逻辑。"""

from common import get_logger
from llm import BaseEmbedding

logger = get_logger(__name__)


class EmbeddingWrapper:
    """对 BaseEmbedding 的薄封装，增加批量拆分和自动重试。

    使用场景：
    - ETL 管道批量向量化文档 Chunk
    - API 路由单条查询向量化
    """

    def __init__(self, embedding: BaseEmbedding, batch_size: int = 100):
        """
        Args:
            embedding: BaseEmbedding 实例
            batch_size: 批量向量化时每批最大文本数
        """
        self._embedding = embedding
        self._batch_size = batch_size
        self._max_retries = 1

    async def embed_chunks(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，自动按 batch_size 拆分，避免单次请求过大。

        Args:
            texts: 文本列表

        Returns:
            向量列表
        """
        if not texts:
            return []

        all_vectors = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            vectors = await self._embed_documents_with_retry(batch)
            all_vectors.extend(vectors)
            logger.debug(f"批量向量化: {i + len(batch)}/{len(texts)} 条完成")

        return all_vectors

    async def embed_query(self, query: str) -> list[float]:
        """查询向量化，带一次重试。

        Args:
            query: 查询文本

        Returns:
            向量
        """
        for attempt in range(self._max_retries + 1):
            try:
                return await self._embedding.embed_query(query)
            except Exception as e:
                if attempt < self._max_retries:
                    logger.warning(f"查询向量化失败(第{attempt+1}次)，重试中: {e}")
                else:
                    raise

        raise RuntimeError("不可达")  # 安抚类型检查器

    async def _embed_documents_with_retry(self, texts: list[str]) -> list[list[float]]:
        """批量向量化（内部），带自动重试。"""
        for attempt in range(self._max_retries + 1):
            try:
                return await self._embedding.embed_documents(texts)
            except Exception as e:
                if attempt < self._max_retries:
                    logger.warning(f"批量向量化失败(第{attempt+1}次)，重试中: {e}")
                else:
                    raise

        raise RuntimeError("不可达")
