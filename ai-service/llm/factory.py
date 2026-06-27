"""模型工厂 — 按 YAML 配置在运行时创建 LLM / Embedding 实例。

设计模式：策略 + 工厂方法（proposal 4.2）
- 新增供应商无需修改工厂代码，仅需注册即可
- 切换供应商只需修改 llm.yaml 中的 type 字段
"""

from models.config import LLMConfig, EmbeddingConfig

from .base import BaseEmbedding, BaseLLM
from .openai_compatible import OpenAICompatibleEmbedding, OpenAICompatibleLLM


class ModelFactory:
    """模型工厂，管理 LLM 和 Embedding 实现的注册与创建。"""

    _llm_registry: dict[str, type[BaseLLM]] = {
        "openai_compatible": OpenAICompatibleLLM,
    }
    _embedding_registry: dict[str, type[BaseEmbedding]] = {
        "openai_compatible": OpenAICompatibleEmbedding,
    }

    @classmethod
    def register_llm(cls, name: str, impl: type[BaseLLM]) -> None:
        """注册自定义 LLM 实现。不修改框架代码即可扩展。

        示例（proposal 4.8）:
            ModelFactory.register_llm("claude", ClaudeLLM)
        """
        cls._llm_registry[name] = impl

    @classmethod
    def create_llm(cls, config: LLMConfig) -> BaseLLM:
        """按配置创建 LLM 实例。

        Args:
            config: LLMConfig，其中 type 字段决定使用哪个实现

        Returns:
            BaseLLM 实例

        Raises:
            ValueError: 未知的 LLM type
        """
        impl = cls._llm_registry.get(config.type)
        if not impl:
            available = list(cls._llm_registry.keys())
            raise ValueError(
                f"未知的 LLM 类型: {config.type}，可用类型: {available}"
            )
        return impl(config)

    @classmethod
    def register_embedding(cls, name: str, impl: type[BaseEmbedding]) -> None:
        """注册自定义 Embedding 实现。"""
        cls._embedding_registry[name] = impl

    @classmethod
    def create_embedding(cls, config: EmbeddingConfig) -> BaseEmbedding:
        """按配置创建 Embedding 实例。

        Args:
            config: EmbeddingConfig，其中 type 字段决定使用哪个实现

        Returns:
            BaseEmbedding 实例

        Raises:
            ValueError: 未知的 embedding type
        """
        impl = cls._embedding_registry.get(config.type)
        if not impl:
            available = list(cls._embedding_registry.keys())
            raise ValueError(
                f"未知的 Embedding 类型: {config.type}，可用类型: {available}"
            )
        return impl(config)
