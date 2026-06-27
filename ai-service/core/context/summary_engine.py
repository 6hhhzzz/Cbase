"""摘要生成与二次压缩引擎。"""

from uuid import UUID

from common import get_logger
from common.utils import estimate_tokens
from llm.base import BaseLLM
from llm.prompts.summary import COMPRESS_PROMPT, SUMMARY_PROMPT
from .history_manager import HistoryManager

logger = get_logger(__name__)

# 默认阈值
DEFAULT_SOFT_LIMIT = 1500
DEFAULT_COMPRESS_TARGET = 800
DEFAULT_TRIGGER_ROUNDS = 10
DEFAULT_MAX_FAILURES = 3


class SummaryEngine:
    """摘要生成与二次压缩引擎。"""

    def __init__(self, llm: BaseLLM, history_manager: HistoryManager,
                 soft_limit: int = DEFAULT_SOFT_LIMIT,
                 compress_target: int = DEFAULT_COMPRESS_TARGET,
                 trigger_rounds: int = DEFAULT_TRIGGER_ROUNDS,
                 max_failures: int = DEFAULT_MAX_FAILURES):
        self._llm = llm
        self._history = history_manager
        self._soft_limit = soft_limit
        self._compress_target = compress_target
        self._trigger_rounds = trigger_rounds
        self._max_failures = max_failures
        self._failure_counts: dict[str, int] = {}

    # ================================================================
    # 公共入口
    # ================================================================

    async def maybe_update_summary(self, conversation_id: UUID) -> bool:
        """后台异步入口：检查是否需要更新或压缩摘要。"""
        if not await self._history.acquire_summary_lock(conversation_id):
            logger.debug(f"摘要锁已被占用，跳过: {conversation_id}")
            return False

        try:
            return await self._try_update_summary(conversation_id)
        except Exception as e:
            await self._handle_failure(str(conversation_id), e)
            return False
        finally:
            await self._history.release_summary_lock(conversation_id)

    # ================================================================
    # 核心逻辑
    # ================================================================

    async def _try_update_summary(self, conversation_id: UUID) -> bool:
        """执行摘要更新/压缩逻辑（锁已获取）。"""
        total_rounds = await self._history.get_total_rounds(conversation_id)

        if total_rounds <= self._trigger_rounds:
            return False

        existing_summary = await self._history.get_summary(conversation_id)
        recent_messages = await self._history.get_recent_messages(conversation_id, count=40)

        overflow_start = max(0, len(recent_messages) - 20)
        new_overflow = recent_messages[:overflow_start]

        if new_overflow:
            return await self._update_with_overflow(conversation_id, new_overflow, existing_summary)

        if existing_summary and estimate_tokens(existing_summary) >= self._soft_limit:
            return await self._compress_existing(conversation_id, existing_summary)

        return False

    async def _update_with_overflow(self, conv_id: UUID, overflow: list,
                                     existing: str | None) -> bool:
        """有新溢出轮次 → 更新摘要。"""
        summary = await self._generate_summary(overflow, existing)
        summary = await self._maybe_compress(summary)

        token_count = estimate_tokens(summary)
        await self._history.update_summary(conv_id, summary, token_count)

        cid = str(conv_id)
        self._failure_counts.pop(cid, None)

        logger.info(f"摘要已更新: conv={conv_id}, tokens={token_count}")
        return True

    async def _compress_existing(self, conv_id: UUID, summary: str) -> bool:
        """无需更新但摘要过长 → 二次压缩。"""
        old_tokens = estimate_tokens(summary)
        compressed = await self._compress_summary(summary)
        new_tokens = estimate_tokens(compressed)
        await self._history.update_summary(conv_id, compressed, new_tokens)
        logger.info(f"摘要二次压缩: conv={conv_id}, {old_tokens}→{new_tokens} tokens")
        return True

    async def _maybe_compress(self, summary: str) -> str:
        """检查摘要长度，超出软上限则压缩。"""
        if estimate_tokens(summary) >= self._soft_limit:
            return await self._compress_summary(summary)
        return summary

    async def _handle_failure(self, cid: str, error: Exception) -> None:
        """连续失败处理。超过阈值则丢弃摘要。"""
        self._failure_counts[cid] = self._failure_counts.get(cid, 0) + 1
        count = self._failure_counts[cid]
        logger.error(f"摘要更新失败(第{count}次): {error}")

        if count >= self._max_failures:
            logger.warning(f"连续失败 {self._max_failures} 次，丢弃摘要: {cid}")
            await self._history.update_summary(UUID(cid), "", 0)
            self._failure_counts.pop(cid, None)

    # ================================================================
    # LLM 调用
    # ================================================================

    async def _generate_summary(self, messages: list, existing_summary: str | None) -> str:
        """调用 LLM 生成摘要。"""
        prompt = SUMMARY_PROMPT.render(messages=messages, max_tokens=self._soft_limit)
        content = (await self._llm.generate_content(prompt=prompt)).content.strip()
        return f"{existing_summary}\n{content}" if existing_summary else content

    async def _compress_summary(self, summary: str) -> str:
        """二次压缩：摘要的摘要。"""
        prompt = COMPRESS_PROMPT.render(summary=summary, target_tokens=self._compress_target)
        return (await self._llm.generate_content(prompt=prompt)).content.strip()
