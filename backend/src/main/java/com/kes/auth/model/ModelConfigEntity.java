package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "model_configs",
       uniqueConstraints = {@UniqueConstraint(columnNames = {"provider_id", "model_name"})})
public class ModelConfigEntity {

    @Id
    @Column(length = 36)
    private String id;

    @ManyToOne(fetch = FetchType.EAGER)
    @JoinColumn(name = "provider_id", nullable = false)
    private ModelProviderEntity provider;

    @Column(name = "model_name", nullable = false, length = 128)
    private String modelName;

    @Column(name = "model_type", nullable = false, length = 32)
    private String modelType;  // "chat" | "embedding" | "reranker"

    @Column(name = "dimension")
    private Integer dimension;

    @Column(name = "max_tokens")
    private Integer maxTokens;

    @Column(name = "is_enabled", nullable = false)
    private boolean isEnabled = true;

    @Column(name = "extra", columnDefinition = "JSONB DEFAULT '{}'")
    private String extra = "{}";

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) createdAt = LocalDateTime.now();
    }

    public ModelConfigEntity() {}

    public ModelConfigEntity(String id, ModelProviderEntity provider, String modelName,
                              String modelType, Integer dimension, Integer maxTokens) {
        this.id = id;
        this.provider = provider;
        this.modelName = modelName;
        this.modelType = modelType;
        this.dimension = dimension;
        this.maxTokens = maxTokens;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public ModelProviderEntity getProvider() { return provider; }
    public void setProvider(ModelProviderEntity provider) { this.provider = provider; }
    public String getModelName() { return modelName; }
    public void setModelName(String modelName) { this.modelName = modelName; }
    public String getModelType() { return modelType; }
    public void setModelType(String modelType) { this.modelType = modelType; }
    public Integer getDimension() { return dimension; }
    public void setDimension(Integer dimension) { this.dimension = dimension; }
    public Integer getMaxTokens() { return maxTokens; }
    public void setMaxTokens(Integer maxTokens) { this.maxTokens = maxTokens; }
    public boolean getIsEnabled() { return isEnabled; }
    public void setIsEnabled(boolean isEnabled) { this.isEnabled = isEnabled; }
    public String getExtra() { return extra; }
    public void setExtra(String extra) { this.extra = extra; }
    public LocalDateTime getCreatedAt() { return createdAt; }
}
