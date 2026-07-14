#!/usr/bin/env python3
"""端到端 DAG 测试 — 验证复杂查询走 DAG 路径。

使用真实 LLM（从环境变量或 llm.yaml 获取配置）测试完整链路：
  QueryPlanner.plan() → DAG 拆解 → Orchestrator 执行

不启动服务器，直接在 Python 进程中测试核心组件。

用法:
    uv run python scripts/test_dag_e2e.py

前提条件:
    - DASHSCOPE_API_KEY 环境变量已设置（或 .env 中配置）
    - PostgreSQL + pgvector 已启动且有测试数据
"""

import asyncio
import json
import os
import sys

# 将 ai-service 加入 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ai-service"))

from common import setup_logging
from core.config import load_settings
from llm.factory import ModelFactory
from llm.model_pool import ModelPool
from retrieval.query_planner import QueryPlanner


# 测试用例：简单 vs 复杂查询
TEST_CASES = [
    # (查询, 预期复杂度)
    ("什么是 Kubernetes", "simple"),
    ("如何配置 Nginx 反向代理", "simple"),
    ("对比一下 Kubernetes 和 Docker Swarm 在服务发现机制上的区别，并给出选型建议", "complex"),
    (
        "我们目前使用的服务网格方案有什么常见隐患，如果要迁移到 Cilium 需要改哪些配置",
        "complex",
    ),
    ("列出过去三个月所有安全相关的更新和漏洞修复", "complex"),
]


async def test_planner():
    """测试 QueryPlanner 是否对复杂查询生成 DAG。"""
    setup_logging()

    # 初始化 LLM
    settings = load_settings()
    java_url = os.environ.get("KES_JAVA_URL", "http://localhost:8080")
    model_pool = ModelPool(java_base_url=java_url)

    try:
        await model_pool.initialize()
        llm = model_pool.get_llm("chat")
        print(f"[OK] ModelPool 加载成功: {llm.get_model_name()}")
    except Exception as e:
        print(f"[WARN] ModelPool 失败 ({e})，降级 llm.yaml")
        llm = ModelFactory.create_llm(settings.llm)
        print(f"[OK] 降级 LLM: {llm.get_model_name()}")

    planner = QueryPlanner(llm)

    results = []
    for query, expected in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"查询: {query}")
        print(f"预期复杂度: {expected}")

        plan = await planner.plan(query)
        print(f"实际复杂度: {plan.complexity}")
        print(f"方法: {plan.method}")
        print(f"rewritten_query: {plan.rewritten_query[:80]}...")

        if plan.complexity == "complex":
            print(f"子查询数: {len(plan.sub_queries)}")
            for sq in plan.sub_queries:
                deps = f" (依赖: {sq.depends_on})" if sq.depends_on else ""
                hyde_flag = " [HyDE]" if sq.hyde else ""
                ctx_flag = " [needs_context]" if sq.needs_context else ""
                print(f"  {sq.id}: {sq.query[:60]}{deps}{hyde_flag}{ctx_flag}")
                print(f"    目的: {sq.purpose}")

        # 验证
        match = plan.complexity == expected
        status = "✓" if match else "✗ (不符合预期)"
        print(f"结果: {status}")

        # 对 complex 查询做额外校验
        if plan.complexity == "complex":
            if len(plan.sub_queries) >= 2:
                print(f"  ✓ 子查询数 >= 2")
            else:
                print(f"  ✗ 子查询数不足: {len(plan.sub_queries)}")

            # 检查有无循环
            from retrieval.query_planner import QueryPlanner as QP
            qp = QP(llm=None)  # 不需要 LLM，只做校验
            if qp._has_cycle(plan.sub_queries):
                print(f"  ✗ DAG 有环！")
            else:
                print(f"  ✓ DAG 无环")

            # 检查拓扑排序
            from retrieval.orchestrator import RetrievalOrchestrator
            orch = RetrievalOrchestrator.__new__(RetrievalOrchestrator)
            waves = orch._topological_sort(plan.sub_queries)
            print(f"  Wave 数: {len(waves)}")
            for i, wave in enumerate(waves):
                wave_ids = [sq.id for sq in wave]
                print(f"    Wave {i}: {wave_ids}")

        results.append((query, plan))

    # 总结
    print(f"\n{'='*60}")
    print(f"总结")
    simple_count = sum(1 for _, p in results if p.complexity == "simple")
    complex_count = sum(1 for _, p in results if p.complexity == "complex")
    print(f"Simple: {simple_count}/{len(results)}, Complex: {complex_count}/{len(results)}")

    # 验证所有 complex 查询都生成了有效 DAG
    for query, plan in results:
        if plan.complexity == "complex":
            assert len(plan.sub_queries) >= 2, f"DAG 子查询不足: {query}"
            assert plan.method != "fallback", f"DAG 降级了: {query}"

    print("\n✓ 所有断言通过!")


if __name__ == "__main__":
    asyncio.run(test_planner())
