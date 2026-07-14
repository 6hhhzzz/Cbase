"""QueryPreprocessor — 三合一查询预处理（Stage 1, v12）。

一次 SLM 调用完成指代消解 + 省略补全 + 语义补全。

与现有 QueryRewriter 的关系：
  QueryPreprocessor 优先使用，QueryRewriter 保留为 fallback。
  retrieve() 中优先调用 preprocessor，失败时回退 rewriter。

质量防御：
  - 过度改写检测：改写后长度 > 原始 50% 且超过 20 字 → 丢弃
  - 语义漂移检测：原始有疑问词但改写后变成纯名词短语 → 丢弃
  - 终极保底：任何降级触发时 final_query = original_query
"""

import json

from common import get_logger
from llm.base import BaseLLM
from llm.prompts.preprocess import PREPROCESS_PROMPT

logger = get_logger(__name__)

# 改写质量阈值
MAX_LENGTH_RATIO = 1.5    # 改写后最长 = 原始 × 1.5
MIN_LENGTH_DIFF = 20      # 绝对长度差阈值（避免短 query 误触发）
QUESTION_MARKERS = ["怎么", "如何", "为什么", "怎样", "?", "？", "吗", "呢"]


class QueryPreprocessor:
    """查询预处理器 — 三合一 SLM 预处理。

    用法::

        preprocessor = QueryPreprocessor(slm)
        result = await preprocessor.preprocess(query, history)
        # → {"resolved_query": "...", "additions": {...}}
    """

    def __init__(self, slm: BaseLLM):
        self._slm = slm

    async def preprocess(
        self, query: str, history: list[dict] | None = None
    ) -> dict:
        """预处理查询（三合一 SLM 调用）。

        Args:
            query: 用户原始查询
            history: 对话历史 [{"role": "user/assistant", "content": "..."}]

        Returns:
            {
                "resolved_query": str,   # 改写后的完整查询
                "original_query": str,    # 保留原始查询
                "used_fallback": bool,    # 是否降级到原始 query
                "additions": dict,        # 改写说明
            }
        """
        if not history:
            return self._noop_result(query)

        try:
            # 历史截断：最近 5 轮 + 摘要锚点
            truncated_history = self._truncate_history(history)

            prompt = PREPROCESS_PROMPT.render(query=query, history=truncated_history)
            response_wrapper = await self._slm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )

            data = self._parse_response(response, query)

            # 质量校验
            resolved = data.get("resolved_query", query)
            validated = self._validate(resolved, query)

            logger.info(
                f"QueryPreprocess: '{query[:40]}' → '{validated[:40]}' "
                f"(used_fallback={validated != resolved})"
            )

            return {
                "resolved_query": validated,
                "original_query": query,
                "used_fallback": validated != resolved,
                "additions": data.get("additions", {}),
            }

        except Exception as e:
            logger.warning(f"QueryPreprocess 失败，回退原始 query: {e}")
            return self._noop_result(query)

    def _noop_result(self, query: str) -> dict:
        return {
            "resolved_query": query,
            "original_query": query,
            "used_fallback": True,
            "additions": {},
        }

    def _truncate_history(self, history: list[dict], max_recent: int = 5) -> str:
        """截断历史：最近 N 轮原文，其余丢弃。

        对于更长历史，依赖 HistoryManager 的摘要机制。
        这里不做摘要生成，因为那是 SummaryEngine 的职责。
        """
        recent = history[-(max_recent * 2):]  # *2 因为每轮有 user+assistant
        lines = []
        for msg in recent:
            role = "用户" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")[:200]  # 每条截断 200 字
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _parse_response(self, response: str, fallback: str) -> dict:
        """解析 SLM 响应为 dict。"""
        response = response.strip()
        if response.startswith("```"):
            import re
            response = re.sub(r"^```(?:json)?\s*", "", response)
            response = re.sub(r"\s*```$", "", response)

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        logger.warning(f"无法解析预处理响应: {response[:200]}")
        return {"resolved_query": fallback, "additions": {}}

    def _validate(self, resolved: str, original: str) -> str:
        """校验改写质量。通过返回 resolved，不通过返回 original。"""
        if not resolved or len(resolved.strip()) < 2:
            return original

        # 防御 1: 过度改写（长度启发式）
        if len(resolved) > len(original) * MAX_LENGTH_RATIO and (
            len(resolved) - len(original) > MIN_LENGTH_DIFF
        ):
            logger.info(
                f"改写长度异常 ({len(original)}→{len(resolved)})，"
                f"判定为过度改写，降级原始 query"
            )
            return original

        # 防御 2: 语义漂移（问句→纯名词短语）
        if self._has_question_markers(original) and not self._has_question_markers(resolved):
            # 原始是问句，改写后变成纯名词/dict 键
            if not any(m in resolved for m in ["介绍", "说明", "解释", "分析", "查询", "搜索"]):
                logger.info(f"语义漂移: '{original[:30]}' → 纯名词，降级原始 query")
                return original

        return resolved

    @staticmethod
    def _has_question_markers(text: str) -> bool:
        return any(m in text for m in QUESTION_MARKERS)
