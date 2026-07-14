"""检索质量追踪与反馈采集。

子模块:
  - builder: TraceBuilder — 纯数据转换，从检索上下文构建 trace dict
  - repository: FeedbackRepository — asyncpg 数据库 INSERT/UPDATE
  - cache: TraceCache — MCP 内存缓存，TTL 过期
"""

import random

from .builder import build_trace
from .repository import FeedbackRepository
from .cache import TraceCache

# 采样率
DEFAULT_SAMPLE_RATE = 0.05


class RetrievalTracer:
    """检索质量追踪器（组合 facade）。

    组合 TraceBuilder + FeedbackRepository + TraceCache + 采样。
    """

    def __init__(self, pool=None):
        self._repo = FeedbackRepository(pool)
        self._cache = TraceCache()

    # ---- Trace 构建（委托给 builder） ----

    def build_trace(self, **kwargs) -> dict:
        """从检索上下文构建 7 模块 trace dict。"""
        return build_trace(**kwargs)

    # ---- 持久化（委托给 repository） ----

    async def save_trace(self, trace: dict) -> str:
        """INSERT trace 到 retrieval_feedback 表。"""
        return await self._repo.save_trace(trace)

    async def update_feedback(
        self, trace_id: str, rating: str, reason: str = ""
    ) -> bool:
        """UPDATE 已有 trace 的反馈。"""
        return await self._repo.update_feedback(trace_id, rating, reason)

    async def update_judge_scores(
        self,
        trace_id: str,
        faithfulness: float,
        answer_relevance: float,
        context_relevance: float,
        judge_model: str = "",
        judge_latency_ms: int = 0,
    ) -> bool:
        """UPDATE Judge 评分到已有 trace。"""
        return await self._repo.update_judge_scores(
            trace_id, faithfulness, answer_relevance,
            context_relevance, judge_model, judge_latency_ms,
        )

    # ---- 内存缓存（委托给 cache） ----

    def cache_trace(self, trace_id: str, trace: dict) -> None:
        """将 trace 存入内存缓存。"""
        self._cache.put(trace_id, trace)

    def pop_cached(self, trace_id: str) -> dict | None:
        """从内存缓存取出并删除 trace。"""
        return self._cache.pop(trace_id)

    # ---- 采样 ----

    @staticmethod
    def should_sample(rate: float = DEFAULT_SAMPLE_RATE) -> bool:
        """随机采样判断。"""
        return random.random() < rate
