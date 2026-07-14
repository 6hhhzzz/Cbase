"""向量检索服务 — pgvector HNSW 向量相似度搜索 + kb_id 权限过滤。"""

import json
from datetime import date
from uuid import UUID

from pgvector.asyncpg import register_vector
from pgvector.utils import Vector

from common import get_logger
from models.retrieval import SearchRequest, SearchResult

logger = get_logger(__name__)


async def search(request: SearchRequest, pool) -> list[SearchResult]:
    """向量检索 + kb_id 权限过滤。

    Java 传入 kb_ids 列表，Python 机械构建 WHERE kb_id = ANY($2)，不作权限判断。
    所有参数使用 asyncpg 参数化占位符，防止 SQL 注入。
    """
    async with pool.acquire() as conn:
        await register_vector(conn)

        kb_ids = request.filter_params.kb_ids
        doc_ids = request.filter_params.doc_ids
        query_vec = Vector(request.query_vector)

        rows = await conn.fetch("""
            SELECT id, doc_id, chunk_index, chunk_text, source_file, embedding,
                   doc_effective_date, doc_expiry_date, doc_version, created_at,
                   metadata,
                   1 - (embedding <=> $1::vector) AS score
            FROM knowledge_chunks
            WHERE kb_id = ANY($2)
              AND status = 'active'
              AND ($4::text[] IS NULL OR doc_id != ALL($4))
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """, query_vec, kb_ids, request.top_k, doc_ids)

        results = []
        today = date.today().isoformat()
        for row in rows:
            # 提取向量以便 CitationInserter 使用
            emb = None
            if row["embedding"] is not None:
                try:
                    emb = [float(v) for v in row["embedding"]]
                except (TypeError, ValueError):
                    pass
            # 构建元数据 — 合并 metadata JSONB + 时间戳
            meta = {}
            db_meta = row["metadata"]
            if db_meta:
                meta.update(json.loads(db_meta) if isinstance(db_meta, str) else db_meta)
            if emb:
                meta["_embedding"] = emb
            eff_date = row["doc_effective_date"]
            exp_date = row["doc_expiry_date"]
            if eff_date:
                meta["doc_effective_date"] = str(eff_date)
            if exp_date:
                meta["doc_expiry_date"] = str(exp_date)
                meta["is_expired"] = str(exp_date) < today
            if row["doc_version"]:
                meta["doc_version"] = row["doc_version"]
            if row["created_at"]:
                meta["chunk_indexed_at"] = row["created_at"]

            results.append(SearchResult(
                chunk_id=row["id"],
                doc_id=UUID(row["doc_id"]),
                chunk_index=row["chunk_index"],
                chunk_text=row["chunk_text"],
                source_file=row["source_file"],
                score=float(row["score"]),
                metadata=meta,
            ))

        logger.info(
            f"检索完成: kb_ids={kb_ids}, doc_ids={doc_ids}, "
            f"top_k={request.top_k}, 命中={len(results)}"
        )
        return results
