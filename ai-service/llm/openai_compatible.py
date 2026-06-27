"""OpenAI 兼容协议适配器。

使用 openai 官方 Python SDK，通过 base_url 指向任意兼容接口：
- DashScope（阿里云）: https://dashscope.aliyuncs.com/compatible-mode/v1
- vLLM 本地部署: http://localhost:8000/v1
- DeepSeek: https://api.deepseek.com/v1
- 任何 OpenAI 兼容网关

对应 proposal 4.5 和 4.7。
"""

from typing import AsyncIterator

import httpx
import openai

from models import LLMConfig, EmbeddingConfig, ChatMessage, LLMResponse

from .base import BaseEmbedding, BaseLLM


class OpenAICompatibleLLM(BaseLLM):
    """覆盖 DashScope / vLLM / DeepSeek 等所有 OpenAI 兼容接口的 LLM 适配器。"""

    def __init__(self, config: LLMConfig):
        # 从配置中读取超时，默认连接 10s、流式读取 60s、总超时 120s
        timeout_config = config.default_params.get("timeout", {})
        connect_timeout = timeout_config.get("connect", 10.0)
        read_timeout = timeout_config.get("read", 60.0)
        total_timeout = timeout_config.get("total", 120.0)

        self._client = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=httpx.Timeout(
                total_timeout,
                connect=connect_timeout,
                read=read_timeout,
            ),
            max_retries=2,
        )
        self._model = config.model
        # 过滤掉 timeout 配置，避免透传给 LLM API 参数
        self._default_params = {k: v for k, v in config.default_params.items()
                                if k != "timeout"}

    async def generate_content(
        self,
        prompt: str,
        context: list[ChatMessage] | None = None,
        history: list[ChatMessage] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """非流式生成。"""
        messages = self._build_messages(prompt, context, history)
        params = {**self._default_params, **kwargs}
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **params,
        )
        return LLMResponse(
            content=response.choices[0].message.content,
            model=self._model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            } if response.usage else None,
        )

    async def stream_content(
        self,
        prompt: str,
        context: list[ChatMessage] | None = None,
        history: list[ChatMessage] | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式生成，逐 token yield。"""
        messages = self._build_messages(prompt, context, history)
        params = {**self._default_params, **kwargs}
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **params,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def get_model_name(self) -> str:
        return self._model


class OpenAICompatibleEmbedding(BaseEmbedding):
    """OpenAI 兼容接口的 Embedding 适配器。"""

    def __init__(self, config: EmbeddingConfig):
        self._client = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=httpx.Timeout(60.0, connect=10.0),
            max_retries=2,
        )
        self._model = config.model
        self._dimension = config.dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量向量化文档。"""
        response = await self._client.embeddings.create(
            model=self._model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    async def embed_query(self, query: str) -> list[float]:
        """单条查询向量化。"""
        results = await self.embed_documents([query])
        return results[0]

    def get_dimension(self) -> int:
        return self._dimension
