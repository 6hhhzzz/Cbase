"""文档 / ETL 数据模型。v3 Space/KB 权限模型。"""

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IngestStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentMetadata(BaseModel):
    """入库文档的权限元数据 — v3 KB 归属 + v3.2 业务时效。"""

    kb_id: str                         # 文档所属的知识库 ID
    contributor_id: UUID | None = None
    uploader_role: str | None = None   # 用于 Excel 双通道判定
    effective_date: str | None = None  # 文档生效日期 (YYYY-MM-DD)
    expiry_date: str | None = None     # 文档失效日期 (YYYY-MM-DD)，空 = 长期有效
    version: str | None = None         # 文档版本号


class DocumentIngestMessage(BaseModel):
    """RabbitMQ 文档入库消息体。"""

    doc_id: UUID
    file_path: str
    file_type: str = Field(..., pattern=r"^(pdf|docx|xlsx|pptx|md|html|txt)$")
    metadata: DocumentMetadata


class IngestCallbackMessage(BaseModel):
    """Python → Java 入库状态回调。"""

    doc_id: UUID
    status: IngestStatus
    error_message: str | None = None
    chunks_created: int = 0
    tokens_used: int = 0


class DocumentChunk(BaseModel):
    """ETL 分块后的单个文本块。"""

    doc_id: UUID
    chunk_index: int
    chunk_text: str = Field(..., max_length=65535)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParseResult(BaseModel):
    """文件解析器返回结果。"""

    file_type: str
    raw_text: str
    page_count: int = 0
    tables: list[dict] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
