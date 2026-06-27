package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * MCP API 密钥 — 用户自助创建，用于外部 Agent 接入 KES。
 * 权限 = 创建者权限，密钥范围不在创建时固化。
 */
@Entity
@Table(name = "api_keys", uniqueConstraints = {
    @UniqueConstraint(columnNames = {"user_id", "name"})
})
public class ApiKey {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "user_id", nullable = false)
    private String userId;

    @Column(nullable = false, length = 128)
    private String name;

    @Column(name = "key_hash", nullable = false, length = 255)
    private String keyHash;

    @Column(name = "key_prefix", nullable = false, length = 16)
    private String keyPrefix;

    @Column(name = "expires_at", nullable = false)
    private LocalDateTime expiresAt;

    @Column(name = "last_used_at")
    private LocalDateTime lastUsedAt;

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "revoked_at")
    private LocalDateTime revokedAt;

    @Column(name = "scope_kb_ids", columnDefinition = "jsonb")
    private String scopeKbIds;  // JSON array: ["kb-1","kb-2"]，null = 无限制

    public ApiKey() {}

    public ApiKey(String id, String userId, String name, String keyHash,
                  String keyPrefix, LocalDateTime expiresAt) {
        this.id = id;
        this.userId = userId;
        this.name = name;
        this.keyHash = keyHash;
        this.keyPrefix = keyPrefix;
        this.expiresAt = expiresAt;
    }

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getKeyHash() { return keyHash; }
    public void setKeyHash(String keyHash) { this.keyHash = keyHash; }

    public String getKeyPrefix() { return keyPrefix; }
    public void setKeyPrefix(String keyPrefix) { this.keyPrefix = keyPrefix; }

    public LocalDateTime getExpiresAt() { return expiresAt; }
    public void setExpiresAt(LocalDateTime expiresAt) { this.expiresAt = expiresAt; }

    public LocalDateTime getLastUsedAt() { return lastUsedAt; }
    public void setLastUsedAt(LocalDateTime lastUsedAt) { this.lastUsedAt = lastUsedAt; }

    public LocalDateTime getCreatedAt() { return createdAt; }

    public LocalDateTime getRevokedAt() { return revokedAt; }
    public void setRevokedAt(LocalDateTime revokedAt) { this.revokedAt = revokedAt; }

    public boolean isRevoked() { return revokedAt != null; }

    public boolean isExpired() {
        return expiresAt != null && LocalDateTime.now().isAfter(expiresAt);
    }

    public String getScopeKbIds() { return scopeKbIds; }
    public void setScopeKbIds(String scopeKbIds) { this.scopeKbIds = scopeKbIds; }

    public boolean isValid() {
        return !isRevoked() && !isExpired();
    }
}
