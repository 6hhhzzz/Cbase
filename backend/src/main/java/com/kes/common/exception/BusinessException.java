package com.kes.common.exception;

/**
 * 业务异常 — 被 GlobalExceptionHandler 统一处理。
 *
 * <p>推荐使用 {@link ErrorCode} 枚举构造，提供类型安全和自描述的错误码。
 * 旧的 int code 构造器保留兼容，逐步迁移到 ErrorCode。
 *
 * <p>使用示例:
 * <pre>{@code
 *   throw new BusinessException(ErrorCode.DOC_NOT_FOUND);
 *   throw new BusinessException(ErrorCode.DOC_NOT_FOUND, "文档不存在: " + docId);
 * }</pre>
 */
public class BusinessException extends RuntimeException {

    private final int code;
    private final String errorCode;

    /** 使用 ErrorCode 枚举构造（推荐） */
    public BusinessException(ErrorCode errorCode) {
        super(errorCode.defaultMessage);
        this.code = errorCode.httpStatus.value();
        this.errorCode = errorCode.name();
    }

    /** 使用 ErrorCode 枚举 + 自定义消息 */
    public BusinessException(ErrorCode errorCode, String customMessage) {
        super(customMessage);
        this.code = errorCode.httpStatus.value();
        this.errorCode = errorCode.name();
    }

    /**
     * @deprecated 请使用 {@link #BusinessException(ErrorCode)} 或 {@link #BusinessException(ErrorCode, String)}
     *             本构造器保留用于过渡期兼容，后续版本移除。
     */
    @Deprecated
    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
        this.errorCode = null;
    }

    public int getCode() {
        return code;
    }

    /** 获取字符串错误码（如 "DOC_NOT_FOUND"），使用 ErrorCode 构造时不为 null */
    public String getErrorCode() {
        return errorCode;
    }

    // ---- 工厂方法（使用 ErrorCode 枚举） ----

    public static BusinessException usernameExists(String username) {
        return new BusinessException(ErrorCode.AUTH_USERNAME_EXISTS, "用户名已存在: " + username);
    }

    public static BusinessException badCredentials() {
        return new BusinessException(ErrorCode.AUTH_BAD_CREDENTIALS);
    }

    public static BusinessException tokenExpired() {
        return new BusinessException(ErrorCode.AUTH_TOKEN_EXPIRED);
    }

    public static BusinessException documentNotFound(String docId) {
        return new BusinessException(ErrorCode.DOC_NOT_FOUND, "文档不存在: " + docId);
    }

    public static BusinessException unsupportedFileType(String fileType) {
        return new BusinessException(ErrorCode.DOC_UNSUPPORTED_TYPE, "不支持的文件类型: " + fileType);
    }

    public static BusinessException fileTooLarge(long maxSize) {
        return new BusinessException(ErrorCode.DOC_FILE_TOO_LARGE,
            "文件过大，最大支持 " + maxSize / 1024 / 1024 + "MB");
    }

    public static BusinessException aiServiceUnavailable() {
        return new BusinessException(ErrorCode.AI_SERVICE_UNAVAILABLE);
    }

    public static BusinessException ingestFailed(String detail) {
        return new BusinessException(ErrorCode.AI_INGEST_FAILED, "文档入库失败: " + detail);
    }

    public static BusinessException conversationNotFound(String convId) {
        return new BusinessException(ErrorCode.CONV_NOT_FOUND, "会话不存在: " + convId);
    }

    public static BusinessException invalidParameter(String detail) {
        return new BusinessException(ErrorCode.PARAM_INVALID, "参数无效: " + detail);
    }

    public static BusinessException accessDenied() {
        return new BusinessException(ErrorCode.DOC_NOT_FOUND, "无权访问该文档");
    }

    /** @deprecated 请使用 {@code new BusinessException(ErrorCode.SPACE_ACCESS_DENIED, message)} */
    @Deprecated
    public static BusinessException forbidden(String message) {
        return new BusinessException(ErrorCode.SPACE_ACCESS_DENIED, message);
    }
}
