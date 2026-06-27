package com.kes.auth.model;

import jakarta.persistence.*;
import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Group 管理员实体 — v4 ACE 权限模型。
 * 直接关联 User，分 OWNER 和 ADMIN 两级。
 * 与 Space 管理员解耦：Group admin 管"人"，Space admin 管"资产"。
 */
@Entity
@Table(name = "group_admins")
@IdClass(GroupAdmin.GroupAdminId.class)
public class GroupAdmin {

    @Id
    @Column(name = "group_id", nullable = false, length = 36)
    private String groupId;

    @Id
    @Column(name = "user_id", nullable = false, length = 36)
    private String userId;

    @Column(nullable = false, length = 20)
    private String role;  // owner | admin

    @Column(name = "granted_by", length = 36)
    private String grantedBy;

    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) createdAt = LocalDateTime.now();
    }

    public GroupAdmin() {}

    public GroupAdmin(String groupId, String userId, String role, String grantedBy) {
        this.groupId = groupId;
        this.userId = userId;
        this.role = role;
        this.grantedBy = grantedBy;
    }

    public String getGroupId() { return groupId; }
    public void setGroupId(String groupId) { this.groupId = groupId; }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }

    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }

    public String getGrantedBy() { return grantedBy; }
    public void setGrantedBy(String grantedBy) { this.grantedBy = grantedBy; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    public static class GroupAdminId implements Serializable {
        private String groupId;
        private String userId;

        public GroupAdminId() {}
        public GroupAdminId(String groupId, String userId) {
            this.groupId = groupId; this.userId = userId;
        }
        public String getGroupId() { return groupId; }
        public void setGroupId(String groupId) { this.groupId = groupId; }
        public String getUserId() { return userId; }
        public void setUserId(String userId) { this.userId = userId; }

        @Override public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof GroupAdminId that)) return false;
            return groupId.equals(that.groupId) && userId.equals(that.userId);
        }
        @Override public int hashCode() { return 31 * groupId.hashCode() + userId.hashCode(); }
    }
}
