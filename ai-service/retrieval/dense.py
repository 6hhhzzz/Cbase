"""DenseRetriever — 稠密向量检索（HNSW 余弦相似度）。"""

from common import get_logger
from llm import BaseEmbedding
from .vector_store import PGVectorClient
from .models import ScoredChunk

logger = get_logger(__name__)


class DenseRetriever:
    """稠密向量检索器。

    封装 PGVectorClient 的向量搜索，返回统一的 ScoredChunk。
    """

    def __init__(self, pgvector: PGVectorClient, embedding: BaseEmbedding):
        self._pgvector = pgvector
        self._embedding = embedding

    async def search(
        self,
        query: str,
        kb_ids: list[str],
        top_k: int = 30,
        excluded_doc_ids: list[str] | None = None,
    ) -> list[ScoredChunk]:
        """执行稠密向量检索。

        Args:
            query: 用户查询文本
            kb_ids: 有权访问的知识库 ID 列表
            top_k: 返回结果数
            excluded_doc_ids: 排除的文档 ID 列表

        Returns:
            ScoredChunk 列表，按 cosine 相似度降序
        """
        if not query.strip():
            return []

        # 嵌入查询
        query_vec = await self._embedding.embed_query(query)

        # 调用 pgvector 搜索
        from models.retrieval import SearchRequest, FilterParams
        request = SearchRequest(
            query_vector=query_vec,
            filter_params=FilterParams(kb_ids=kb_ids, doc_ids=excluded_doc_ids),
            top_k=top_k,
        )
        results = await self._pgvector.search(request)

        # 转换为 ScoredChunk
        chunks = []
        for r in results:
            chunks.append(ScoredChunk(
                chunk_id=str(r.doc_id),
                content=r.chunk_text,
                score=r.score,
                source_file=r.source_file,
                metadata=r.metadata,
            ))

        logger.debug(f"DenseRetriever: query='{query[:50]}...', top_k={top_k}, hits={len(chunks)}")
        return chunks
