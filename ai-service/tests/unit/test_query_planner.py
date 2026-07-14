"""QueryPlanner 测试 — DAG 拆解 + HyDE 标记 + 校验。

测试覆盖:
  - QueryPlan/SubQuery 数据模型
  - _extract_json: 正常 JSON / markdown 包裹 / 解析失败
  - _validate_dag: 去重 / 截断 / 循环检测 / 引用检查
  - plan(): simple 查询 / complex 查询 / LLM 失败降级
  - 拓扑排序 (orchestrator._topological_sort)
"""

import json
import pytest
from unittest.mock import AsyncMock

from retrieval.models import QueryPlan, SubQuery, IntentResult
from retrieval.query_planner import QueryPlanner, MAX_SUB_QUERIES


# ================================================================
# SubQuery / QueryPlan 数据模型
# ================================================================

class TestSubQueryModel:
    """SubQuery 数据模型测试。"""

    def test_defaults(self):
        sq = SubQuery(id="q1", query="测试查询")
        assert sq.id == "q1"
        assert sq.query == "测试查询"
        assert sq.depends_on == []
        assert sq.purpose == ""
        assert sq.hyde is False
        assert sq.needs_context is False

    def test_with_dependencies(self):
        sq = SubQuery(
            id="q2",
            query="替代方案",
            depends_on=["q1"],
            purpose="查找替代方案",
            hyde=True,
            needs_context=True,
        )
        assert sq.depends_on == ["q1"]
        assert sq.hyde is True
        assert sq.needs_context is True

    def test_serializable(self):
        """SubQuery 应可 JSON 序列化。"""
        sq = SubQuery(id="q1", query="测试", depends_on=["q0"], hyde=True)
        d = {
            "id": sq.id,
            "query": sq.query,
            "depends_on": sq.depends_on,
            "purpose": sq.purpose,
            "hyde": sq.hyde,
            "needs_context": sq.needs_context,
        }
        assert json.dumps(d)  # 不抛异常


class TestQueryPlanModel:
    """QueryPlan 数据模型测试。"""

    def test_default_simple(self):
        plan = QueryPlan()
        assert plan.complexity == "simple"
        assert plan.rewritten_query == ""
        assert plan.sub_queries == []
        assert plan.method == "llm"
        assert plan.top_k == 5

    def test_complex_with_sub_queries(self):
        sq1 = SubQuery(id="q1", query="A 的优缺点")
        sq2 = SubQuery(id="q2", query="B 的优缺点")
        plan = QueryPlan(
            complexity="complex",
            rewritten_query="对比 A 和 B",
            sub_queries=[sq1, sq2],
        )
        assert plan.complexity == "complex"
        assert len(plan.sub_queries) == 2

    def test_intent_result_alias(self):
        """IntentResult 是 QueryPlan 的向后兼容别名。"""
        result = IntentResult(complexity="simple", rewritten_query="测试", top_k=10)
        assert result.complexity == "simple"
        assert result.top_k == 10


# ================================================================
# _extract_json
# ================================================================

class TestExtractJson:
    """JSON 提取测试。"""

    def _extract(self, response):
        planner = QueryPlanner(llm=None)
        return planner._extract_json(response)

    def test_valid_json(self):
        data = self._extract('{"complexity": "simple", "rewritten_query": "测试"}')
        assert data == {"complexity": "simple", "rewritten_query": "测试"}

    def test_json_with_markdown_fence(self):
        response = '```json\n{"complexity": "complex", "sub_queries": []}\n```'
        data = self._extract(response)
        assert data["complexity"] == "complex"

    def test_json_with_plain_fence(self):
        response = '```\n{"complexity": "simple"}\n```'
        data = self._extract(response)
        assert data == {"complexity": "simple"}

    def test_json_embedded_in_text(self):
        response = '分析结果如下：\n{"complexity": "simple", "rewritten_query": "如何配置Nginx"}\n以上是分析结果。'
        data = self._extract(response)
        assert data is not None
        assert data["complexity"] == "simple"

    def test_invalid_json(self):
        data = self._extract("这不是合法的 JSON 响应")
        assert data is None

    def test_empty_response(self):
        data = self._extract("")
        assert data is None

    def test_partial_json(self):
        """不完整的 JSON 返回 None。"""
        data = self._extract('{"complexity": "simple"')
        assert data is None


# ================================================================
# _validate_dag
# ================================================================

class TestValidateDag:
    """DAG 校验测试。"""

    def _validate(self, sub_queries):
        planner = QueryPlanner(llm=None)
        return planner._validate_dag(sub_queries)

    def test_empty(self):
        assert self._validate([]) == []

    def test_valid_dag(self):
        sqs = [
            SubQuery(id="q1", query="A 的特性"),
            SubQuery(id="q2", query="B 的特性"),
        ]
        result = self._validate(sqs)
        assert len(result) == 2

    def test_truncate_excess(self):
        """超过 MAX_SUB_QUERIES 应截断。"""
        sqs = [
            SubQuery(id=f"q{i}", query=f"查询{i}")
            for i in range(MAX_SUB_QUERIES + 3)
        ]
        result = self._validate(sqs)
        assert len(result) == MAX_SUB_QUERIES

    def test_dedup_ids(self):
        """重复 id 应去重（保留第一个）。"""
        sqs = [
            SubQuery(id="q1", query="查询1"),
            SubQuery(id="q1", query="重复的查询1"),
            SubQuery(id="q2", query="查询2"),
        ]
        result = self._validate(sqs)
        assert len(result) == 2
        assert result[0].query == "查询1"  # 保留第一个

    def test_filter_empty_query(self):
        """空 query 的子查询应被过滤。"""
        sqs = [
            SubQuery(id="q1", query="有效查询"),
            SubQuery(id="q2", query="   "),
            SubQuery(id="q3", query=""),
        ]
        result = self._validate(sqs)
        assert len(result) == 1
        assert result[0].id == "q1"

    def test_all_empty_queries(self):
        sqs = [SubQuery(id="q1", query=""), SubQuery(id="q2", query="  ")]
        assert self._validate(sqs) == []

    def test_invalid_depends_on_reference(self):
        """引用了不存在的依赖 id → 该依赖被过滤。"""
        sqs = [
            SubQuery(id="q1", query="查询1"),
            SubQuery(id="q2", query="查询2", depends_on=["q1", "q99"]),
        ]
        result = self._validate(sqs)
        assert len(result) == 2
        # q99 被移除
        assert result[1].depends_on == ["q1"]

    def test_all_invalid_depends_on(self):
        """所有依赖都无效 → depends_on 变为空。"""
        sqs = [
            SubQuery(id="q1", query="查询1", depends_on=["q_nonexistent"]),
        ]
        result = self._validate(sqs)
        assert len(result) == 1
        assert result[0].depends_on == []

    def test_cycle_detection_simple(self):
        """简单循环：A→B→A。"""
        sqs = [
            SubQuery(id="q1", query="A", depends_on=["q2"]),
            SubQuery(id="q2", query="B", depends_on=["q1"]),
        ]
        result = self._validate(sqs)
        assert result == []  # 循环被拒绝

    def test_cycle_detection_self_loop(self):
        """自环：A→A。"""
        sqs = [
            SubQuery(id="q1", query="A", depends_on=["q1"]),
        ]
        result = self._validate(sqs)
        assert result == []

    def test_cycle_detection_three_nodes(self):
        """三节点循环：A→B→C→A。"""
        sqs = [
            SubQuery(id="q1", query="A", depends_on=["q2"]),
            SubQuery(id="q2", query="B", depends_on=["q3"]),
            SubQuery(id="q3", query="C", depends_on=["q1"]),
        ]
        result = self._validate(sqs)
        assert result == []

    def test_dag_no_cycle(self):
        """合法的 DAG：A→B→C（无环）。"""
        sqs = [
            SubQuery(id="q1", query="A"),
            SubQuery(id="q2", query="B", depends_on=["q1"]),
            SubQuery(id="q3", query="C", depends_on=["q1", "q2"]),
        ]
        result = self._validate(sqs)
        assert len(result) == 3

    def test_multi_parent_dag(self):
        """多入度无环 DAG。"""
        sqs = [
            SubQuery(id="q1", query="背景知识"),
            SubQuery(id="q2", query="相关概念"),
            SubQuery(id="q3", query="综合分析", depends_on=["q1", "q2"]),
        ]
        result = self._validate(sqs)
        assert len(result) == 3


# ================================================================
# _parse_response
# ================================================================

class TestParseResponse:
    """LLM 响应解析测试。"""

    def _parse(self, response, fallback="原始查询"):
        planner = QueryPlanner(llm=None)
        return planner._parse_response(response, fallback)

    def test_simple_plan(self):
        response = json.dumps({
            "complexity": "simple",
            "rewritten_query": "如何配置 Nginx 反向代理",
            "top_k": 5,
            "sub_queries": [],
        })
        plan = self._parse(response)
        assert plan.complexity == "simple"
        assert plan.rewritten_query == "如何配置 Nginx 反向代理"
        assert plan.sub_queries == []

    def test_complex_plan_with_dag(self):
        response = json.dumps({
            "complexity": "complex",
            "rewritten_query": "对比 K8s 和 Docker Swarm 的服务发现机制",
            "top_k": 8,
            "sub_queries": [
                {"id": "q1", "query": "Kubernetes 服务发现机制", "depends_on": [],
                 "purpose": "了解 K8s 服务发现", "hyde": True, "needs_context": False},
                {"id": "q2", "query": "Docker Swarm 服务发现机制", "depends_on": [],
                 "purpose": "了解 Swarm 服务发现", "hyde": True, "needs_context": False},
            ],
        })
        plan = self._parse(response)
        assert plan.complexity == "complex"
        assert len(plan.sub_queries) == 2
        assert plan.sub_queries[0].id == "q1"
        assert plan.sub_queries[0].hyde is True
        assert plan.sub_queries[1].hyde is True
        # 对比查询两个子查询无依赖
        assert plan.sub_queries[0].depends_on == []
        assert plan.sub_queries[1].depends_on == []

    def test_multi_hop_plan(self):
        """多跳推理：先找问题再找解决方案。"""
        response = json.dumps({
            "complexity": "complex",
            "rewritten_query": "当前服务网格方案有什么隐患，如何迁移到 Cilium",
            "top_k": 8,
            "sub_queries": [
                {"id": "q1", "query": "服务网格方案的风险和隐患", "depends_on": [],
                 "purpose": "找出当前方案的问题", "hyde": True, "needs_context": False,
                 "query_template": "", "extract_entities": None,
                 "extract_reasoning": None, "extract_filters": None},
                {"id": "q2", "query": "", "depends_on": ["q1"],
                 "query_template": "{{extracted.product_name}} 迁移到 Cilium 的配置要求",
                 "purpose": "基于问题找迁移方案", "hyde": False, "needs_context": True,
                 "extract_entities": [{"key": "product_name", "description": "服务网格产品名称"}],
                 "extract_reasoning": "从上游结果中提取当前架构的约束条件",
                 "extract_filters": ["valid_after"]},
            ],
        })
        plan = self._parse(response)
        assert plan.complexity == "complex"
        assert len(plan.sub_queries) == 2
        assert plan.sub_queries[1].depends_on == ["q1"]
        assert plan.sub_queries[1].needs_context is True
        assert plan.sub_queries[1].extract_entities is not None
        assert len(plan.sub_queries[1].extract_entities) == 1

    def test_invalid_json_fallback(self):
        plan = self._parse("乱七八糟的响应", fallback="测试查询")
        assert plan.complexity == "simple"
        assert plan.method == "fallback"
        assert plan.rewritten_query == "测试查询"

    def test_empty_sub_queries_for_complex(self):
        """complex 但无有效子查询 → 降级为 simple。"""
        response = json.dumps({
            "complexity": "complex",
            "rewritten_query": "测试",
            "sub_queries": [],
        })
        plan = self._parse(response)
        assert plan.complexity == "simple"

    def test_cycle_in_llm_response(self):
        """LLM 返回了有循环的 DAG → 校验后降级。"""
        response = json.dumps({
            "complexity": "complex",
            "rewritten_query": "测试",
            "sub_queries": [
                {"id": "q1", "query": "A", "depends_on": ["q2"]},
                {"id": "q2", "query": "B", "depends_on": ["q1"]},
            ],
        })
        plan = self._parse(response)
        assert plan.complexity == "simple"  # 降级

    def test_hyde_false_with_specific_code(self):
        """含编号/专有名词的子查询 → hyde=false。"""
        response = json.dumps({
            "complexity": "complex",
            "rewritten_query": "查询 KES 和 RAGFlow 的区别",
            "sub_queries": [
                {"id": "q1", "query": "KES-2025-001 配置说明", "depends_on": [],
                 "hyde": False, "needs_context": False},
                {"id": "q2", "query": "RAGFlow 配置说明", "depends_on": [],
                 "hyde": False, "needs_context": False},
            ],
        })
        plan = self._parse(response)
        assert plan.sub_queries[0].hyde is False


# ================================================================
# plan() — 端到端
# ================================================================

class TestPlanMethod:
    """plan() 端到端测试。"""

    @pytest.fixture
    def mock_llm(self):
        llm = AsyncMock()
        llm.generate_content.return_value.content = json.dumps({
            "complexity": "simple",
            "rewritten_query": "什么是 Kubernetes",
            "top_k": 5,
            "sub_queries": [],
        })
        return llm

    @pytest.mark.asyncio
    async def test_plan_simple(self, mock_llm):
        planner = QueryPlanner(llm=mock_llm)
        plan = await planner.plan("什么是 Kubernetes")
        assert plan.complexity == "simple"
        assert plan.method == "llm"

    @pytest.mark.asyncio
    async def test_plan_complex(self, mock_llm):
        mock_llm.generate_content.return_value.content = json.dumps({
            "complexity": "complex",
            "rewritten_query": "比较 K8s 和 Swarm",
            "sub_queries": [
                {"id": "q1", "query": "K8s 特性", "depends_on": []},
                {"id": "q2", "query": "Swarm 特性", "depends_on": []},
            ],
        })
        planner = QueryPlanner(llm=mock_llm)
        plan = await planner.plan("K8s 和 Docker Swarm 有什么区别")
        assert plan.complexity == "complex"
        assert len(plan.sub_queries) == 2

    @pytest.mark.asyncio
    async def test_plan_llm_failure_fallback(self, mock_llm):
        """LLM 调用失败 → 降级为 simple。"""
        mock_llm.generate_content.side_effect = Exception("API 不可用")
        planner = QueryPlanner(llm=mock_llm)
        plan = await planner.plan("任意查询")
        assert plan.complexity == "simple"
        assert plan.method == "fallback"
        assert plan.top_k == 5


# ================================================================
# 拓扑排序 (orchestrator._topological_sort)
# ================================================================

class TestTopologicalSort:
    """DAG 拓扑排序测试（逻辑在 Orchestrator 中）。"""

    def _sort(self, sub_queries):
        from retrieval.dag_executor import DAGExecutor
        # 直接测 DAGExecutor 的拓扑排序（纯算法，无依赖）
        executor = DAGExecutor.__new__(DAGExecutor)
        return executor._topological_sort(sub_queries)

    def test_single_node(self):
        sqs = [SubQuery(id="q1", query="查询")]
        waves = self._sort(sqs)
        assert len(waves) == 1
        assert len(waves[0]) == 1
        assert waves[0][0].id == "q1"

    def test_independent_nodes_same_wave(self):
        """无依赖的节点应在同一 wave。"""
        sqs = [
            SubQuery(id="q1", query="A"),
            SubQuery(id="q2", query="B"),
            SubQuery(id="q3", query="C"),
        ]
        waves = self._sort(sqs)
        assert len(waves) == 1
        assert len(waves[0]) == 3

    def test_linear_chain(self):
        """A → B → C 线性依赖 → 3 个 wave。"""
        sqs = [
            SubQuery(id="q1", query="A"),
            SubQuery(id="q2", query="B", depends_on=["q1"]),
            SubQuery(id="q3", query="C", depends_on=["q2"]),
        ]
        waves = self._sort(sqs)
        assert len(waves) == 3
        assert waves[0][0].id == "q1"
        assert waves[1][0].id == "q2"
        assert waves[2][0].id == "q3"

    def test_diamond_dependency(self):
        """菱形依赖：q1、q2 并行 → q3。

        q1 ──┐
              ├──► q3
        q2 ──┘
        """
        sqs = [
            SubQuery(id="q1", query="A"),
            SubQuery(id="q2", query="B"),
            SubQuery(id="q3", query="C", depends_on=["q1", "q2"]),
        ]
        waves = self._sort(sqs)
        assert len(waves) == 2
        # Wave 0: q1, q2 并行
        assert {sq.id for sq in waves[0]} == {"q1", "q2"}
        # Wave 1: q3
        assert waves[1][0].id == "q3"

    def test_complex_dag(self):
        """复杂 DAG:
        q1 ──► q2 ──► q4
               q3 ──┘
        """
        sqs = [
            SubQuery(id="q1", query="背景"),
            SubQuery(id="q2", query="分析", depends_on=["q1"]),
            SubQuery(id="q3", query="案例"),
            SubQuery(id="q4", query="结论", depends_on=["q2", "q3"]),
        ]
        waves = self._sort(sqs)
        assert len(waves) == 3
        # Wave 0: q1, q3 并行（都无依赖）
        assert {sq.id for sq in waves[0]} == {"q1", "q3"}
        # Wave 1: q2（只依赖 q1）
        assert {sq.id for sq in waves[1]} == {"q2"}
        # Wave 2: q4（依赖 q2, q3）
        assert {sq.id for sq in waves[2]} == {"q4"}


# ================================================================
# _has_cycle
# ================================================================

class TestCycleDetection:
    """循环检测单元测试。"""

    def _has_cycle(self, sub_queries):
        planner = QueryPlanner(llm=None)
        return planner._has_cycle(sub_queries)

    def test_no_cycle(self):
        sqs = [
            SubQuery(id="q1", query="A"),
            SubQuery(id="q2", query="B", depends_on=["q1"]),
        ]
        assert not self._has_cycle(sqs)

    def test_simple_cycle(self):
        sqs = [
            SubQuery(id="q1", query="A", depends_on=["q2"]),
            SubQuery(id="q2", query="B", depends_on=["q1"]),
        ]
        assert self._has_cycle(sqs)

    def test_self_loop(self):
        sqs = [SubQuery(id="q1", query="A", depends_on=["q1"])]
        assert self._has_cycle(sqs)
