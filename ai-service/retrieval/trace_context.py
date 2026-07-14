"""TraceContext — 统一追踪上下文。

替代旧的两套追踪系统（Langfuse 猴子补丁 + trace_detail dict 手动构建）。
贯穿整个检索→生成→引用链路，每个节点通过 span() 记录结构化 input/output。
中间 Chunk 只记 chunk_id，不记全文 snippet。
结束时调用 to_langfuse() 生成 Langfuse span 树，to_trace_dict() 生成 DB 落库 dict。

用法:
    trace_ctx = TraceContext(query="...", source="web_chat", metadata={...})

    h = trace_ctx.span("query_planner", input={"query": ..., "history_len": 3})
    plan = await planner.plan(query, history)
    h.finish(output={"complexity": plan.complexity, "sub_query_count": 3})

    trace_ctx.to_langfuse(langfuse_tracer, parent_trace)
    trace_dict = trace_ctx.to_trace_dict()
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpanSnapshot:
    """一次操作的结构化快照。"""

    node: str                          # "query_planner"、"hybrid_search"、"reranker" 等
    input: dict[str, Any]              # 结构化输入
    output: dict[str, Any] = field(default_factory=dict)  # 结构化输出（finish() 时填入）
    timing_ms: int = 0                 # 耗时（毫秒）
    error: str | None = None           # 错误信息
    children: list[SpanSnapshot] = field(default_factory=list)


class SpanHandle:
    """span() 返回的句柄，调用 .finish() 完成记录。"""

    __slots__ = ("_snapshot", "_start")

    def __init__(self, snapshot: SpanSnapshot) -> None:
        self._snapshot = snapshot
        self._start = time.monotonic()

    def finish(self, output: dict[str, Any]) -> SpanSnapshot:
        """完成记录并返回 snapshot（自动计算耗时）。"""
        self._snapshot.output = output
        self._snapshot.timing_ms = int((time.monotonic() - self._start) * 1000)
        return self._snapshot

    def fail(self, error: str) -> SpanSnapshot:
        """以错误状态完成。"""
        self._snapshot.error = error
        self._snapshot.timing_ms = int((time.monotonic() - self._start) * 1000)
        return self._snapshot

    def child(self, node: str, input: dict[str, Any]) -> "SpanHandle":
        """创建子 span（如 DAG 子查询）。"""
        child_snapshot = SpanSnapshot(node=node, input=input)
        self._snapshot.children.append(child_snapshot)
        return SpanHandle(child_snapshot)


class TraceContext:
    """统一追踪上下文，贯穿整个检索→生成→引用链路。

    特性:
        - 每个节点通过 span() 记录结构化 input/output
        - 中间 Chunk 只记 chunk_id，不记全文 snippet
        - to_langfuse() 生成 Langfuse span 树
        - to_trace_dict() 生成 feedback 落库 dict
    """

    def __init__(
        self,
        query: str,
        source: str = "web_chat",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.trace_id = str(uuid.uuid4())
        self.query = query
        self.source = source
        self.metadata = metadata or {}
        self.spans: list[SpanSnapshot] = []

    # ── 记录 span ──────────────────────────────────────────────

    def span(self, node: str, input: dict[str, Any]) -> SpanHandle:
        """开始记录一个操作 span。

        Args:
            node: 节点名，如 "query_planner"、"hybrid_search"、"reranker"
            input: 结构化输入 dict

        Returns:
            SpanHandle, 调用 .finish(output) 完成记录
        """
        snapshot = SpanSnapshot(node=node, input=input)
        self.spans.append(snapshot)
        return SpanHandle(snapshot)

    # ── 生成 Langfuse span 树 ─────────────────────────────────

    # -- 节点分组（控制 Langfuse 树形结构）--
    _RETRIEVAL_NODES = {
        "query_planner", "mcp_query_preparation",
        "hybrid_search", "dag_sub_query", "circuit_breaker",
        "hybrid_fusion", "reranker",
    }
    _GENERATION_NODES = {"llm_generation", "hyde_generation",
                         "three_d_extraction", "judge"}

    def to_langfuse(self, tracer: Any, parent_trace: Any) -> None:
        """生成 Langfuse span 树（嵌套层级 → 节点图）。

        结构:
            [Trace]
             ├── [retrieval]          ← 父 span
             │    ├── query_planner
             │    ├── hybrid_search
             │    │    └── dag_sub_query (含子节点)
             │    ├── hybrid_fusion
             │    └── reranker
             └── [generation]         ← 父 span
                  ├── context_assembly
                  ├── llm_generation
                  ├── citation
                  └── judge
        """
        if not (tracer and getattr(tracer, "_enabled", False)):
            return

        try:
            # Trace 级 metadata
            tracer.update_span(parent_trace, metadata={
                "source": self.source,
                "spans_count": len(self.spans),
                **self.metadata,
            })

            # 创建两个父 span
            retrieval_parent = tracer.span(
                parent=parent_trace, name="retrieval",
                input_data={"query": self.query},
            )
            gen_parent = tracer.span(
                parent=parent_trace, name="generation",
                input_data={"source": self.source},
            )

            # 遍历所有 spans，按类型挂载到对应父节点
            for snap in self.spans:
                if snap.node in self._RETRIEVAL_NODES:
                    parent = retrieval_parent
                else:
                    parent = gen_parent
                self._snapshot_to_langfuse(snap, tracer, parent)

            # 关闭父 span（标记完成）
            if retrieval_parent is not None and retrieval_parent is not object():
                pass  # SDK 自动处理 end_time
            if gen_parent is not None and gen_parent is not object():
                pass

        except Exception:
            pass  # Langfuse 失败不影响主流程

    def _snapshot_to_langfuse(
        self, snap: SpanSnapshot, tracer: Any, parent: Any
    ) -> Any:
        """将单个 SpanSnapshot 转为 Langfuse span/generation，递归嵌套子节点。"""
        is_gen = snap.node in self._GENERATION_NODES
        meta = {"timing_ms": snap.timing_ms, "error": snap.error}

        if is_gen:
            obj = tracer.generation(
                parent=parent, name=snap.node,
                model=snap.input.get("model", ""),
                input_data=snap.input, output_data=snap.output,
                metadata=meta,
            )
        else:
            obj = tracer.span(
                parent=parent, name=snap.node,
                input_data=snap.input, output_data=snap.output,
                metadata=meta,
            )

        # 递归嵌套子 span（如 dag_sub_query 下的 three_d_extraction）
        parent_for_children = obj if obj is not None else parent
        for child in snap.children:
            self._snapshot_to_langfuse(child, tracer, parent_for_children)

        return obj

    # ── 生成 DB trace dict ────────────────────────────────────

    def to_trace_dict(self) -> dict[str, Any]:
        """生成落库用的 trace dict（替代旧 trace_detail）。

        Returns:
            {"trace_id": ..., "query": ..., "spans": [...], "stages_detail": {...}}
        """
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "source": self.source,
            "metadata": self.metadata,
            "spans": [self._snapshot_to_dict(s) for s in self.spans],
        }

    def _snapshot_to_dict(self, snap: SpanSnapshot) -> dict[str, Any]:
        return {
            "node": snap.node,
            "input": snap.input,
            "output": snap.output,
            "timing_ms": snap.timing_ms,
            "error": snap.error,
            "children": [self._snapshot_to_dict(c) for c in snap.children],
        }
