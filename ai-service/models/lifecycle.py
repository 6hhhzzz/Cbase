"""文档生命周期模型 — Java 调用 Python 同步文档状态时使用。"""

from pydantic import BaseModel, Field


class DocumentStatusRequest(BaseModel):
    """Java 调用 POST /v1/documents/status 的请求体。"""
    doc_id: str = Field(..., description="文档 ID")
    status: str = Field(..., pattern="^(active|soft_deleted)$", description="目标状态")
