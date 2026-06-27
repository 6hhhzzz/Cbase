package com.kes.common.exception;

import org.springframework.http.HttpStatus;

/**
 * 统一错误码枚举 — 全项目唯一的错误码定义。
 *
 * <p>格式: 模块_错误类型（大写蛇形命名）。每个枚举值携带对应的 HTTP 状态码和默认中文消息。
 *
 * <p>使用方式:
 * <pre>{@code
 *   throw new BusinessException(ErrorCode.DOC_NOT_FOUND);
 *   throw new BusinessException(ErrorCode.AUTH_TOKEN_EXPIRED, "自定义消息覆盖默认消息");
 * }</pre>
 */
public enum ErrorCode {

    // ---- Auth 认证模块 ----
    AUTH_USERNAME_EXISTS(HttpStatus.CONFLICT, "用户名已存在"),
    AUTH_BAD_CREDENTIALS(HttpStatus.UNAUTHORIZED, "用户名或密码错误"),
    AUTH_TOKEN_EXPIRED(HttpStatus.UNAUTHORIZED, "Token 已过期，请重新登录"),
    AUTH_NOT_LOGGED_IN(HttpStatus.UNAUTHORIZED, "未登录或 Token 已过期"),
    AUTH_WRONG_PASSWORD(HttpStatus.BAD_REQUEST, "旧密码错误"),
    AUTH_PASSWORD_TOO_SHORT(HttpStatus.BAD_REQUEST, "新密码至少 6 位"),

    // ---- User 用户 ----
    USER_NOT_FOUND(HttpStatus.NOT_FOUND, "用户不存在"),

    // ---- Space 空间模块 ----
    SPACE_NOT_FOUND(HttpStatus.NOT_FOUND, "Space 不存在"),
    SPACE_ACCESS_DENIED(HttpStatus.FORBIDDEN, "无权访问该 Space"),
    SPACE_ADMIN_REQUIRED(HttpStatus.FORBIDDEN, "需要 Space 管理员权限"),
    SPACE_OWNER_REQUIRED(HttpStatus.FORBIDDEN, "仅 Space 拥有者可执行此操作"),
    SPACE_ADMIN_ALREADY_EXISTS(HttpStatus.CONFLICT, "用户已是该 Space 的管理员"),
    SPACE_GROUP_ALREADY_ADDED(HttpStatus.CONFLICT, "该组已是 Space 的准入组"),
    SPACE_GROUP_NOT_FOUND(HttpStatus.NOT_FOUND, "该组不是 Space 的准入组"),
    SPACE_CANNOT_REMOVE_SELF(HttpStatus.BAD_REQUEST, "Owner 不能移除自己，请先转让 Owner"),
    SPACE_CANNOT_REMOVE_OTHER_OWNER(HttpStatus.FORBIDDEN, "不能移除其他 Owner"),
    SPACE_ADMIN_NOT_FOUND(HttpStatus.NOT_FOUND, "该用户不是 Space 管理员"),
    SPACE_NOT_ADMIN_CANNOT_OWNER(HttpStatus.BAD_REQUEST, "目标用户必须是 Space 的现有管理员才能接任 Owner"),
    GLOBAL_ADMIN_REQUIRED(HttpStatus.FORBIDDEN, "需要全局管理员权限"),

    // ---- KB 知识库模块 ----
    KB_NOT_FOUND(HttpStatus.NOT_FOUND, "KB 不存在"),
    KB_ACCESS_DENIED(HttpStatus.FORBIDDEN, "无权访问该知识库"),

    // ---- Document 文档模块 ----
    DOC_NOT_FOUND(HttpStatus.NOT_FOUND, "文档不存在"),
    DOC_UNSUPPORTED_TYPE(HttpStatus.BAD_REQUEST, "不支持的文件类型"),
    DOC_FILE_TOO_LARGE(HttpStatus.BAD_REQUEST, "文件过大"),
    DOC_UPLOAD_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "文件上传失败，请稍后重试"),
    DOC_APPROVAL_NOT_FOUND(HttpStatus.NOT_FOUND, "审批记录不存在"),

    // ---- Group 用户组模块 ----
    GROUP_NOT_FOUND(HttpStatus.NOT_FOUND, "用户组不存在"),
    GROUP_NAME_EMPTY(HttpStatus.BAD_REQUEST, "组名称不能为空"),
    GROUP_NAME_CONFLICT(HttpStatus.CONFLICT, "组名称已存在"),
    GROUP_HAS_CHILDREN(HttpStatus.BAD_REQUEST, "该组下有子组，请先删除子组"),
    GROUP_CANNOT_PARENT_SELF(HttpStatus.BAD_REQUEST, "不能将组的父组设为自己"),
    GROUP_MEMBER_NOT_FOUND(HttpStatus.NOT_FOUND, "用户不是该组成员"),
    GROUP_ALREADY_MEMBER(HttpStatus.CONFLICT, "用户已是该组成员"),
    GROUP_ADMIN_REQUIRED(HttpStatus.FORBIDDEN, "无权限管理该组"),
    GROUP_CANNOT_REMOVE_OWNER(HttpStatus.FORBIDDEN, "不能移除其他 owner"),
    GROUP_ADMIN_ALREADY_EXISTS(HttpStatus.CONFLICT, "该用户已是此组的管理员"),
    GROUP_ADMIN_NOT_FOUND(HttpStatus.NOT_FOUND, "该用户不是此组的管理员"),

    // ---- Role 角色模块 ----
    ROLE_NOT_FOUND(HttpStatus.NOT_FOUND, "角色不存在"),
    ROLE_NAME_EMPTY(HttpStatus.BAD_REQUEST, "角色名称不能为空"),
    ROLE_NAME_CONFLICT(HttpStatus.CONFLICT, "角色名称已存在"),
    ROLE_SYSTEM_PROTECTED(HttpStatus.FORBIDDEN, "系统角色不可修改或删除"),
    ROLE_IN_USE(HttpStatus.BAD_REQUEST, "角色被 ACE 规则引用，无法删除"),
    ACE_ALREADY_EXISTS(HttpStatus.CONFLICT, "该 ACE 规则已存在"),
    ACE_NOT_FOUND(HttpStatus.NOT_FOUND, "ACE 条目不存在"),

    // ---- AI 服务模块 ----
    AI_SERVICE_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "AI 服务暂不可用，请稍后重试"),
    AI_INGEST_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "文档入库失败"),

    // ---- Conversation 会话模块 ----
    CONV_NOT_FOUND(HttpStatus.NOT_FOUND, "会话不存在"),

    // ---- 通用参数 ----
    PARAM_INVALID(HttpStatus.BAD_REQUEST, "参数无效"),
    PARAM_MISSING(HttpStatus.BAD_REQUEST, "缺少必填参数"),

    // ---- Model 模型配置模块 ----
    MODEL_PROVIDER_NOT_FOUND(HttpStatus.NOT_FOUND, "模型供应商不存在"),
    MODEL_CONFIG_NOT_FOUND(HttpStatus.NOT_FOUND, "模型配置不存在"),
    MODEL_NAME_CONFLICT(HttpStatus.CONFLICT, "模型名称已存在"),
    MODEL_INVALID_URL(HttpStatus.BAD_REQUEST, "Base URL 格式无效"),

    // ---- API Key 模块 ----
    API_KEY_NOT_FOUND(HttpStatus.NOT_FOUND, "API 密钥不存在"),
    API_KEY_REVOKED(HttpStatus.GONE, "API 密钥已被撤销"),
    API_KEY_NAME_CONFLICT(HttpStatus.CONFLICT, "该名称已被使用"),
    API_KEY_EXPIRED(HttpStatus.UNAUTHORIZED, "API 密钥已过期"),
    API_KEY_UNAUTHORIZED(HttpStatus.FORBIDDEN, "无权操作该密钥"),

    // ---- CSV / 文件处理 ----
    CSV_PARSE_FAILED(HttpStatus.BAD_REQUEST, "CSV 解析失败"),
    CSV_EMPTY(HttpStatus.BAD_REQUEST, "CSV 文件为空"),
    CSV_MISSING_COLUMN(HttpStatus.BAD_REQUEST, "CSV 缺少必填列"),

    // ---- 存储 ----
    STORAGE_OPERATION_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "文件存储操作失败"),

    // ---- 内部错误 ----
    INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "服务器内部错误"),
    ;

    public final HttpStatus httpStatus;
    public final String defaultMessage;

    ErrorCode(HttpStatus httpStatus, String defaultMessage) {
        this.httpStatus = httpStatus;
        this.defaultMessage = defaultMessage;
    }
}
