"""对话与会话数据模型。

对应《核心接口契约文档》§2：
- ChatRequest: Java → Python 问答请求（含 Java 转发的 history_messages 和 filter_params）
- ChatMessage: 单条对话消息
- ChatTokenChunk: SSE 流式响应的单个 token 块

注意：Python 不操作数据库，消息持久化由 Java 独占负责。
"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from models.retrieval import FilterParams


class ChatMessage(BaseModel):
    """单条对话消息。用于 LLM 上下文组装和 Java 转发的历史消息。"""

    role: str = Field(..., pattern=r"^(user|assistant|system|context)$")
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_openai_format(self) -> dict:
        """转为 OpenAI 兼容格式，供 LLM 适配器使用。"""
        return {"role": self.role, "content": self.content}


class ChatRequest(BaseModel):
    """Java → Python 问答请求。

    对应《核心接口契约文档》§2.2 字段说明。
    filter_params 由 Java 从 JWT 构建，Python 信任并使用。
    history_messages 由 Java 从 PG 读取后转发，Python 直接使用。
    """

    query: str = Field(..., min_length=1, max_length=4096)
    filter_params: FilterParams  # 安全红线：必填，Java 构建
    conversation_id: UUID
    history_messages: list[ChatMessage] = Field(default_factory=list)  # Java 转发
    top_k: int = Field(default=5, ge=1, le=20)


class ChatTokenChunk(BaseModel):
    """SSE 流式响应的单个 token 块。

    对应《核心接口契约文档》§2.4 SSE 流式响应数据格式。
    普通块：token 非空、done=false、sources=null
    结束块：token 为空、done=true、sources 含检索源文献
    """

    token: str
    done: bool = False
    sources: list[dict] | None = None   # 仅 done=true 时附带
    citations: list[dict] | None = None # ★ v5: 引用标注列表
