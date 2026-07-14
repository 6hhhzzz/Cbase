package com.kes.common.util;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.Map;
import java.util.UUID;

/**
 * JWT 工具类 — 双 Token 机制（v3 Space/KB RBAC）。
 *
 * <p>Refresh Token（长期，7天）:
 * <pre>
 * {
 *   "sub": "user-uuid",
 *   "type": "refresh",
 *   "iat": ..., "exp": ...
 * }
 * </pre>
 *
 * <p>Context Access Token（短期，30分钟）:
 * <pre>
 * {
 *   "sub": "user-uuid",
 *   "username": "zhangsan",
 *   "type": "context",
 *   "space_id": "uuid",
 *   "role": "member",
 *   "iat": ..., "exp": ...
 * }
 * </pre>
 */
@Component
public class JwtUtil {

    private final SecretKey key;
    private final long expiration;
    private final long refreshExpiration;
    private final long contextExpiration;

    public JwtUtil(
        @Value("${jwt.secret}") String secret,
        @Value("${jwt.expiration}") long expiration,
        @Value("${jwt.refresh-expiration}") long refreshExpiration,
        @Value("${jwt.context-expiration:1800000}") long contextExpiration
    ) {
        if (secret == null || secret.length() < 32) {
            throw new IllegalArgumentException(
                "JWT 密钥长度不足 (当前 " + (secret == null ? 0 : secret.length()) + " 字符)。" +
                "请在 application.yml 中设置 jwt.secret 为至少 32 字符的随机字符串。" +
                "可使用: openssl rand -base64 32"
            );
        }
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expiration = expiration;
        this.refreshExpiration = refreshExpiration;
        this.contextExpiration = contextExpiration;
    }

    // ---- Refresh Token ----

    public String generateRefreshToken(String userId) {
        return Jwts.builder()
            .id(UUID.randomUUID().toString())
            .subject(userId)
            .claim("type", "refresh")
            .issuedAt(new Date())
            .expiration(new Date(System.currentTimeMillis() + refreshExpiration))
            .signWith(key)
            .compact();
    }

    // ---- Context Access Token ----

    /** 生成 Context Token（含 Space ID + 角色） */
    public String generateContextToken(String userId, String username,
                                        String spaceId, String role) {
        return Jwts.builder()
            .subject(userId)
            .claims(Map.of(
                "username", username,
                "type", "context",
                "space_id", spaceId,
                "role", role
            ))
            .issuedAt(new Date())
            .expiration(new Date(System.currentTimeMillis() + contextExpiration))
            .signWith(key)
            .compact();
    }

    // ---- 通用解析 ----

    public Claims parseToken(String token) {
        return Jwts.parser()
            .verifyWith(key)
            .build()
            .parseSignedClaims(token)
            .getPayload();
    }

    public boolean isTokenValid(String token) {
        try {
            parseToken(token);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public String extractBearerToken(String authHeader) {
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            return authHeader.substring(7);
        }
        return null;
    }

    public String extractUserId(String token) {
        return parseToken(token).getSubject();
    }

    public boolean isContextToken(String token) {
        return "context".equals(parseToken(token).get("type", String.class));
    }

    /** 提取当前 Space ID */
    public String extractSpaceId(String token) {
        return parseToken(token).get("space_id", String.class);
    }

    /** 提取当前上下文中的角色 */
    public String extractContextRole(String token) {
        return parseToken(token).get("role", String.class);
    }
}
