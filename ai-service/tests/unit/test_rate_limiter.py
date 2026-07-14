"""Token Bucket 频率限制器测试。"""

import asyncio
import pytest

from kes_mcp.rate_limiter import TokenBucket


class TestTokenBucket:
    """测试 TokenBucket 核心行为。"""

    @pytest.mark.asyncio
    async def test_initial_full_capacity(self):
        """新桶初始满容量。"""
        bucket = TokenBucket(capacity=30, fill_rate=1.0)
        assert bucket.available >= 29  # 接近满容量

    @pytest.mark.asyncio
    async def test_consume_reduces_tokens(self):
        """消费后 token 数减少。"""
        bucket = TokenBucket(capacity=30, fill_rate=1.0)
        before = bucket.available
        allowed, retry = await bucket.consume()
        assert allowed
        assert retry == 0.0
        assert bucket.available < before

    @pytest.mark.asyncio
    async def test_consume_many_within_capacity(self):
        """连续消费 30 次全部成功（不超过容量）。"""
        bucket = TokenBucket(capacity=30, fill_rate=1.0)
        for i in range(30):
            allowed, _ = await bucket.consume()
            assert allowed, f"第 {i+1} 次消费应该成功"

    @pytest.mark.asyncio
    async def test_exceed_capacity_returns_retry_after(self):
        """超过容量后返回限流 + retry_after。"""
        bucket = TokenBucket(capacity=5, fill_rate=1.0)
        # 耗尽 5 个 token
        for i in range(5):
            allowed, _ = await bucket.consume()
            assert allowed, f"第 {i+1} 次消费应该成功"

        # 第 6 次被限流
        allowed, retry_after = await bucket.consume()
        assert not allowed
        assert retry_after >= 1.0  # 至少需要等 1 秒

    @pytest.mark.asyncio
    async def test_refill_after_wait(self):
        """等待足够时间后 token 自动补充。"""
        bucket = TokenBucket(capacity=5, fill_rate=10.0)  # 快速填充，方便测试
        # 耗尽
        for _ in range(5):
            await bucket.consume()

        # 第 6 次被限流
        allowed, _ = await bucket.consume()
        assert not allowed

        # 等待 token 补充
        await asyncio.sleep(0.2)  # 10 tokens/s, 0.2s = 2 tokens

        allowed, _ = await bucket.consume()
        assert allowed

    @pytest.mark.asyncio
    async def test_refill_capped_at_capacity(self):
        """长时间等待也不会超过容量。"""
        bucket = TokenBucket(capacity=5, fill_rate=100.0)
        # 不消费，等待补充
        await asyncio.sleep(0.1)

        # 可用数不应超过容量
        assert bucket.available <= 5.0

    @pytest.mark.asyncio
    async def test_retry_after_scales_with_needed_tokens(self):
        """retry_after 随所需 token 数等比例增长，最小不低于 1 秒。"""
        bucket = TokenBucket(capacity=10, fill_rate=2.0)
        # 耗尽
        for _ in range(10):
            await bucket.consume()

        # 需要等 1/2 = 0.5 秒，但 retry_after 钳位到不低于 1 秒
        allowed, retry = await bucket.consume()
        assert not allowed
        assert retry >= 1.0

        # fill_rate=0.5 时需要等 2 秒
        bucket_slow = TokenBucket(capacity=2, fill_rate=0.5)
        for _ in range(2):
            await bucket_slow.consume()
        allowed, retry = await bucket_slow.consume()
        assert not allowed
        assert 1.5 <= retry <= 2.5

    @pytest.mark.asyncio
    async def test_concurrent_consumers_dont_exceed_capacity(self):
        """并发消费不会超出容量。"""
        bucket = TokenBucket(capacity=10, fill_rate=1.0)

        success_count = 0

        async def try_consume():
            nonlocal success_count
            allowed, _ = await bucket.consume()
            if allowed:
                success_count += 1

        # 20 个并发消费
        tasks = [try_consume() for _ in range(20)]
        await asyncio.gather(*tasks)

        # 最多成功 10 次（容量），不会超过
        assert success_count <= 10
        # 至少有 8 次成功（允许时间流逝带来少量补充）
        assert success_count >= 8

    @pytest.mark.asyncio
    async def test_default_capacity_and_rate(self):
        """默认参数：容量 30，速率 1.0。"""
        bucket = TokenBucket()
        assert 29 <= bucket.available <= 30
        for i in range(30):
            allowed, _ = await bucket.consume()
            assert allowed, f"第 {i+1} 次应成功"
        # 第 31 次被限流
        allowed, _ = await bucket.consume()
        assert not allowed
