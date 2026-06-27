package com.kes.common.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.kes.common.exception.ErrorCode;

/**
 * 统一 JSON 响应包装 — 所有 Controller 均使用此格式返回。
 *
 * <p>成功: {@code {code: 0, message: "ok", data: ..., timestamp: ...}}
 * <p>错误: {@code {code: 400, error_code: "DOC_NOT_FOUND", message: "...", timestamp: ...}}
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiResponse<T>(
    int code,
    String message,
    T data,
    long timestamp,
    String errorCode
) {
    /** 成功响应 */
    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(0, "ok", data, System.currentTimeMillis(), null);
    }

    /** 成功响应（无数据体） */
    public static <T> ApiResponse<T> success() {
        return new ApiResponse<>(0, "ok", null, System.currentTimeMillis(), null);
    }

    /**
     * 错误响应（使用 ErrorCode 枚举，推荐）。
     * 使用 ErrorCode 的默认消息。
     */
    public static <T> ApiResponse<T> error(ErrorCode errorCode) {
        return new ApiResponse<>(errorCode.httpStatus.value(), errorCode.defaultMessage, null, System.currentTimeMillis(), errorCode.name());
    }

    /**
     * 错误响应（使用 ErrorCode 枚举 + 自定义消息）。
     */
    public static <T> ApiResponse<T> error(ErrorCode errorCode, String message) {
        return new ApiResponse<>(errorCode.httpStatus.value(), message, null, System.currentTimeMillis(), errorCode.name());
    }

    /**
     * @deprecated 请使用 {@link #error(ErrorCode, String)} 传递 ErrorCode 枚举。
     *             本方法保留用于过渡期兼容。
     */
    @Deprecated
    public static <T> ApiResponse<T> error(int code, String message) {
        return new ApiResponse<>(code, message, null, System.currentTimeMillis(), null);
    }
}
