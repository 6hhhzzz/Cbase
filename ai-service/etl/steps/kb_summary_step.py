"""UpdateKBSummaryStep — 文档入库后刷新 KB 摘要。

在 IndexStep 之后运行，聚合该 KB 下所有文档的 doc_topics，
生成 kb_summary 和 kb_topics，调用 Java API 写入 knowledge_bases.metadata。
"""

import json
import os

import httpx

from common import get_logger
from .base import PipelineStep

logger = get_logger(__name__)

_JAVA_BASE = os.environ.get("KES_JAVA_URL", "http://localhost:8080")


class UpdateKBSummaryStep(PipelineStep):
    """KB 摘要刷新步骤。

    输入: ctx["msg"].metadata.kb_id, ctx["target_kb_id"]（DocClassifyStep 产出）
    """

    async def execute(self, ctx: dict) -> dict:
        msg = ctx.get("msg")
        if not msg:
            return ctx

        kb_id = ctx.get("target_kb_id") or msg.metadata.kb_id
        if not kb_id:
            return ctx

        try:
            pool = await self._get_pool()
            if not pool:
                logger.warning("UpdateKBSummary: 无法获取 pgpool")
                return ctx

            # 聚合该 KB 下所有 doc_topics
            all_topics = await self._aggregate_topics(pool, kb_id)
            if not all_topics:
                logger.info(f"UpdateKBSummary: KB {kb_id} 无文档，跳过")
                return ctx

            kb_summary = "、".join(all_topics[:6])

            # 通过 Java API 写入
            space_id = await self._get_space_id(pool, kb_id)
            if space_id:
                await self._call_java_api(kb_id, space_id, kb_summary, all_topics)
                logger.info(f"UpdateKBSummary: kb_id={kb_id}, summary={kb_summary}")

        except Exception as e:
            logger.warning(f"UpdateKBSummary 失败: {e}")

        return ctx

    async def _get_pool(self):
        try:
            # 通过 app.state 或全局引用获取 pool
            import api.app as app_mod
            pg = getattr(app_mod, '_pgvector_client', None)
            if pg and hasattr(pg, 'pool'):
                return pg.pool
        except Exception:
            pass
        return None

    async def _get_space_id(self, pool, kb_id: str) -> str | None:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT space_id FROM knowledge_bases WHERE id = $1", kb_id
                )
                return row["space_id"] if row else None
        except Exception:
            return None

    async def _aggregate_topics(self, pool, kb_id: str) -> list[str]:
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DISTINCT metadata->'doc_topics' AS topics
                    FROM knowledge_chunks
                    WHERE kb_id = $1 AND status = 'active'
                      AND metadata->'doc_topics' IS NOT NULL
                """, kb_id)

            seen = set()
            unique = []
            for r in rows:
                topics = r["topics"]
                if isinstance(topics, str):
                    topics = json.loads(topics)
                if isinstance(topics, list):
                    for t in topics:
                        if t not in seen:
                            seen.add(t)
                            unique.append(t)
            return unique
        except Exception:
            return []

    async def _call_java_api(self, kb_id: str, space_id: str,
                              kb_summary: str, kb_topics: list[str]) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # 使用内部 token（MCP auth 或 app token）
                resp = await client.put(
                    f"{_JAVA_BASE}/api/spaces/{space_id}/kbs/{kb_id}/metadata",
                    json={"kb_summary": kb_summary, "kb_topics": kb_topics},
                    headers={"X-Internal-Call": "true"},
                )
                if resp.status_code != 200:
                    logger.warning(f"Java API 返回 {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"调用 Java API 失败: {e}")
