package com.kes.auth.model;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * Token 响应 — v2 双 Token 机制。
 *
 * <p>登录时: access_token=null, refresh_token=有效值, user=UserInfo
 * <p>切换上下文时: access_token=有效值(短期), refresh_token=null, user=null
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record TokenResponse(
    String accessToken,
    String refreshToken,
    long expiresIn,
    UserInfo user
) {}
