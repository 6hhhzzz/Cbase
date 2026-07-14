"""SparseRetriever — 稀疏关键词检索（PostgreSQL tsvector BM25）。

使用 PostgreSQL 原生全文搜索能力：
    - tsvector: 分词后的文档向量（存储在 fts 列）
    - ts_query: 分词后的查询
    - ts_rank: BM25 类似的排名函数
    - GIN 索引：加速全文搜索
"""

import asyncio

import asyncpg

from common import get_logger
from .models import ScoredChunk

logger = get_logger(__name__)


class SparseRetriever:
    """稀疏（关键词）检索器 — PostgreSQL 全文搜索。

    使用 tsvector + ts_query 实现类似 BM25 的效果。
    对专有名词、产品型号、内部代号等精确匹配极其有效。

    v12: 新增 search_splade() — SPLADE 神经词扩展检索。
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Args:
            pool: asyncpg 连接池（复用 PGVectorClient 的连接池）
        """
        self._pool = pool

    async def search(
        self,
        query: str,
        kb_ids: list[str],
        top_k: int = 30,
        keywords: list[str] | None = None,
        excluded_doc_ids: list[str] | None = None,
    ) -> list[ScoredChunk]:
        """执行关键词全文检索。

        Args:
            query: 用户查询文本
            kb_ids: 有权访问的知识库 ID 列表
            top_k: 返回结果数
            keywords: 额外的关键词（来自 QueryRewriter 输出）
            excluded_doc_ids: 排除的文档 ID 列表

        Returns:
            ScoredChunk 列表，按 ts_rank 降序
        """
        if not query.strip() and not keywords:
            return []

        # 构建 ts_query：原始查询 + 关键词加权
        search_text = query
        if keywords:
            # 关键词放到前面增加权重
            search_text = " ".join(keywords) + " " + query

        # 将中文查询转为 PostgreSQL ts_query 可用格式
        # tsvector 使用 simple 词典（对中文按字符拆分）
        ts_query = _build_ts_query(search_text)

        async with self._pool.acquire() as conn:
            from pgvector.asyncpg import register_vector
            await register_vector(conn)

            rows = await conn.fetch("""
                SELECT id, chunk_text, content_with_weight, source_file,
                       doc_effective_date, doc_expiry_date, doc_version, created_at,
                       ts_rank(fts, $1::tsquery) AS score
                FROM knowledge_chunks
                WHERE kb_id = ANY($2)
                  AND status = 'active'
                  AND fts @@ $1::tsquery
                  AND ($4::text[] IS NULL OR doc_id != ALL($4))
                ORDER BY score DESC
                LIMIT $3
            """, ts_query, kb_ids, top_k, excluded_doc_ids)

        from typing import Any
        from datetime import date

        today = date.today().isoformat()
        chunks = []
        for row in rows:
            meta: dict[str, Any] = {"retriever": "sparse"}
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

            chunks.append(ScoredChunk(
                chunk_id=row["id"],
                content=row["content_with_weight"] or row["chunk_text"],
                score=float(row["score"]),
                source_file=row["source_file"] or "",
                metadata=meta,
            ))

        logger.debug(f"SparseRetriever(BM25): query='{query[:50]}...', keywords={keywords}, hits={len(chunks)}")
        return chunks

    async def ensure_fts_column(self) -> None:
        """确保 knowledge_chunks 表有 fts 列和 GIN 索引。

        对已有 NULL fts 的行，使用 jieba 分词后构建 tsvector；
        无 jieba 时降级为逐字拆分。
        """
        async with self._pool.acquire() as conn:
            # 添加 fts 列
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'knowledge_chunks' AND column_name = 'fts'
                    ) THEN
                        ALTER TABLE knowledge_chunks ADD COLUMN fts tsvector;
                    END IF;
                END $$;
            """)
            # 添加 content_with_weight 列
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'knowledge_chunks' AND column_name = 'content_with_weight'
                    ) THEN
                        ALTER TABLE knowledge_chunks ADD COLUMN content_with_weight TEXT;
                    END IF;
                END $$;
            """)
            # 对 NULL fts 的行逐行更新（使用 jieba 分词）
            rows = await conn.fetch(
                "SELECT id, COALESCE(content_with_weight, chunk_text) AS text "
                "FROM knowledge_chunks WHERE fts IS NULL"
            )
            if rows:
                for row in rows:
                    tokenized = _tokenize_for_tsvector(row["text"])
                    if tokenized:
                        await conn.execute(
                            "UPDATE knowledge_chunks SET fts = to_tsvector('simple', $1) WHERE id = $2",
                            tokenized, row["id"],
                        )
                logger.info(f"FTS 已为 {len(rows)} 条记录构建（jieba 分词）")
            # 创建 GIN 索引
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_kc_fts
                ON knowledge_chunks USING GIN (fts)
            """)
            logger.info("FTS 列和 GIN 索引已确保存在")


def _build_ts_query(text: str) -> str:
    """将搜索文本转为 PostgreSQL ts_query 格式。

    使用 jieba 分词后将词用 | 连接：
        "项目背景介绍" → '项目'|'背景'|'介绍'
    英文/数字保留原词。

    降级：jieba 不可用时回退到逐字拆分。
    """
    if not text or not text.strip():
        return "''"

    terms = _tokenize(text)
    if not terms:
        return "''"
    # 去重保序 + 限制 30 个词
    seen = set()
    unique_terms = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)
    return " | ".join(f"'{t}'" for t in unique_terms[:30])


def _tokenize(text: str) -> list[str]:
    """中文分词 + 英文/数字保留。"""
    import re

    try:
        import jieba
    except ImportError:
        return _tokenize_fallback(text)

    terms = []
    # 先按空格和标点拆分，对每段做 jieba 分词
    segments = re.split(r'[\s,，。！？、：；（）()【】]+', text.replace('"', ' ').replace("'", ' '))
    for seg in segments:
        if not seg:
            continue
        # 纯英文/数字直接保留
        if re.match(r'^[a-zA-Z0-9._\-]+$', seg):
            terms.append(seg)
        else:
            words = jieba.cut(seg)
            for w in words:
                w = w.strip().replace("'", "''")
                if w and len(w) >= 1:
                    terms.append(w)
    return terms


def _tokenize_fallback(text: str) -> list[str]:
    """无 jieba 时的降级分词（逐字符拆分中文）。"""
    import re
    terms = []
    parts = text.split()
    for part in parts:
        sub_parts = re.findall(r'[一-鿿]|[a-zA-Z0-9]+|\S', part)
        for sp in sub_parts:
            clean = sp.strip().replace("'", "''")
            if clean:
                terms.append(clean)
    return terms


def _tokenize_for_tsvector(text: str) -> str:
    """为 tsvector 构建做分词，委托给 common.utils.tokenize_chinese。"""
    from common.utils import tokenize_chinese
    return tokenize_chinese(text)
