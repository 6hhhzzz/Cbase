"""Chunk 数据写入 — 批量插入 + 删除 + 状态更新。"""

import json
from datetime import date
from uuid import UUID

from pgvector.asyncpg import register_vector
from pgvector.utils import Vector

from common import get_logger
from common.utils import current_timestamp_ms, generate_chunk_id, tokenize_chinese
from models.document import DocumentChunk

logger = get_logger(__name__)


def _parse_date(value: str | None) -> date | None:
    """将 YYYY-MM-DD 字符串转为 datetime.date。"""
    if value is None:
        return None
    return date.fromisoformat(value)


async def insert_chunks(
    chunks: list[DocumentChunk],
    pool,
    embedding,
    vectors: list[list[float]] | None = None,
) -> int:
    """批量写入 Chunk + 可选的预计算向量。"""
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
            batch_vectors = await embedding.embed_documents(batch)
            vectors.extend(batch_vectors)
            logger.debug(f"向量化 {i + len(batch)}/{len(texts)} 条")

    # 构建批量插入数据
    rows = []
    for i, chunk in enumerate(chunks):
        meta = chunk.metadata
        cw = meta.get("content_with_weight", chunk.chunk_text)

        chunk_meta = {
            "chunk_type": meta.get("chunk_type", "text"),
            "level": meta.get("level"),
            "heading": meta.get("heading"),
            "page_range": meta.get("page_range"),
            "doc_id": str(chunk.doc_id),
            # v12 parent-child: 两级分块元数据（parent_id 空时 excluded）
            "parent_id": meta.get("parent_id"),
            "parent_content": meta.get("parent_content"),
            "parent_title": meta.get("parent_title"),
        }
        chunk_meta = {k: v for k, v in chunk_meta.items() if v is not None}
        meta_json = json.dumps(chunk_meta, ensure_ascii=False)

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
            meta_json,
            current_timestamp_ms(),
            tokenize_chinese(cw),
        ))

    async with pool.acquire() as conn:
        await register_vector(conn)
        await conn.executemany("""
            INSERT INTO knowledge_chunks
                (id, doc_id, chunk_index, chunk_text, embedding,
                 kb_id, status, source_file,
                 doc_effective_date, doc_expiry_date, doc_version,
                 content_with_weight, metadata, created_at, fts)
            VALUES ($1, $2, $3, $4, $5::vector,
                    $6, 'active', $7, $8, $9, $10,
                    $11, $12::jsonb, $13, to_tsvector('simple', $14))
            ON CONFLICT (id) DO NOTHING
        """, rows)

    logger.info(f"成功写入 {len(chunks)} 个 chunks 到 PostgreSQL")
    return len(chunks)


async def delete_by_doc_id(doc_id: UUID, pool) -> int:
    """按 doc_id 删除所有关联 Chunk。"""
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM knowledge_chunks WHERE doc_id = $1",
            str(doc_id),
        )
        count = int(result.split()[1]) if result.startswith("DELETE") else 0
        logger.info(f"已删除 doc_id={doc_id} 的 {count} 个 chunks")
        return count


async def update_chunk_status(doc_id: str, status: str, pool) -> int:
    """批量更新某文档所有 chunks 的状态。"""
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE knowledge_chunks SET status = $1 WHERE doc_id = $2",
            status, doc_id,
        )
        count = int(result.split()[1]) if result.startswith("UPDATE") else 0
        logger.info(f"已更新 chunks 状态: doc_id={doc_id}, status={status}, count={count}")
        return count
