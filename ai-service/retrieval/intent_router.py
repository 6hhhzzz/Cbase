"""IntentRouter — 意图路由（规则前置 + LLM 兜底）。

架构师建议：
    - 企业知识库意图收敛，正则能覆盖 80%+ 场景
    - 模糊不清的 Query 才丢给 LLM
"""

import re

from common import get_logger
from llm.base import BaseLLM
from llm.prompts.intent import INTENT_PROMPT
from .models import IntentResult

logger = get_logger(__name__)

# 规则模式：意图 → 正则列表
_INTENT_PATTERNS: dict[str, list[str]] = {
    "compare": [
        r"(对比|区别|比较|vs\.?|哪一个更好|哪个更|有什么不同|有什么差别|差异)",
        r"(A和B|和.+相比|相较于)",
    ],
    "summary": [
        r"(总结|概述|概览|介绍一下|什么是|是什么|综合.*情况|整体.*情况)",
        r"(说一?下|讲一?下|介绍一?下)",
    ],
    "howto": [
        r"(怎么|如何|怎样|步骤|流程|方法|怎么做|怎么办|指南)",
    ],
}

# 意图 → top_k 映射
_INTENT_TOP_K: dict[str, int] = {
    "factoid": 5,
    "summary": 15,
    "compare": 8,
    "howto": 8,
}


class IntentRouter:
    """意图路由器。

    规则前置：检查正则模式。
    LLM 兜底：模糊不清时才调 LLM。
    """

    def __init__(self, llm: BaseLLM):
        self._llm = llm

    async def route(self, query: str) -> IntentResult:
        """路由查询意图。

        Args:
            query: 用户查询

        Returns:
            IntentResult（含意图标识、top_k、子查询）
        """
        # Step 1: 规则匹配
        for intent, patterns in _INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query):
                    return self._build_result(intent, query, method="rule")

        # Step 2: LLM 兜底
        try:
            llm_intent = await self._llm_classify(query)
            return self._build_result(llm_intent, query, method="llm")
        except Exception as e:
            logger.warning(f"LLM 意图分类失败，默认 factoid: {e}")
            return self._build_result("factoid", query, method="fallback")

    def _build_result(self, intent: str, query: str, method: str) -> IntentResult:
        """构建意图结果。"""
        top_k = _INTENT_TOP_K.get(intent, 5)
        sub_queries = []

        if intent == "compare":
            # 尝试拆为子查询（简单的基于"和"、"与"拆分）
            sub_queries = self._split_compare_query(query)

        return IntentResult(
            intent=intent,
            method=method,
            top_k=top_k,
            sub_queries=sub_queries,
        )

    def _split_compare_query(self, query: str) -> list[str]:
        """尝试拆分对比查询为子查询。"""
        # 简单策略：按"和"、"与"、"vs"拆分
        parts = re.split(r"\s*(?:和|与|vs\.?|VS\.?)\s*", query)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 2:
            return parts
        return []

    async def _llm_classify(self, query: str) -> str:
        """LLM 零样本分类。"""
        prompt = INTENT_PROMPT.render(query=query)
        response_wrapper = await self._llm.generate_content(prompt)
        response = (
            response_wrapper.content
            if hasattr(response_wrapper, "content")
            else str(response_wrapper)
        )
        response = response.strip().lower()

        for intent in ["factoid", "summary", "compare", "howto"]:
            if intent in response:
                return intent

        return "factoid"
