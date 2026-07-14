package com.kes.common.exception;

import com.kes.common.model.ApiResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.AuthenticationException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * 全局异常处理器 — 将各类异常统一转换为 ApiResponse 格式。
 * 对应 openapi.yaml ErrorResponse Schema。
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    /** 业务异常 — HTTP 状态码由 ErrorCode.httpStatus 决定 */
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiResponse<Void>> handleBusiness(BusinessException e) {
        log.warn("业务异常: error_code={}, message={}", e.getErrorCode(), e.getMessage());
        ErrorCode errorCode = ErrorCode.valueOf(e.getErrorCode());
        return ResponseEntity.status(errorCode.httpStatus)
            .body(ApiResponse.error(errorCode, e.getMessage()));
    }

    /** 参数校验失败 */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ApiResponse<Void> handleValidation(MethodArgumentNotValidException e) {
        String detail = e.getBindingResult().getFieldErrors().stream()
            .map(f -> f.getField() + ": " + f.getDefaultMessage())
            .reduce((a, b) -> a + "; " + b)
            .orElse("参数校验失败");
        log.warn("参数校验失败: {}", detail);
        return ApiResponse.error(ErrorCode.PARAM_INVALID, detail);
    }

    /** 未认证 */
    @ExceptionHandler(AuthenticationException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public ApiResponse<Void> handleAuth(AuthenticationException e) {
        log.warn("认证失败: {}", e.getMessage());
        return ApiResponse.error(ErrorCode.AUTH_NOT_LOGGED_IN);
    }

    /** 未知异常 → 500 */
    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public ApiResponse<Void> handleUnknown(Exception e) {
        log.error("未捕获的异常: {}", e.getMessage(), e);
        return ApiResponse.error(ErrorCode.INTERNAL_ERROR);
    }
}
