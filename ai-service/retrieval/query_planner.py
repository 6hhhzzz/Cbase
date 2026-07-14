"""QueryPlanner — LLM 驱动的 DAG 拆解 + HyDE 判断（v11）。

一次 LLM 调用完成：
  1. 复杂度判定（simple/complex）
  2. DAG 拆解（子查询 + 依赖关系）
  3. HyDE 标记（抽象查询 → hyde=true）
  4. needs_context 标记（串行依赖是否需要前一步检索结果改写）

替代旧 IntentRouter（只做"标签→top_k"）。
"""

import json
import re
from typing import Any

from common import get_logger
from llm.base import BaseLLM
from llm.prompts.query_plan import QUERY_PLAN_PROMPT
from .models import QueryPlan, SubQuery

logger = get_logger(__name__)

# DAG 安全上限
MAX_SUB_QUERIES = 6


class QueryPlanner:
    """查询计划器 — LLM 驱动的查询分析 + DAG 拆解。

    用法::

        planner = QueryPlanner(llm)
        plan = await planner.plan(query, history_len=3)
        # plan.complexity → "simple" | "complex"
        # plan.sub_queries → list[SubQuery]
    """

    def __init__(self, llm: BaseLLM):
        self._llm = llm

    async def plan(self, query: str, history: list[dict] | None = None,
                   tracer: Any = None, trace_parent: Any = None) -> QueryPlan:
        """分析查询并生成执行计划（合并指代消解 + 复杂度判定 + DAG 拆解）。

        Args:
            query: 用户原始查询
            history: 对话历史 [{"role": "user/assistant", "content": "..."}]
            tracer: LangfuseTracer（可选，用于 LLM 调用埋点）
            trace_parent: Langfuse trace/span 对象（generation span 的 parent）

        Returns:
            QueryPlan（complexity + rewritten_query + keywords + DAG sub_queries）
        """
        # 构建历史文本
        history_text = "（首轮查询，无历史上下文）"
        if history:
            recent = history[-6:]  # 最近 6 条消息（3 轮对话）
            lines = []
            for msg in recent:
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")[:200]  # 截断每条消息
                lines.append(f"[{role}]: {content}")
            if lines:
                history_text = "\n".join(lines)

        try:
            prompt = QUERY_PLAN_PROMPT.render(query=query, history=history_text)
            model_name = getattr(self._llm, 'get_model_name', lambda: 'unknown')()

            # ── Langfuse: planner generation span ──
            _gen_span = None
            if tracer is not None and trace_parent is not None:
                _gen_span = tracer.generation(
                    parent=trace_parent, name="planner", model=model_name,
                    input_data=prompt,
                )

            response_wrapper = await self._llm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )

            plan = self._parse_response(response, query)

            # ── Langfuse: update planner span with output ──
            if _gen_span is not None:
                tracer.update_span(_gen_span, output={
                    "complexity": plan.complexity,
                    "rewritten_query": plan.rewritten_query,
                    "keywords": plan.keywords,
                    "sub_query_count": len(plan.sub_queries),
                })

            logger.info(
                f"QueryPlan: complexity={plan.complexity}, "
                f"keywords={plan.keywords}, sub_queries={len(plan.sub_queries)}"
            )
            return plan

        except Exception as e:
            logger.warning(f"QueryPlanner 失败，降级为 simple: {e}")
            return QueryPlan(
                complexity="simple",
                rewritten_query=query,
                method="fallback",
                top_k=5,
            )

    # ---- 解析 ----

    def _parse_response(self, response: str, fallback_query: str) -> QueryPlan:
        """解析 LLM 响应为 QueryPlan。"""
        data = self._extract_json(response)

        if not data:
            logger.warning("无法解析 QueryPlanner 响应，降级为 simple")
            return QueryPlan(
                complexity="simple",
                rewritten_query=fallback_query,
                method="fallback",
                top_k=5,
            )

        complexity = data.get("complexity", "simple")
        rewritten_query = data.get("rewritten_query", fallback_query)
        keywords = data.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        top_k = data.get("top_k", 5)
        raw_sub_queries = data.get("sub_queries", [])

        sub_queries = []
        if complexity == "complex" and raw_sub_queries:
            for sq_data in raw_sub_queries:
                # 解析 extract_entities（可能是 list[dict] 或 None）
                extract_entities = sq_data.get("extract_entities")
                if extract_entities and isinstance(extract_entities, list):
                    extract_entities = [
                        e for e in extract_entities
                        if isinstance(e, dict) and "key" in e
                    ]
                else:
                    extract_entities = None

                sub_queries.append(SubQuery(
                    id=sq_data.get("id", f"q{len(sub_queries)}"),
                    query=sq_data.get("query", ""),
                    query_template=sq_data.get("query_template", ""),
                    depends_on=sq_data.get("depends_on", []),
                    purpose=sq_data.get("purpose", ""),
                    hyde=sq_data.get("hyde", False),
                    needs_context=sq_data.get("needs_context", False),
                    extract_entities=extract_entities,
                    extract_reasoning=sq_data.get("extract_reasoning"),
                    extract_filters=sq_data.get("extract_filters"),
                ))

        # 校验
        sub_queries = self._validate_dag(sub_queries)

        # 如果校验后没有有效子查询，降级
        if complexity == "complex" and not sub_queries:
            complexity = "simple"

        return QueryPlan(
            complexity=complexity,
            rewritten_query=rewritten_query,
            keywords=keywords,
            sub_queries=sub_queries,
            method="llm",
            top_k=top_k,
        )

    def _extract_json(self, response: str) -> dict | None:
        """从 LLM 响应中提取 JSON 对象。"""
        response = response.strip()

        # 去掉可能的 markdown 代码块标记
        if response.startswith("```"):
            response = re.sub(r"^```(?:json)?\s*", "", response)
            response = re.sub(r"\s*```$", "", response)

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 JSON 对象
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    # ---- DAG 校验 ----

    def _validate_dag(self, sub_queries: list[SubQuery]) -> list[SubQuery]:
        """校验 DAG 合法性：去重、截断、循环检测、引用检查。

        Args:
            sub_queries: 原始子查询列表

        Returns:
            校验后的子查询列表（可能被截断或清空）
        """
        if not sub_queries:
            return []

        # 1. 数量上限
        if len(sub_queries) > MAX_SUB_QUERIES:
            logger.warning(
                f"子查询数 {len(sub_queries)} 超过上限 {MAX_SUB_QUERIES}，截断"
            )
            sub_queries = sub_queries[:MAX_SUB_QUERIES]

        # 2. ID 去重
        seen_ids: set[str] = set()
        unique: list[SubQuery] = []
        for sq in sub_queries:
            if sq.id not in seen_ids:
                seen_ids.add(sq.id)
                unique.append(sq)
            else:
                logger.warning(f"重复子查询 id={sq.id}，跳过")
        sub_queries = unique

        # 3. 过滤空 query（但保留有 query_template 的模板子查询）
        sub_queries = [
            sq for sq in sub_queries
            if sq.query.strip() or (sq.needs_context and sq.query_template.strip())
        ]
        if not sub_queries:
            return []

        # 4. 收集所有有效 id
        valid_ids = {sq.id for sq in sub_queries}

        # 5. 检查 depends_on 引用有效性
        for sq in sub_queries:
            for dep_id in sq.depends_on:
                if dep_id not in valid_ids:
                    logger.warning(
                        f"子查询 {sq.id} 引用了不存在的依赖 {dep_id}，移除该依赖"
                    )
            # 过滤掉无效引用
            sq.depends_on[:] = [d for d in sq.depends_on if d in valid_ids]

        # 6. 循环依赖检测（DFS）
        if self._has_cycle(sub_queries):
            logger.warning("DAG 存在循环依赖，清空子查询让 DAG 失效")
            return []

        # 7. v12: needs_context 约束校验
        for sq in sub_queries:
            if sq.needs_context:
                # 必须有 extract_entities
                if not sq.extract_entities:
                    logger.warning(
                        f"子查询 {sq.id} needs_context=true 但 extract_entities 为空，"
                        f"降级为 needs_context=false"
                    )
                    sq.needs_context = False
                    sq.extract_entities = None
                    continue

                # 必须有 query_template
                if not sq.query_template.strip():
                    logger.warning(
                        f"子查询 {sq.id} needs_context=true 但 query_template 为空，"
                        f"降级为 needs_context=false"
                    )
                    sq.needs_context = False
                    sq.extract_entities = None
                    continue

                # extract_entities 的 key 必须被 query_template 引用
                for ent in sq.extract_entities:
                    key = ent.get("key", "")
                    ref = f"{{{{extracted.{key}}}}}"
                    if ref not in sq.query_template:
                        logger.warning(
                            f"子查询 {sq.id}: extract_entities key='{key}' "
                            f"在 query_template 中未被引用，移除该实体"
                        )
                    else:
                        # 确认 query_template 中的占位符有对应的 extract_entities
                        pass

                # extract_reasoning 非空时长度 ≥ 10
                if sq.extract_reasoning and len(sq.extract_reasoning.strip()) < 10:
                    sq.extract_reasoning = None

        # 8. v13: 对比/聚合子查询依赖链告警
        _comparison_kw = {"对比", "差异", "区别", "不同", "比较", "汇总", "综合", "分别"}
        for sq in sub_queries:
            purpose_q = ((sq.purpose or "") + (sq.query or "")).lower()
            is_comparison = any(kw in purpose_q for kw in _comparison_kw)
            if is_comparison and not sq.depends_on and len(sub_queries) >= 3:
                logger.warning(
                    f"子查询 {sq.id} 可能是对比/聚合查询但无依赖关系: "
                    f"purpose='{sq.purpose}', depends_on={sq.depends_on}"
                )

        return sub_queries

    def _has_cycle(self, sub_queries: list[SubQuery]) -> bool:
        """DFS 检测有向图中是否存在环。

        使用三色标记法: 0=未访问, 1=访问中, 2=已完成。
        """
        id_to_idx = {sq.id: i for i, sq in enumerate(sub_queries)}
        color = [0] * len(sub_queries)  # 0=white, 1=gray, 2=black

        def dfs(idx: int) -> bool:
            if color[idx] == 1:  # gray → 回边，有环
                return True
            if color[idx] == 2:  # black → 已完成
                return False

            color[idx] = 1  # visiting
            for dep_id in sub_queries[idx].depends_on:
                dep_idx = id_to_idx.get(dep_id)
                if dep_idx is not None and dfs(dep_idx):
                    return True
            color[idx] = 2  # done
            return False

        for i in range(len(sub_queries)):
            if dfs(i):
                return True

        return False
