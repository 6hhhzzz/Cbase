"""PostgreSQL + pgvector 向量数据库客户端。v3 Space/KB 权限模型。

使用 asyncpg 连接池 + pgvector 扩展进行向量相似度搜索。
所有检索操作强制预过滤权限（使用 Java 传入的 kb_ids 列表）。
"""

from datetime import date
from uuid import UUID

import asyncpg
from pgvector.asyncpg import register_vector
from pgvector.utils import Vector

from common import get_logger
from common.utils import current_timestamp_ms, generate_chunk_id, tokenize_chinese
from llm import BaseEmbedding
from models.config import PGVectorConfig
from models.document import DocumentChunk
from models.retrieval import SearchRequest, SearchResult

logger = get_logger(__name__)


def _parse_date(value: str | None) -> date | None:
    """将 YYYY-MM-DD 字符串转为 datetime.date，asyncpg 需要 date 对象。"""
    if value is None:
        return None
    return date.fromisoformat(value)


class PGVectorClient:
    """PostgreSQL + pgvector 向量存储客户端。v3 用 kb_id 作为唯一权限过滤字段。

    负责：
    - 连接池管理
    - knowledge_chunks 表创建和索引管理
    - 文档 Chunk 批量写入
    - 向量检索 + kb_id 权限过滤
    - 按 doc_id 删除关联 Chunk
    """

    def __init__(self, config: PGVectorConfig, embedding: BaseEmbedding):
        self._config = config
        self._embedding = embedding
        self._pool: asyncpg.Pool | None = None
        self._connected = False

    @property
    def pool(self) -> asyncpg.Pool | None:
        """暴露连接池供 SparseRetriever 等组件复用。"""
        return self._pool

    # ---- 连接管理 ----

    async def ensure_collection(self) -> None:
        """连接 PostgreSQL，注册 pgvector，确保 knowledge_chunks 表和索引存在。"""
        try:
            self._pool = await asyncpg.create_pool(
                host=self._config.host,
                port=self._config.port,
                user=self._config.user,
                password=self._config.password,
                database=self._config.database,
                min_size=self._config.min_pool_size,
                max_size=self._config.max_pool_size,
            )

            async with self._pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await register_vector(conn)

                # v3 建表：kb_id 是唯一权限字段
                dim = self._config.dimension
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS knowledge_chunks (
                        id                  VARCHAR(64)   PRIMARY KEY,
                        doc_id              VARCHAR(64)   NOT NULL,
                        chunk_index         INTEGER       NOT NULL,
                        chunk_text          TEXT          NOT NULL,
                        embedding           VECTOR({dim})  NOT NULL,
                        kb_id               VARCHAR(64)   NOT NULL,
                        status              VARCHAR(16)   NOT NULL DEFAULT 'active',
                        source_file         VARCHAR(512)  NOT NULL DEFAULT '',
                        doc_effective_date  DATE,
                        doc_expiry_date     DATE,
                        doc_version         VARCHAR(64),
                        content_with_weight TEXT          NOT NULL DEFAULT '',
                        created_at          BIGINT        NOT NULL
                    )
                """)

                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_kc_doc_id ON knowledge_chunks(doc_id)"
                )
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_kc_kb ON knowledge_chunks(kb_id)"
                )

                # 向量索引：优先 HNSW，失败降级 IVFFlat
                try:
                    await conn.execute("SET maintenance_work_mem = '256MB'")
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_kc_embedding_hnsw
                        ON knowledge_chunks
                        USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64)
                    """)
                except Exception:
                    logger.warning("HNSW 索引创建失败，降级使用 IVFFlat")
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_kc_embedding
                        ON knowledge_chunks
                        USING IVFFLAT (embedding vector_cosine_ops)
                        WITH (lists = 1024)
                    """)

            self._connected = True
            logger.info(
                f"PostgreSQL+pgvector(v3) 连接成功: "
                f"host={self._config.host}:{self._config.port}, db={self._config.database}"
            )

        except Exception as e:
            logger.error(f"PostgreSQL+pgvector 连接失败: {e}")
            raise

    async def ping(self) -> bool:
        """检查 PostgreSQL 连通性。"""
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    # ---- 数据写入 ----

    async def insert_chunks(self, chunks: list[DocumentChunk],
                             vectors: list[list[float]] | None = None) -> int:
        """批量写入 Chunk + 可选的预计算向量。

        Args:
            chunks:  待写入的文档块列表
            vectors: 预计算的向量列表（与 chunks 一一对应），为 None 时内部调用 embedding

        Returns:
            成功写入的 chunk 数量
        """
        if not chunks:
            return 0

        # 向量化：优先使用传入的预计算向量
        if vectors is not None and len(vectors) == len(chunks):
            pass
        else:
            texts = [c.chunk_text for c in chunks]
            batch_size = 8
            vectors = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_vectors = await self._embedding.embed_documents(batch)
                vectors.extend(batch_vectors)
                logger.debug(f"向量化 {i + len(batch)}/{len(texts)} 条")

        # 构建批量插入数据（v5: 含 content_with_weight，fts 由触发器自动生成）
        rows = []
        for i, chunk in enumerate(chunks):
            meta = chunk.metadata
            # content_with_weight 优先取 metadata 中的，否则用 chunk_text
            cw = meta.get("content_with_weight", chunk.chunk_text)
            rows.append((
                generate_chunk_id(str(chunk.doc_id), chunk.chunk_index),
                str(chunk.doc_id),
                chunk.chunk_index,
                chunk.chunk_text,
                Vector(vectors[i]),
                meta.get("kb_id", ""),
                meta.get("source_file", ""),
                _parse_date(meta.get("effective_date")),
                _parse_date(meta.get("expiry_date")),
                meta.get("version"),
                cw,
                current_timestamp_ms(),
                tokenize_chinese(cw),  # fts: jieba 分词后由 to_tsvector 索引
            ))

        async with self._pool.acquire() as conn:
            await register_vector(conn)
            await conn.executemany("""
                INSERT INTO knowledge_chunks
                    (id, doc_id, chunk_index, chunk_text, embedding,
                     kb_id, status, source_file,
                     doc_effective_date, doc_expiry_date, doc_version,
                     content_with_weight, created_at, fts)
                VALUES ($1, $2, $3, $4, $5::vector,
                        $6, 'active', $7, $8, $9, $10,
                        $11, $12, to_tsvector('simple', $13))
                ON CONFLICT (id) DO NOTHING
            """, rows)

        logger.info(f"成功写入 {len(chunks)} 个 chunks 到 PostgreSQL")
        return len(chunks)

    # ---- 检索 ----

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        """向量检索 + kb_id 权限过滤。

        Java 传入 kb_ids 列表，Python 机械构建 WHERE kb_id = ANY($2)，不作权限判断。
        所有参数使用 asyncpg 参数化占位符，防止 SQL 注入。
        """
        async with self._pool.acquire() as conn:
            await register_vector(conn)

            kb_ids = request.filter_params.kb_ids
            doc_ids = request.filter_params.doc_ids
            query_vec = Vector(request.query_vector)

            rows = await conn.fetch("""
                SELECT doc_id, chunk_index, chunk_text, source_file, embedding,
                       1 - (embedding <=> $1::vector) AS score
                FROM knowledge_chunks
                WHERE kb_id = ANY($2)
                  AND status = 'active'
                  AND ($4::text[] IS NULL OR doc_id != ALL($4))
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """, query_vec, kb_ids, request.top_k, doc_ids)

            results = []
            for row in rows:
                # 提取向量以便 CitationInserter 使用
                emb = None
                if row["embedding"] is not None:
                    try:
                        emb = [float(v) for v in row["embedding"]]
                    except (TypeError, ValueError):
                        pass
                results.append(SearchResult(
                    doc_id=UUID(row["doc_id"]),
                    chunk_index=row["chunk_index"],
                    chunk_text=row["chunk_text"],
                    source_file=row["source_file"],
                    score=float(row["score"]),
                    metadata={"_embedding": emb} if emb else {},
                ))

            logger.info(
                f"检索完成: kb_ids={kb_ids}, doc_ids={doc_ids}, "
                f"top_k={request.top_k}, 命中={len(results)}"
            )
            return results

    # ---- 删除 ----

    async def delete_by_doc_id(self, doc_id: UUID) -> int:
        """按 doc_id 删除所有关联 Chunk。"""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM knowledge_chunks WHERE doc_id = $1",
                str(doc_id),
            )
            count = int(result.split()[1]) if result.startswith("DELETE") else 0
            logger.info(f"已删除 doc_id={doc_id} 的 {count} 个 chunks")
            return count

    async def update_chunk_status(self, doc_id: str, status: str) -> int:
        """批量更新某文档所有 chunks 的状态。
        - soft_deleted: 标记为不可检索
        - active: 恢复为可检索
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE knowledge_chunks SET status = $1 WHERE doc_id = $2",
                status, doc_id,
            )
            count = int(result.split()[1]) if result.startswith("UPDATE") else 0
            logger.info(f"已更新 chunks 状态: doc_id={doc_id}, status={status}, count={count}")
            return count
