package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 角色定义实体 — v4 ACE 权限模型。
 * 管理员可自定义角色，permissions JSONB 定义权限集。
 * is_system = true 的系统角色不可删除、不可修改 permissions。
 */
@Entity
@Table(name = "roles")
public class Role {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, length = 64)
    private String name;

    @Column(columnDefinition = "TEXT DEFAULT ''")
    private String description;

    @Column(nullable = false, columnDefinition = "JSONB DEFAULT '{}'")
    private String permissions;  // JSONB: {"doc:read": true, "doc:write": true, ...}

    @Column(name = "is_system", nullable = false)
    private boolean isSystem = false;

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) createdAt = LocalDateTime.now();
    }

    public Role() {}

    public Role(String id, String name, String description, String permissions, boolean isSystem) {
        this.id = id;
        this.name = name;
        this.description = description;
        this.permissions = permissions;
        this.isSystem = isSystem;
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }

    public String getPermissions() { return permissions; }
    public void setPermissions(String permissions) { this.permissions = permissions; }

    public boolean isSystem() { return isSystem; }
    public void setSystem(boolean system) { isSystem = system; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
