"""LLM Reranker — 无 GPU 时的降级 Reranker。

当 BGE-Reranker / Cohere Rerank 等交叉编码器不可用时，
使用 LLM 对候选文档进行重排序。

参考 RAGFlow 的 rerank_by_model 思路：
    1. 取 Top-M 候选（通常 20 以内）
    2. 批量发送给 LLM 打分
    3. 按分数重排
"""

import json

from common import get_logger
from llm.base import BaseLLM
from llm.prompts.rerank import RERANK_PROMPT

logger = get_logger(__name__)

# 每批最多发送给 LLM 的候选数
_BATCH_SIZE = 10


class LLMReranker:
    """LLM-based 降级 Reranker。

    用法::

        reranker = LLMReranker(llm)
        reranked = await reranker.rerank(query, candidates)
    """

    def __init__(self, llm: BaseLLM, batch_size: int = _BATCH_SIZE):
        self._llm = llm
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        candidates: list[dict],
    ) -> list[dict]:
        """对候选文档重排序。

        Args:
            query: 用户查询
            candidates: 候选文档列表 [{"id": ..., "content": ...}, ...]

        Returns:
            按相关性分数降序排列的候选文档（附加 score 字段）
        """
        if not candidates:
            return []

        if len(candidates) <= self._batch_size:
            return await self._rerank_batch(query, candidates)

        # 分批处理
        all_scored = []
        for i in range(0, len(candidates), self._batch_size):
            batch = candidates[i:i + self._batch_size]
            scored = await self._rerank_batch(query, batch)
            all_scored.extend(scored)

        # 合并重排
        all_scored.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_scored

    async def _rerank_batch(
        self, query: str, batch: list[dict]
    ) -> list[dict]:
        """对单批候选打分。"""
        prompt = RERANK_PROMPT.render(query=query, candidates=batch)

        try:
            response_wrapper = await self._llm.generate_content(prompt)
            response = response_wrapper.content if hasattr(response_wrapper, 'content') else str(response_wrapper)
            # 解析 JSON
            scores = _parse_scores(response)
            # 合并分数
            score_map = {s["id"]: s["score"] for s in scores}
            for doc in batch:
                doc["score"] = score_map.get(doc["id"], 50)  # 默认中等分
            return sorted(batch, key=lambda x: x.get("score", 50), reverse=True)
        except Exception as e:
            logger.warning(f"LLM rerank 失败，返回原始顺序: {e}")
            return batch


def _parse_scores(response: str) -> list[dict]:
    """从 LLM 响应中解析分数 JSON。"""
    # 尝试直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 块
    import re
    match = re.search(r"\[.*\]", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning(f"无法解析 LLM rerank 响应: {response[:200]}")
    return []
