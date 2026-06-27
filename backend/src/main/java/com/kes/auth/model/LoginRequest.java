package com.kes.auth.model;

import jakarta.validation.constraints.NotBlank;

/**
 * 登录请求 — 对应 openapi.yaml LoginRequest Schema。
 */
public record LoginRequest(
    @NotBlank String username,
    @NotBlank String password
) {}
