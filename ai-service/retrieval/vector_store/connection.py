"""PG 连接管理 — asyncpg 连接池 + DDL + 索引管理。"""

import asyncpg
from pgvector.asyncpg import register_vector

from common import get_logger
from models.config import PGVectorConfig

logger = get_logger(__name__)


class PGConnectionManager:
    """PostgreSQL + pgvector 连接管理器。

    负责：连接池创建、pgvector 扩展注册、knowledge_chunks 表和索引创建。
    """

    def __init__(self, config: PGVectorConfig):
        self._config = config
        self._pool: asyncpg.Pool | None = None

    @property
    def pool(self) -> asyncpg.Pool | None:
        """暴露连接池供其他组件复用。"""
        return self._pool

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
                        metadata            JSONB         DEFAULT '{{}}',
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
