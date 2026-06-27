package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * ACE 核心权限实体 — v4 ACE 权限模型。
 * 记录「谁 (principal) 对什么资源 (resource) 拥有什么角色 (role)」。
 * principal 可以是用户组 (group) 或用户 (user)，resource 可以是 KB 或 Document。
 * effect: allow | deny（deny 始终覆盖 allow）。
 */
@Entity
@Table(name = "access_control_entries",
       uniqueConstraints = @UniqueConstraint(columnNames = {
           "space_id", "resource_type", "resource_id", "principal_type", "principal_id"}))
public class AccessControlEntry {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "space_id", nullable = false, length = 36)
    private String spaceId;

    @Column(name = "resource_type", nullable = false, length = 16)
    private String resourceType;  // kb | document

    @Column(name = "resource_id", nullable = false, length = 36)
    private String resourceId;

    @Column(name = "principal_type", nullable = false, length = 16)
    private String principalType;  // group | user

    @Column(name = "principal_id", nullable = false, length = 36)
    private String principalId;

    @Column(name = "role_id", nullable = false, length = 36)
    private String roleId;

    @Column(nullable = false, length = 8)
    private String effect = "allow";  // allow | deny

    @Column(nullable = false)
    private int priority = 0;

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

    public AccessControlEntry() {}

    public AccessControlEntry(String id, String spaceId, String resourceType, String resourceId,
                              String principalType, String principalId, String roleId,
                              String effect, int priority) {
        this.id = id;
        this.spaceId = spaceId;
        this.resourceType = resourceType;
        this.resourceId = resourceId;
        this.principalType = principalType;
        this.principalId = principalId;
        this.roleId = roleId;
        this.effect = effect;
        this.priority = priority;
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getSpaceId() { return spaceId; }
    public void setSpaceId(String spaceId) { this.spaceId = spaceId; }

    public String getResourceType() { return resourceType; }
    public void setResourceType(String resourceType) { this.resourceType = resourceType; }

    public String getResourceId() { return resourceId; }
    public void setResourceId(String resourceId) { this.resourceId = resourceId; }

    public String getPrincipalType() { return principalType; }
    public void setPrincipalType(String principalType) { this.principalType = principalType; }

    public String getPrincipalId() { return principalId; }
    public void setPrincipalId(String principalId) { this.principalId = principalId; }

    public String getRoleId() { return roleId; }
    public void setRoleId(String roleId) { this.roleId = roleId; }

    public String getEffect() { return effect; }
    public void setEffect(String effect) { this.effect = effect; }

    public int getPriority() { return priority; }
    public void setPriority(int priority) { this.priority = priority; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
