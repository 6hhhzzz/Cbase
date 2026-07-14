"""Trace 内存缓存 — MCP 侧 trace_id → trace 缓存，TTL 自动过期。"""

import asyncio
import time
from dataclasses import dataclass

from common import get_logger

logger = get_logger(__name__)

# MCP 内存缓存 TTL（秒）
_CACHE_TTL = 600  # 10 分钟


@dataclass
class _CachedTrace:
    trace: dict
    expires_at: float


class TraceCache:
    """MCP 内存缓存，用于在 MCP Tool 调用和反馈上报之间传递 trace 数据。"""

    def __init__(self):
        self._cache: dict[str, _CachedTrace] = {}
        self._cleanup_task: asyncio.Task | None = None

    def put(self, trace_id: str, trace: dict) -> None:
        """将 trace 存入内存缓存（TTL 自动过期）。"""
        self._cache[trace_id] = _CachedTrace(
            trace=trace,
            expires_at=time.monotonic() + _CACHE_TTL,
        )
        self._start_cleanup()

    def pop(self, trace_id: str) -> dict | None:
        """从内存缓存取出并删除 trace。"""
        self._evict_expired()
        entry = self._cache.pop(trace_id, None)
        if entry is None:
            return None
        return entry.trace

    def _start_cleanup(self) -> None:
        """启动后台清理任务（仅一次）。"""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """后台定期清理过期缓存。"""
        while self._cache:
            await asyncio.sleep(60)
            self._evict_expired()

    def _evict_expired(self) -> None:
        """删除所有过期缓存条目。"""
        now = time.monotonic()
        expired = [
            tid for tid, entry in self._cache.items()
            if entry.expires_at <= now
        ]
        for tid in expired:
            del self._cache[tid]
