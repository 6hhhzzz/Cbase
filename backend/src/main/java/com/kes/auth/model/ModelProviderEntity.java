package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 模型供应商实体 — v6 模型配置管理。
 * 存储 LLM/Embedding/Reranker 等服务商配置。
 * API Key 以环境变量名存储（如 ${DASHSCOPE_API_KEY}），实际值由环境注入。
 */
@Entity
@Table(name = "model_providers")
public class ModelProviderEntity {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, length = 64, unique = true)
    private String name;

    @Column(name = "type", nullable = false, length = 32)
    private String type;  // "openai_compatible" | "ollama" | "cross_encoder"

    @Column(name = "base_url", nullable = false, length = 512)
    private String baseUrl;

    @Column(name = "api_key_env", length = 128)
    private String apiKeyEnv;  // "${DASHSCOPE_API_KEY}" — 只存变量名

    @Column(name = "is_enabled", nullable = false)
    private boolean isEnabled = true;

    @Column(name = "extra", columnDefinition = "JSONB DEFAULT '{}'")
    private String extra = "{}";

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) createdAt = LocalDateTime.now();
        if (updatedAt == null) updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public ModelProviderEntity() {}

    public ModelProviderEntity(String id, String name, String type, String baseUrl,
                                String apiKeyEnv, boolean isEnabled) {
        this.id = id;
        this.name = name;
        this.type = type;
        this.baseUrl = baseUrl;
        this.apiKeyEnv = apiKeyEnv;
        this.isEnabled = isEnabled;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getType() { return type; }
    public void setType(String type) { this.type = type; }
    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }
    public String getApiKeyEnv() { return apiKeyEnv; }
    public void setApiKeyEnv(String apiKeyEnv) { this.apiKeyEnv = apiKeyEnv; }
    public boolean getIsEnabled() { return isEnabled; }
    public void setIsEnabled(boolean isEnabled) { this.isEnabled = isEnabled; }
    public String getExtra() { return extra; }
    public void setExtra(String extra) { this.extra = extra; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
