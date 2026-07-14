"""可观测性模块 — Langfuse 追踪集成。

提供 LangfuseTracer，在检索流水线中创建 trace/span/generation/score。
"""

from .langfuse_tracer import LangfuseTracer

__all__ = ["LangfuseTracer"]
