# LLM / Embedding 适配层
# 设计模式：适配器 + 策略（proposal 4.2）
# 调用方只依赖抽象，不依赖具体 SDK

from .base import BaseEmbedding, BaseLLM
from .factory import ModelFactory
from .openai_compatible import OpenAICompatibleEmbedding, OpenAICompatibleLLM

__all__ = [
    "BaseLLM",
    "BaseEmbedding",
    "OpenAICompatibleLLM",
    "OpenAICompatibleEmbedding",
    "ModelFactory",
]
