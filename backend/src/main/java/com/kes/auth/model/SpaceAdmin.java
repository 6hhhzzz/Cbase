package com.kes.auth.model;

import jakarta.persistence.*;
import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Space 管理员实体 — v4 ACE 权限模型。
 * 直接关联 User（非用户组），分 OWNER（创建者）和 ADMIN（管理员）两级。
 * 联合主键 (space_id, user_id)。
 */
@Entity
@Table(name = "space_admins")
@IdClass(SpaceAdmin.SpaceAdminId.class)
public class SpaceAdmin {

    @Id
    @Column(name = "space_id", nullable = false, length = 36)
    private String spaceId;

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

    public SpaceAdmin() {}

    public SpaceAdmin(String spaceId, String userId, String role, String grantedBy) {
        this.spaceId = spaceId;
        this.userId = userId;
        this.role = role;
        this.grantedBy = grantedBy;
    }

    // ---- Getters / Setters ----

    public String getSpaceId() { return spaceId; }
    public void setSpaceId(String spaceId) { this.spaceId = spaceId; }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }

    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }

    public String getGrantedBy() { return grantedBy; }
    public void setGrantedBy(String grantedBy) { this.grantedBy = grantedBy; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }

    /**
     * 联合主键类 (space_id, user_id)
     */
    public static class SpaceAdminId implements Serializable {
        private String spaceId;
        private String userId;

        public SpaceAdminId() {}

        public SpaceAdminId(String spaceId, String userId) {
            this.spaceId = spaceId;
            this.userId = userId;
        }

        public String getSpaceId() { return spaceId; }
        public void setSpaceId(String spaceId) { this.spaceId = spaceId; }

        public String getUserId() { return userId; }
        public void setUserId(String userId) { this.userId = userId; }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (!(o instanceof SpaceAdminId)) return false;
            SpaceAdminId that = (SpaceAdminId) o;
            return spaceId.equals(that.spaceId) && userId.equals(that.userId);
        }

        @Override
        public int hashCode() {
            return 31 * spaceId.hashCode() + userId.hashCode();
        }
    }
}
