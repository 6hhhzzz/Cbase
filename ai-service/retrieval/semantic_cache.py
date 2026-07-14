"""Semantic Cache — 语义缓存层（Stage 0, v12）。

在检索全流程最上游拦截高频重复查询。
命中 → 跳过所有 Stage, 50ms 内返回缓存答案。

缓存在 Redis 中，key 为 query embedding hash + history hash，
TTL 与文档有效期联动。

不适合缓存的情况：
  - 含时间限定词（"最近"/"本周"等）
  - 含用户身份相关词（"我的"/"我的部门"）
  - DAG 复杂查询
"""

import hashlib
import json
import time

from common import get_logger

logger = get_logger(__name__)

# 相似度阈值
CACHE_SIMILARITY_THRESHOLD = 0.95

# 不适合缓存的词
TEMPORAL_WORDS = ["最近", "本周", "上周", "这个月", "上个月", "今年", "去年", "今天", "昨天", "明天"]
PERSONAL_WORDS = ["我的", "我们", "我部门", "我个人", "我"]


class SemanticCache:
    """语义缓存。

    用法::

        cache = SemanticCache(pgvector_client, redis_client)
        cached = await cache.get(query, history_hash)
        if cached:
            return cached  # 直接返回，跳过检索
        # ... 执行完整检索 ...
        await cache.set(query, history_hash, answer, sources)
    """

    def __init__(self, pgvector_client, redis_client):
        self._pg = pgvector_client
        self._redis = redis_client
        self._prefix = "kes:cache:"

    async def get(
        self, query: str, history_hash: str = ""
    ) -> dict | None:
        """查询缓存。

        Args:
            query: 用户查询文本
            history_hash: 对话历史的 hash（用于区分不同上下文）

        Returns:
            缓存命中时返回 {"answer", "sources", "citations"}，
            未命中返回 None
        """
        cache_key = self._build_key(query, history_hash)

        try:
            cached = await self._redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                cached_at = data.get("cached_at", 0)
                ttl = data.get("ttl", 300)
                if time.time() - cached_at < ttl:
                    logger.info(f"SemanticCache 命中: query='{query[:50]}...'")
                    return {
                        "answer": data.get("answer", ""),
                        "sources": data.get("sources", []),
                        "citations": data.get("citations", []),
                    }
                else:
                    logger.debug(f"SemanticCache 过期: query='{query[:50]}...'")
        except Exception as e:
            logger.warning(f"SemanticCache get 失败: {e}")

        return None

    async def set(
        self,
        query: str,
        history_hash: str,
        answer: str,
        sources: list[dict],
        citations: list[dict] | None = None,
        ttl: int = 3600,
    ) -> None:
        """写入缓存。

        Args:
            query: 用户查询文本
            history_hash: 对话历史 hash
            answer: LLM 生成的答案
            sources: 引用来源列表
            citations: 引用详情
            ttl: 过期时间（秒），默认 1 小时
        """
        cache_key = self._build_key(query, history_hash)

        data = {
            "answer": answer,
            "sources": sources,
            "citations": citations or [],
            "cached_at": int(time.time()),
            "ttl": ttl,
            "query_hash": self._query_hash(query),
        }

        try:
            await self._redis.setex(cache_key, ttl, json.dumps(data, ensure_ascii=False))
            logger.debug(f"SemanticCache 写入: query='{query[:50]}...', ttl={ttl}s")
        except Exception as e:
            logger.warning(f"SemanticCache set 失败: {e}")

    @staticmethod
    def is_cacheable(query: str, complexity: str = "simple") -> bool:
        """判断查询是否适合缓存。

        Args:
            query: 查询文本
            complexity: 查询复杂度（simple/complex）

        Returns:
            True 表示适合缓存
        """
        if complexity == "complex":
            return False
        if any(w in query for w in TEMPORAL_WORDS):
            return False
        if any(w in query for w in PERSONAL_WORDS):
            return False
        return True

    @staticmethod
    def _query_hash(query: str) -> str:
        return hashlib.md5(query.strip().encode()).hexdigest()[:16]

    def _build_key(self, query: str, history_hash: str) -> str:
        qh = self._query_hash(query)
        if history_hash:
            return f"{self._prefix}{qh}:{history_hash[:8]}"
        return f"{self._prefix}{qh}"
