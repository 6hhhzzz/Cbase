"""上下文组装器 — 将多来源输入组装为 LLM 的最终上下文。

对应《核心接口契约文档》§1 架构图 Python 步骤4：
- 接收 Java 转发的 history_messages
- 组装顺序: [system_prompt] → [summary] → [Java 转发的历史消息] → [当前 query]

注意：消息历史由 Java 在 /v1/chat 请求中转发，Python 不独立查询业务数据库。
"""

from uuid import UUID

from common import get_logger
from common.utils import estimate_tokens
from models.chat import ChatMessage
from models.retrieval import SearchResult

from .history_manager import HistoryManager

logger = get_logger(__name__)


class ContextAssembler:
    """将多来源输入组装为 LLM 的最终上下文。

    组装顺序:
        [system_prompt] → [summary] → [Java 转发的历史消息] → [当前 query]
    """

    CONTEXT_BUDGET_RATIO = 0.2  # 历史部分不超过模型窗口的 20%

    def __init__(self, history_manager: HistoryManager):
        self._history = history_manager

    async def assemble(
        self,
        conversation_id: UUID,
        query: str,
        search_results: list[SearchResult],
        system_prompt: str,
        history_messages: list[ChatMessage] | None = None,
    ) -> tuple[list[dict], str]:
        """组装完整 LLM 上下文。

        组装顺序:
            [system_prompt] → [summary] → [Java 转发的历史消息] → [当前 query]

        Args:
            conversation_id: 会话 ID
            query: 当前用户提问
            search_results: pgvector 检索结果
            system_prompt: RAG 问答 System Prompt（已填充检索结果）
            history_messages: Java 在请求中转发的最新 N 条历史消息

        Returns:
            messages: 完整的 OpenAI 格式消息列表
            summary_text: 本次使用的摘要文本（用于日志/调试）
        """
        messages = []

        # 1. System Prompt（已包含检索结果作为 context）
        messages.append({"role": "system", "content": system_prompt})

        # 2. 获取摘要（如有）
        summary_text = await self._history.get_summary(conversation_id) or ""
        if summary_text:
            messages.append({
                "role": "system",
                "content": f"历史对话摘要:\n{summary_text}",
            })

        # 3. Java 转发的历史消息（权威来源）
        if history_messages:
            for msg in history_messages:
                messages.append(msg.to_openai_format())

        # 4. 当前用户提问
        messages.append({"role": "user", "content": query})

        # 5. 上下文预算检查
        total_tokens = estimate_tokens(
            " ".join(m.get("content", "") for m in messages)
        )
        logger.info(
            f"上下文组装完成: conv={conversation_id}, "
            f"消息数={len(messages)}, 估算 tokens={total_tokens}"
        )

        return messages, summary_text

    def build_retrieval_context(self, search_results: list[SearchResult]) -> str:
        """将检索结果格式化为 LLM 可读的文本。

        Args:
            search_results: pgvector 检索结果列表

        Returns:
            格式化的检索结果文本
        """
        if not search_results:
            return "未找到相关文档。"

        parts = []
        for i, result in enumerate(search_results, 1):
            parts.append(
                f"[{i}] 来源: {result.source_file} (相关度: {result.score:.2f})\n"
                f"{result.chunk_text}\n"
            )
        return "\n---\n".join(parts)
