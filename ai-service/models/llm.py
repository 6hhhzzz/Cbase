"""LLM / Embedding 返回值模型。对应 proposal 4.4 的通用类型定义。"""

from pydantic import BaseModel


class LLMResponse(BaseModel):
    """BaseLLM.generate_content() 的返回值。"""

    content: str
    model: str
    usage: dict | None = None
    # usage 示例: {"prompt_tokens": 1500, "completion_tokens": 300}


class EmbeddingResult(BaseModel):
    """BaseEmbedding 返回值。"""

    vectors: list[list[float]]
    dimension: int
    tokens_used: int
