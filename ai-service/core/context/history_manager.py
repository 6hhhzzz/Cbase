"""对话历史管理器 — Redis 缓存（可选优化层）。

对应《模块功能边界划分》§1.2 Python 允许范围：
- Redis 仅作为可选缓存层，用于加速摘要读写和分布式锁
- PostgreSQL 是唯一数据真实源，由 Java 独占维护
- Python 禁止读写业务数据库表（messages / conversations 等）
- 消息历史由 Java 在 /v1/chat 请求中通过 history_messages 字段转发

Redis 键设计:
    kes:conv:{id}:summary      → String, 摘要纯文本, TTL 7 天
    kes:conv:{id}:summary_lock → String, TTL 30s (SET NX 分布式锁)
"""

import json
from uuid import UUID

import redis.asyncio as aioredis

from common import get_logger
from models.config import RedisConfig

logger = get_logger(__name__)

# Redis Key 前缀
KEY_MESSAGES = "kes:conv:{id}:messages"
KEY_SUMMARY = "kes:conv:{id}:summary"
KEY_META = "kes:conv:{id}:meta"
KEY_SUMMARY_LOCK = "kes:conv:{id}:summary_lock"

# 常量
DEFAULT_TTL = 604800  # 7 天（秒）


class HistoryManager:
    """Redis 缓存管理器（可选优化层）。

    职责（仅限）:
    - 摘要缓存读写（Redis）
    - 摘要更新分布式锁（Redis SET NX）
    - 消息缓存（Redis，可选加速，非权威源）

    禁止:
    - 读写业务数据库表（messages / conversations）
    - 将 Redis 数据视为权威真实源
    """

    def __init__(self, redis_config: RedisConfig):
        self._redis_cfg = redis_config
        self._redis: aioredis.Redis | None = None

    async def initialize(self) -> None:
        """初始化 Redis 连接池。"""
        self._redis = aioredis.Redis(
            host=self._redis_cfg.host,
            port=self._redis_cfg.port,
            db=self._redis_cfg.db,
            decode_responses=True,
        )

    async def close(self) -> None:
        """关闭连接。"""
        if self._redis:
            await self._redis.close()

    # ========== Key 辅助 ==========

    def _msg_key(self, conversation_id: UUID) -> str:
        return KEY_MESSAGES.format(id=str(conversation_id))

    def _summary_key(self, conversation_id: UUID) -> str:
        return KEY_SUMMARY.format(id=str(conversation_id))

    def _meta_key(self, conversation_id: UUID) -> str:
        return KEY_META.format(id=str(conversation_id))

    def _lock_key(self, conversation_id: UUID) -> str:
        return KEY_SUMMARY_LOCK.format(id=str(conversation_id))

    # ========== 摘要缓存 ==========

    async def get_summary(self, conversation_id: UUID) -> str | None:
        """从 Redis 读取最新摘要文本。"""
        if not self._redis:
            return None
        return await self._redis.get(self._summary_key(conversation_id))

    async def update_summary(
        self, conversation_id: UUID, summary: str, token_count: int
    ) -> None:
        """更新摘要缓存。"""
        if not self._redis:
            return
        await self._redis.setex(
            self._summary_key(conversation_id),
            DEFAULT_TTL,
            summary,
        )
        await self._redis.hset(
            self._meta_key(conversation_id), "summary_tokens", str(token_count)
        )

    # ========== 消息缓存（可选，非权威源） ==========

    async def get_recent_messages(
        self, conversation_id: UUID, count: int = 30
    ) -> list[dict]:
        """从 Redis 读取缓存的最近消息。

        Redis 未命中时返回空列表——消息历史的权威来源是
        Java 通过 /v1/chat 请求转发的 history_messages 字段。
        """
        if not self._redis:
            return []
        key = self._msg_key(conversation_id)
        raw_list = await self._redis.lrange(key, -count, -1)
        if raw_list:
            messages = []
            for raw in raw_list:
                data = json.loads(raw)
                messages.append(data)
            return messages
        return []

    async def get_total_rounds(self, conversation_id: UUID) -> int:
        """获取会话总轮次（从 Redis 消息列表长度估算）。

        每轮 = 2 条消息（user + assistant）。
        Redis 未命中时返回 0。
        """
        if not self._redis:
            return 0
        raw_count = await self._redis.llen(self._msg_key(conversation_id))
        return raw_count // 2

    async def cache_message(self, conversation_id: UUID, role: str, content: str) -> None:
        """将消息缓存到 Redis（可选优化，非持久化存储）。"""
        if not self._redis:
            return
        key = self._msg_key(conversation_id)
        data = {"role": role, "content": content}
        raw = json.dumps(data, ensure_ascii=False)
        await self._redis.rpush(key, raw)
        await self._redis.expire(key, DEFAULT_TTL)

    # ========== 分布式锁 ==========

    async def acquire_summary_lock(self, conversation_id: UUID) -> bool:
        """获取摘要更新锁，防止并发重复生成。

        Returns:
            True 表示获取成功，False 表示已有其他进程在更新
        """
        if not self._redis:
            return False
        key = self._lock_key(conversation_id)
        return await self._redis.set(key, "1", nx=True, ex=30)

    async def release_summary_lock(self, conversation_id: UUID) -> None:
        """释放摘要更新锁。"""
        if self._redis:
            await self._redis.delete(self._lock_key(conversation_id))
