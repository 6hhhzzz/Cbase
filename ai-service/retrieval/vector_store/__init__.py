"""PostgreSQL + pgvector 向量数据库客户端。

已重构为 vector_store/ 子包（connection / search / repository）。
"""

from llm import BaseEmbedding
from models.config import PGVectorConfig
from models.document import DocumentChunk
from models.retrieval import SearchRequest, SearchResult

from .connection import PGConnectionManager
from .search import search as _search
from .repository import insert_chunks as _insert_chunks
from .repository import delete_by_doc_id as _delete_by_doc_id
from .repository import update_chunk_status as _update_chunk_status


class PGVectorClient:
    """PostgreSQL + pgvector 向量存储客户端（组合 facade）。

    委托给 connection / search / repository 子模块。
    """

    def __init__(self, config: PGVectorConfig, embedding: BaseEmbedding):
        self._config = config
        self._embedding = embedding
        self._conn = PGConnectionManager(config)

    @property
    def pool(self):
        """暴露连接池供 SparseRetriever 等组件复用。"""
        return self._conn.pool

    async def ensure_collection(self) -> None:
        """连接 PostgreSQL，确保表/索引存在。"""
        await self._conn.ensure_collection()

    async def ping(self) -> bool:
        """检查 PostgreSQL 连通性。"""
        return await self._conn.ping()

    async def insert_chunks(
        self, chunks: list[DocumentChunk],
        vectors: list[list[float]] | None = None,
    ) -> int:
        """批量写入 Chunk。"""
        return await _insert_chunks(chunks, self._conn.pool, self._embedding, vectors)

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        """向量检索 + kb_id 权限过滤。"""
        return await _search(request, self._conn.pool)

    async def delete_by_doc_id(self, doc_id) -> int:
        """按 doc_id 删除所有关联 Chunk。"""
        return await _delete_by_doc_id(doc_id, self._conn.pool)

    async def update_chunk_status(self, doc_id: str, status: str) -> int:
        """批量更新某文档所有 chunks 的状态。"""
        return await _update_chunk_status(doc_id, status, self._conn.pool)
