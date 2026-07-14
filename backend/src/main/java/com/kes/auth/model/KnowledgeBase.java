package com.kes.auth.model;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

/**
 * 知识库实体 — v3 Space/KB RBAC。
 * 一个 Space 下可有多个 KB，每个 KB 有独立的可见范围 (space_wide | restricted)。
 */
@Entity
@Table(name = "knowledge_bases")
public class KnowledgeBase {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "space_id", nullable = false, length = 36)
    private String spaceId;

    @Column(nullable = false, length = 128)
    private String name;

    @Column(columnDefinition = "TEXT")
    private String description;

    @Column(nullable = false, length = 16)
    private String visibility;  // space_wide | restricted

    @Column(name = "deleted_at")
    private LocalDateTime deletedAt;

    @Column(name = "created_by", nullable = false, length = 36)
    private String createdBy;

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "metadata", columnDefinition = "jsonb")
    private Map<String, Object> metadata = new HashMap<>();

    @PrePersist
    protected void onCreate() {
        LocalDateTime now = LocalDateTime.now();
        if (createdAt == null) createdAt = now;
        if (updatedAt == null) updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public KnowledgeBase() {}

    public KnowledgeBase(String id, String spaceId, String name, String description,
                         String visibility, String createdBy) {
        this.id = id;
        this.spaceId = spaceId;
        this.name = name;
        this.description = description;
        this.visibility = visibility;
        this.createdBy = createdBy;
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getSpaceId() { return spaceId; }
    public void setSpaceId(String spaceId) { this.spaceId = spaceId; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public String getVisibility() { return visibility; }
    public void setVisibility(String visibility) { this.visibility = visibility; }

    public LocalDateTime getDeletedAt() { return deletedAt; }
    public void setDeletedAt(LocalDateTime deletedAt) { this.deletedAt = deletedAt; }

    public String getCreatedBy() { return createdBy; }
    public void setCreatedBy(String createdBy) { this.createdBy = createdBy; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }

    public Map<String, Object> getMetadata() { return metadata; }
    public void setMetadata(Map<String, Object> metadata) { this.metadata = metadata; }
}
