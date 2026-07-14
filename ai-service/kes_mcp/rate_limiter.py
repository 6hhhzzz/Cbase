"""Token Bucket 频率限制器 — 单进程级别，控制 MCP Tool + Resource 调用速率。

使用 Token Bucket 算法：
- 容量 30 tokens：允许突发（Agent 并行读 Resource 场景）
- 填充 1 token/s：稳态 60 次/分钟，远超合理 Agent 行为
- async 安全：asyncio.Lock 保护
- 单调时钟：time.monotonic() 不受系统时间跳变影响
"""

import asyncio
import time


class TokenBucket:
    """Token Bucket 频率限制器。

    用法::

        bucket = TokenBucket(capacity=30, fill_rate=1.0)
        async with bucket:
            allowed, retry_after = bucket.consume()
            if not allowed:
                raise RateLimitExceeded(retry_after)
    """

    def __init__(self, capacity: int = 30, fill_rate: float = 1.0):
        """
        Args:
            capacity: 最大 token 数（突发容量）
            fill_rate: token 填充速率（个/秒）
        """
        self._capacity = float(capacity)
        self._fill_rate = fill_rate
        self._tokens = float(capacity)  # 初始满桶
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self, n: int = 1) -> tuple[bool, float]:
        """消费 n 个 token。

        Returns:
            (allowed, retry_after_seconds)
            - allowed=True: 消费成功
            - allowed=False: token 不足，retry_after 为建议等待秒数（向上取整）
        """
        async with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True, 0.0

            # token 不足，计算需要等待的时间
            needed = n - self._tokens
            wait_seconds = needed / self._fill_rate
            return False, max(1.0, wait_seconds)

    def _refill(self):
        """根据流逝时间补充 token（需在 lock 内调用）。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._fill_rate)
        self._last_refill = now

    @property
    def available(self) -> float:
        """当前可用 token 数（仅用于监控/测试，不保证原子性）。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        return min(self._capacity, self._tokens + elapsed * self._fill_rate)
