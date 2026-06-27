package com.kes.auth.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 注册请求 — v3。仅需基本用户信息。
 */
public record RegisterRequest(
    @NotBlank @Size(min = 3, max = 32) String username,
    @NotBlank @Size(min = 8) String password,
    @NotBlank @JsonProperty("display_name") String displayName
) {}
