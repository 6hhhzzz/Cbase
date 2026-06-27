"""自定义异常体系 — 统一错误码，与 Java ErrorCode 枚举对应。

业务代码抛出这些异常，由 FastAPI 异常处理器统一转换为 JSON 响应。
响应格式: {"error_code": "DOC_NOT_FOUND", "message": "文档不存在"}
"""


class ErrorCode:
    """错误码常量 — 与 Java ErrorCode 枚举一一对应。仅定义 Python 端实际使用的码。"""

    # Auth
    AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED"
    AUTH_NOT_LOGGED_IN = "AUTH_NOT_LOGGED_IN"

    # Document
    DOC_NOT_FOUND = "DOC_NOT_FOUND"
    DOC_UNSUPPORTED_TYPE = "DOC_UNSUPPORTED_TYPE"

    # KB
    KB_NOT_FOUND = "KB_NOT_FOUND"

    # AI Service
    AI_SERVICE_UNAVAILABLE = "AI_SERVICE_UNAVAILABLE"
    AI_INGEST_FAILED = "AI_INGEST_FAILED"

    # Parameter
    PARAM_INVALID = "PARAM_INVALID"
    PARAM_MISSING = "PARAM_MISSING"

    # Internal
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppException(Exception):
    """应用级异常基类。

    Attributes:
        message: 面向用户的错误消息
        error_code: 字符串错误码，如 "DOC_NOT_FOUND"，与 Java ErrorCode 枚举对齐
    """

    def __init__(self, message: str, error_code: str = ErrorCode.INTERNAL_ERROR):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class MissingFiltersError(AppException):
    """filter_params 参数缺失——安全红线。"""

    def __init__(self):
        super().__init__(
            message="filter_params 参数为必填项，请提供权限过滤参数",
            error_code=ErrorCode.PARAM_MISSING,
        )


class VectorDBConnectionError(AppException):
    """向量数据库连接异常。"""

    def __init__(self, detail: str = "向量数据库不可用"):
        super().__init__(message=detail, error_code=ErrorCode.AI_SERVICE_UNAVAILABLE)


class LLMServiceError(AppException):
    """LLM 调用异常。"""

    def __init__(self, detail: str = "LLM 服务不可用"):
        super().__init__(message=detail, error_code=ErrorCode.AI_SERVICE_UNAVAILABLE)


class EmbeddingServiceError(AppException):
    """Embedding 调用异常。"""

    def __init__(self, detail: str = "Embedding 服务不可用"):
        super().__init__(message=detail, error_code=ErrorCode.AI_SERVICE_UNAVAILABLE)


class IngestPipelineError(AppException):
    """文档入库管道异常。"""

    def __init__(self, detail: str = "文档入库失败"):
        super().__init__(message=detail, error_code=ErrorCode.AI_INGEST_FAILED)


class UnsupportedFileTypeError(AppException):
    """不支持的文件类型。"""

    def __init__(self, file_type: str):
        super().__init__(
            message=f"不支持的文件类型: {file_type}",
            error_code=ErrorCode.DOC_UNSUPPORTED_TYPE,
        )
