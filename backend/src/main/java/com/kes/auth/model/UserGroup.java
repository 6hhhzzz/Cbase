package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 全局用户组实体 — v4 ACE 权限模型。
 * 支持嵌套（parent_group_id 自引用），is_system_admin 标记超级管理员组。
 */
@Entity
@Table(name = "user_groups")
public class UserGroup {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "parent_group_id", length = 36)
    private String parentGroupId;

    @Column(nullable = false, length = 128)
    private String name;

    @Column(columnDefinition = "TEXT DEFAULT ''")
    private String description;

    @Column(name = "is_system_admin", nullable = false)
    private boolean isSystemAdmin = false;

    @Column(name = "created_by", nullable = false, length = 36)
    private String createdBy;

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

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

    public UserGroup() {}

    public UserGroup(String id, String name, String parentGroupId, String createdBy) {
        this.id = id;
        this.name = name;
        this.parentGroupId = parentGroupId;
        this.createdBy = createdBy;
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getParentGroupId() { return parentGroupId; }
    public void setParentGroupId(String parentGroupId) { this.parentGroupId = parentGroupId; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public boolean isSystemAdmin() { return isSystemAdmin; }
    public void setSystemAdmin(boolean systemAdmin) { isSystemAdmin = systemAdmin; }

    public String getCreatedBy() { return createdBy; }
    public void setCreatedBy(String createdBy) { this.createdBy = createdBy; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
