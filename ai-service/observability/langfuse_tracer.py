"""LangfuseTracer — DAG 检索流水线的 Langfuse 埋点封装 (SDK v2)。

核心理念：span/generation 创建后必须调用 update() 才会发送到 Langfuse。

用法:
    tracer = LangfuseTracer()
    trace = tracer.trace("查询文本", user_id="xxx")
    # 在 orchestrator 中
    span = trace.span(name="wave_0", metadata={...})
    span.update(metadata={...})   # ← 必须！
    gen = trace.generation(name="answer", model="qwen-plus")
    gen.update(output="...")
    tracer.flush()

环境变量:
    LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY / LANGFUSE_BASE_URL
"""

from __future__ import annotations

import os
from typing import Any

from common import get_logger

logger = get_logger(__name__)

_DISABLED = object()


class LangfuseTracer:
    """Langfuse 追踪器 — SDK v2 API 封装。"""

    def __init__(self):
        self._client = None
        self._enabled = False
        self._ensure_client()

    # ── 公共 API ────────────────────────────────────────────

    def trace(self, name: str, user_id: str = "", session_id: str = "",
              metadata: dict[str, Any] | None = None,
              input_data: Any = None) -> Any:
        """创建顶层 trace，返回 StatefulTraceClient。"""
        if not self._client:
            return _DISABLED
        try:
            kwargs: dict = {"name": name[:200], "metadata": metadata}
            if input_data is not None:
                kwargs["input"] = input_data
            # SDK v2 的 or 逻辑把 "" 当作 None → 触发 validation error
            # 解决：只在有实际值时传参
            if user_id:
                kwargs["user_id"] = user_id
            if session_id:
                kwargs["session_id"] = session_id
            trace = self._client.trace(**kwargs)
            return trace
        except Exception as e:
            logger.debug(f"Langfuse trace 失败: {e}")
            return _DISABLED

    def span(self, parent: Any, name: str,
             metadata: dict[str, Any] | None = None,
             input_data: Any = None,
             output_data: Any = None) -> Any:
        """创建子 span，支持 input/output 直传（Langfuse UI 节点图渲染）。"""
        if parent is _DISABLED or parent is None or not self._client:
            return _DISABLED
        try:
            _trace_id = getattr(parent, 'id', None) or getattr(parent, 'trace_id', None)
            kwargs: dict = {"name": name, "metadata": metadata}
            if input_data is not None:
                kwargs["input"] = input_data
            if output_data is not None:
                kwargs["output"] = output_data
            if _trace_id:
                kwargs["trace_id"] = _trace_id
            s = parent.span(**kwargs)
            s.update()
            return s
        except Exception:
            return _DISABLED

    def generation(self, parent: Any, name: str, model: str = "",
                   metadata: dict[str, Any] | None = None,
                   input_data: Any = None,
                   output_data: Any = None) -> Any:
        """创建 generation span，支持 input/output 直传。"""
        if parent is _DISABLED or parent is None or not self._client:
            return _DISABLED
        try:
            _trace_id = getattr(parent, 'id', None) or getattr(parent, 'trace_id', None)
            kwargs: dict = {"name": name, "model": model or None, "metadata": metadata}
            if input_data is not None:
                kwargs["input"] = input_data
            if output_data is not None:
                kwargs["output"] = output_data
            if _trace_id:
                kwargs["trace_id"] = _trace_id
            g = parent.generation(**kwargs)
            g.update()
            return g
        except Exception:
            return _DISABLED

    def update_span(self, span_obj: Any, output: Any = None,
                    metadata: dict[str, Any] | None = None):
        """更新 span 的 output 和 metadata。"""
        if span_obj is _DISABLED or span_obj is None:
            return
        try:
            kwargs: dict = {}
            if output is not None:
                kwargs["output"] = output
            if metadata:
                kwargs["metadata"] = metadata
            if kwargs:
                span_obj.update(**kwargs)
        except Exception:
            pass

    def score(self, name: str, value: float, comment: str = ""):
        """挂评分到当前 trace。"""
        if not self._client:
            return
        try:
            self._client.score(name=name, value=value, comment=comment)
        except Exception:
            pass

    def flush(self):
        """刷新缓冲区。"""
        if self._client:
            try:
                self._client.flush()
            except Exception:
                pass

    # ── 内部 ─────────────────────────────────────────────────

    def _ensure_client(self):
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        base_url = os.getenv("LANGFUSE_BASE_URL", "")

        # 显式开关：LANGFUSE_ENABLED=true 才启用追踪
        if os.getenv("LANGFUSE_ENABLED", "").lower() not in ("true", "1", "yes"):
            logger.info("Langfuse 已禁用（LANGFUSE_ENABLED 未开启）")
            return

        if not secret_key or not public_key:
            logger.info("Langfuse 未配置，追踪已禁用")
            return

        try:
            from langfuse import Langfuse
            self._client = Langfuse(
                secret_key=secret_key,
                public_key=public_key,
                host=base_url,
            )
            self._enabled = True
            logger.info(f"Langfuse 已连接: {base_url}")
        except ImportError:
            logger.warning("langfuse 未安装")
        except Exception as e:
            logger.warning(f"Langfuse 初始化失败: {e}")
