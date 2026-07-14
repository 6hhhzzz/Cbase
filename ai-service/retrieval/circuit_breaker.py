"""DAG 执行熔断器 — 防止异常子查询耗尽资源。

从 orchestrator.py 提取，独立类，无依赖。
"""

import time


class DAGCircuitBreaker:
    """DAG 执行熔断器。

    熔断条件（OR 逻辑）：
      - 连续 2 个子查询检索结果为空（无任何 chunk）
      - DAG 总执行时间 > total_timeout_ms（默认 30s）
      - 连续 2 次 SLM 提取返回空

    注意：不再使用 RRF 排名分作为熔断依据。
    RRF 分 = 1/(k+rank) 天然 < 0.05，无法反映相关性质量。
    """

    def __init__(self, max_empty_streak=2, total_timeout_ms=30000,
                 max_extract_failures=2):
        self._max_empty_streak = max_empty_streak
        self._max_extract_failures = max_extract_failures
        self.empty_streak = 0
        self.extract_failure_streak = 0
        self.start_time = time.time()
        self.total_timeout_ms = total_timeout_ms
        self.tripped = False
        self.trip_reason = ""

    def check_empty(self, is_empty: bool) -> None:
        """检查子查询检索结果是否为空。连续 N 次为空 → 熔断。"""
        if is_empty:
            self.empty_streak += 1
        else:
            self.empty_streak = 0
        if self.empty_streak >= self._max_empty_streak:
            self.tripped = True
            self.trip_reason = f"连续 {self.empty_streak} 次子查询检索无结果"

    def check_timeout(self) -> None:
        """检查 DAG 总执行时间是否超时。"""
        elapsed = (time.time() - self.start_time) * 1000
        if elapsed > self.total_timeout_ms:
            self.tripped = True
            self.trip_reason = f"DAG 执行超时 ({self.total_timeout_ms}ms)"

    def check_extract_failure(self, extracted: dict | None) -> str:
        """检查 SLM 提取是否连续失败。返回 'fallback_to_keywords' 或 'continue'。"""
        if not extracted or not extracted.get("entities"):
            self.extract_failure_streak += 1
        else:
            self.extract_failure_streak = 0
        if self.extract_failure_streak >= self._max_extract_failures:
            return "fallback_to_keywords"
        return "continue"
