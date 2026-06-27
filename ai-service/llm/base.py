"""LLM / Embedding 抽象基类。定义策略接口，所有供应商实现必须继承此类。"""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from models import ChatMessage, LLMResponse


class BaseLLM(ABC):
    """LLM 策略接口。所有模型供应商实现必须继承此类。

    设计动机（proposal 4.1）：
    - 解耦供应商 SDK 依赖
    - 调用方只依赖抽象，不依赖具体实现
    - 切换模型时业务代码零改动
    """

    @abstractmethod
    async def generate_content(
        self,
        prompt: str,
        context: list[ChatMessage] | None = None,
        history: list[ChatMessage] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """非流式生成。

        Args:
            prompt: 当前用户提问
            context: 检索到的文档片段（role="context"）
            history: 历史对话（role="user"/"assistant" 交替）

        Returns:
            LLMResponse: 包含 content、model、usage 等字段
        """
        ...

    @abstractmethod
    async def stream_content(
        self,
        prompt: str,
        context: list[ChatMessage] | None = None,
        history: list[ChatMessage] | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式生成，逐 token yield。用于 SSE 推送。

        Args:
            prompt: 当前用户提问
            context: 检索到的文档片段
            history: 历史对话

        Yields:
            str: 增量生成的文本 token
        """
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """返回当前模型名称，用于日志和审计。"""
        ...

    def _build_messages(
        self,
        prompt: str,
        context: list[ChatMessage] | None,
        history: list[ChatMessage] | None,
    ) -> list[dict]:
        """将多来源输入合并为 OpenAI 格式消息列表。子类可覆盖。

        Args:
            prompt: 当前用户提问
            context: 检索文档片段
            history: 历史对话

        Returns:
            OpenAI 格式的消息列表
        """
        messages = []
        if history:
            messages.extend([m.to_openai_format() for m in history])
        if context:
            messages.extend([m.to_openai_format() for m in context])
        messages.append({"role": "user", "content": prompt})
        return messages


class BaseEmbedding(ABC):
    """Embedding 策略接口。所有 Embedding 供应商实现必须继承此类。

    设计动机（proposal 4.1）：
    - 与 BaseLLM 统一设计模式
    - 切换 Embedding 供应商时检索代码不受影响
    """

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量向量化文档。

        Args:
            texts: 文本列表

        Returns:
            向量列表，每个向量为 list[float]
        """
        ...

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """单条查询向量化。

        Args:
            query: 查询文本

        Returns:
            向量
        """
        ...

    @abstractmethod
    def get_dimension(self) -> int:
        """返回向量维度，用于 pgvector Schema 校验。"""
        ...
