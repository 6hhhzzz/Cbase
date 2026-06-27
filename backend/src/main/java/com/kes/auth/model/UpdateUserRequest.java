package com.kes.auth.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Size;

/**
 * 管理员编辑用户请求。所有字段可选，只更新非 null 字段。
 */
public record UpdateUserRequest(
    @Size(min = 1, max = 64)
    @JsonProperty("display_name")
    String displayName,

    @Email
    String email,

    String status
) {}
