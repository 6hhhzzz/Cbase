"""检索相关数据模型。用于向量检索请求和结果传递。"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FilterParams(BaseModel):
    """权限过滤参数 — v4 ACE + 文档级权限。
    Java 在调用前计算好用户有权访问的所有 kb_id，传入列表。
    doc_ids 为 null 时无文档级限制；非 null 时排除列表中的文档。
    Python 只负责机械地构建 WHERE 查询，不作权限判断。
    """

    kb_ids: list[str] = Field(default_factory=list)
    doc_ids: list[str] | None = None


class SearchRequest(BaseModel):
    """pgvector 向量检索请求。"""

    query_vector: list[float]
    filter_params: FilterParams
    top_k: int = 5


class SearchResult(BaseModel):
    """单条检索结果。"""

    chunk_id: str = ""
    doc_id: UUID
    chunk_index: int
    chunk_text: str
    source_file: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
