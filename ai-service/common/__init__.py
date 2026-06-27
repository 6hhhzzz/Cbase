# 公共模块：日志、异常、工具函数等横切关注点

from .exceptions import (
    AppException,
    EmbeddingServiceError,
    IngestPipelineError,
    LLMServiceError,
    VectorDBConnectionError,
    MissingFiltersError,
    UnsupportedFileTypeError,
)
from .logging import get_logger, setup_logging
from .utils import (
    current_timestamp_ms,
    estimate_tokens,
    generate_chunk_id,
    generate_doc_id,
    truncate_text,
)

__all__ = [
    # 日志
    "setup_logging",
    "get_logger",
    # 异常
    "AppException",
    "MissingFiltersError",
    "VectorDBConnectionError",
    "LLMServiceError",
    "EmbeddingServiceError",
    "IngestPipelineError",
    "UnsupportedFileTypeError",
    # 工具
    "generate_doc_id",
    "generate_chunk_id",
    "estimate_tokens",
    "current_timestamp_ms",
    "truncate_text",
]
