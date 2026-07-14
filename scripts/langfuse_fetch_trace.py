"""Langfuse Trace 全量拉取 — 按 trace ID 输出完整节点树。

用法:
    ./langfuse_fetch_trace.py <trace_id>            # 终端打印
    ./langfuse_fetch_trace.py <trace_id> --json     # JSON 格式
    ./langfuse_fetch_trace.py --last 3              # 最近 N 条
    ./langfuse_fetch_trace.py --last 1 --json       # 最近一条，JSON

示例:
    cd ai-service && .venv/bin/python ../scripts/langfuse_fetch_trace.py c9e2fb3f-27df-4c7e-8b4d-4a475bee30b3
"""

import json
import os
import sys
from collections import defaultdict
from typing import Any

# ── 加载 .env ──
def _load_env(env_path: str = ".env") -> dict:
    env = {}
    # 尝试多个路径
    for p in [env_path, os.path.join(os.path.dirname(__file__), "..", ".env")]:
        try:
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k] = v
            break
        except FileNotFoundError:
            continue
    return env


def _init_client():
    env = _load_env()
    from langfuse import Langfuse
    return Langfuse(
        secret_key=env["LANGFUSE_SECRET_KEY"],
        public_key=env["LANGFUSE_PUBLIC_KEY"],
        host=env["LANGFUSE_BASE_URL"],
    )


# ── 节点树构建 ──

def _node_kind(obs: Any) -> str:
    """判断 observation 类型：span 还是 generation。"""
    t = getattr(obs, "type", "span")
    return str(t).lower() if t else "span"


def _obs_to_dict(obs: Any) -> dict:
    """单个 observation → 结构化 dict。"""
    d: dict[str, Any] = {
        "id": getattr(obs, "id", ""),
        "name": getattr(obs, "name", ""),
        "kind": _node_kind(obs),
        "input": _safe_json(getattr(obs, "input", None)),
        "output": _safe_json(getattr(obs, "output", None)),
        "metadata": _safe_json(getattr(obs, "metadata", None)),
        "model": getattr(obs, "model", None) or None,
        "start_time": str(getattr(obs, "start_time", "")) if getattr(obs, "start_time", None) else None,
        "end_time": str(getattr(obs, "end_time", "")) if getattr(obs, "end_time", None) else None,
        "children": [],
    }
    # 计算耗时
    try:
        if d["start_time"] and d["end_time"]:
            from datetime import datetime
            st = datetime.fromisoformat(d["start_time"].replace("Z", "+00:00"))
            et = datetime.fromisoformat(d["end_time"].replace("Z", "+00:00"))
            d["duration_ms"] = int((et - st).total_seconds() * 1000)
    except Exception:
        d["duration_ms"] = 0
    return d


def _safe_json(val: Any) -> Any:
    """安全解析 JSON 字符串。"""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


def fetch_trace_tree(trace_id: str) -> dict | None:
    """拉取 trace + 所有 observations，构建节点树。"""
    client = _init_client()

    # 拉取所有 observations（分页 API → tuple of (page_key, [ObservationsView])）
    obs_list: list[Any] = []
    for page_key, page_data in client.get_observations(trace_id=trace_id):
        obs_list.extend(page_data)
    if not obs_list:
        print(f"⚠️ Trace {trace_id} 没有 observations", file=sys.stderr)
        return None

    # 按 parent_observation_id 建树
    obs_map: dict[str, dict] = {}
    parent_map: dict[str, list[dict]] = defaultdict(list)
    roots: list[dict] = []

    for o in obs_list:
        d = _obs_to_dict(o)
        obs_map[d["id"]] = d
        pid = getattr(o, "parent_observation_id", None)
        if pid and pid in obs_map:
            # parent 已在前面处理过
            parent_map[pid].append(d)
        elif pid:
            # parent 还未处理，暂存
            parent_map[pid].append(d)
        else:
            roots.append(d)

    # 挂载子节点
    def attach(children: list[dict]) -> None:
        for c in children:
            cid = c["id"]
            if cid in parent_map:
                c["children"] = parent_map[cid]
                attach(c["children"])

    attach(roots)

    return {
        "trace_id": trace_id,
        "observations": roots,
    }


# ── 终端输出 ──

def _print_tree(nodes: list[dict], indent: int = 0) -> None:
    for n in nodes:
        prefix = "  " * indent + ("└── " if indent > 0 else "")
        kind_tag = "[GEN]" if n["kind"] == "generation" else "[SPAN]"
        dur = f"({n.get('duration_ms', 0)}ms)" if n.get("duration_ms") else ""
        model_tag = f" model={n['model']}" if n["model"] else ""
        print(f"{prefix}{kind_tag} {n['name']} {dur}{model_tag}")

        # 打印关键字段
        _input = n.get("input")
        _output = n.get("output")
        if _input and isinstance(_input, dict):
            _show = {k: v for k, v in _input.items() if k not in ("kb_ids",)}
            if _show:
                print(f"{'  ' * (indent+1)}in : {_truncate_dict(_show, 120)}")
        if _output and isinstance(_output, dict):
            _show = {k: v for k, v in _output.items() if k not in ("chunk_ids",)}
            if _show:
                print(f"{'  ' * (indent+1)}out: {_truncate_dict(_show, 120)}")
            if "chunk_ids" in _output:
                ids = _output["chunk_ids"]
                print(f"{'  ' * (indent+1)}chunk_ids: [{len(ids)}] {ids[:3]}{'...' if len(ids) > 3 else ''}")

        if n["children"]:
            _print_tree(n["children"], indent + 1)


def _truncate_dict(d: dict, max_len: int = 120) -> str:
    s = json.dumps(d, ensure_ascii=False, default=str)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


def _truncate_string(s: str, max_len: int = 80) -> str:
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


# ── main ──

def main():
    args = sys.argv[1:]
    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    trace_id: str | None = None
    output_json = False

    i = 0
    while i < len(args):
        if args[i] == "--json":
            output_json = True
        elif args[i] == "--last":
            i += 1
            n = int(args[i]) if i < len(args) else 5
            client = _init_client()
            traces = client.fetch_traces(limit=n)
            for t in traces.data[:1] if n == 1 else traces.data:
                print(f"{t.id} | {_truncate_string(t.name or '', 80)}")
            if n == 1 and traces.data:
                trace_id = traces.data[0].id
                break
            sys.exit(0)
        else:
            trace_id = args[i]
        i += 1

    if not trace_id:
        print("请提供 trace ID，或 --last N", file=sys.stderr)
        sys.exit(1)

    tree = fetch_trace_tree(trace_id)
    if tree is None:
        sys.exit(1)

    if output_json:
        print(json.dumps(tree, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"\nTrace: {trace_id}")
        print("=" * 80)
        _print_tree(tree["observations"])


if __name__ == "__main__":
    main()
