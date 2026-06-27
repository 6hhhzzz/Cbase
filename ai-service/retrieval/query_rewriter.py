"""QueryRewriter — 查询改写（缓存 + 短路 + 关键词提取）。

架构师建议：
    - 短路条件避免不必要的 LLM 调用
    - 改写时顺便提取核心关键词传给 BM25
    - Redis 缓存改写结果（5 分钟 TTL）
"""

import json
import time

from common import get_logger
from llm.base import BaseLLM
from llm.prompts.rewrite import REWRITE_PROMPT
from .models import RewriteResult

logger = get_logger(__name__)

_CACHE_TTL = 300  # 改写结果缓存 5 分钟


class QueryRewriter:
    """查询改写器。

    短路条件：
        - 无对话历史
        - 查询已足够具体（长度 > 50 且含具体实体）
        - 60 秒内刚做过改写
    """

    def __init__(self, llm: BaseLLM):
        self._llm = llm
        self._cache: dict[str, tuple[float, RewriteResult]] = {}  # query → (timestamp, result)
        self._last_rewrite_time: float = 0

    def should_rewrite(
        self,
        query: str,
        history_len: int = 0,
    ) -> bool:
        """判断是否需要改写。

        Args:
            query: 原始查询
            history_len: 对话历史轮数

        Returns:
            True 表示需要改写
        """
        if history_len <= 0:
            return False
        if len(query) > 50 and self._has_concrete_entities(query):
            return False
        if self._last_rewrite_time > 0 and (
            time.time() - self._last_rewrite_time < 60
        ):
            return False
        return True

    async def rewrite(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> RewriteResult:
        """改写查询。

        Args:
            query: 原始查询
            history: 对话历史 [{"role": "user/assistant", "content": "..."}]

        Returns:
            RewriteResult (含 rewritten_query 和 keywords)
        """
        if not history:
            return RewriteResult(rewritten_query=query, skipped=True)

        # 检查缓存
        cache_key = f"{query}:{len(history)}"
        if cache_key in self._cache:
            ts, result = self._cache[cache_key]
            if time.time() - ts < _CACHE_TTL:
                logger.debug(f"QueryRewrite cache hit: {query[:50]}")
                return result

        try:
            prompt = REWRITE_PROMPT.render(query=query, history=history)
            response_wrapper = await self._llm.generate_content(prompt)
            response = (
                response_wrapper.content
                if hasattr(response_wrapper, "content")
                else str(response_wrapper)
            )

            result = _parse_rewrite_response(response, query)
            self._cache[cache_key] = (time.time(), result)
            self._last_rewrite_time = time.time()
            logger.info(f"QueryRewrite: '{query[:50]}' → '{result.rewritten_query[:50]}' "
                        f"keywords={result.keywords}")
            return result

        except Exception as e:
            logger.warning(f"QueryRewrite 失败，返回原查询: {e}")
            return RewriteResult(rewritten_query=query, skipped=True)

    def _has_concrete_entities(self, query: str) -> bool:
        """检测查询是否包含具体实体（产品型号、编号等）。"""
        import re
        # 包含数字+字母组合（如货号、版本号）
        if re.search(r"[A-Za-z]+[0-9]+|[0-9]+[A-Za-z]+", query):
            return True
        # 包含引号中的词
        if re.search(r"['\"'「『].+?['\"'」』]", query):
            return True
        # 足够长的查询
        if len(query) > 80:
            return True
        return False


def _parse_rewrite_response(response: str, fallback_query: str) -> RewriteResult:
    """解析 LLM 改写响应。"""
    try:
        data = json.loads(response)
        return RewriteResult(
            rewritten_query=data.get("rewritten_query", fallback_query),
            keywords=data.get("keywords", []),
        )
    except json.JSONDecodeError:
        # 尝试提取 JSON 块
        import re
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return RewriteResult(
                    rewritten_query=data.get("rewritten_query", fallback_query),
                    keywords=data.get("keywords", []),
                )
            except json.JSONDecodeError:
                pass

    logger.warning(f"无法解析改写响应，使用原查询: {response[:200]}")
    return RewriteResult(rewritten_query=fallback_query, skipped=True)
