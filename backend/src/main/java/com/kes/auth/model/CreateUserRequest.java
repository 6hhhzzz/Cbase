package com.kes.auth.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 管理员创建用户请求。
 * password 可选 — 为空时系统自动生成随机密码。
 */
public record CreateUserRequest(
    @NotBlank @Size(min = 3, max = 32)
    String username,

    @NotBlank @Size(min = 1, max = 64)
    @JsonProperty("display_name")
    String displayName,

    @Email
    String email,

    @Size(min = 8, max = 128)
    String password
) {}
