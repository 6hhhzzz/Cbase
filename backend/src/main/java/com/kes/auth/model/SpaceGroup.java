package com.kes.auth.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Space 准入组实体 — v4 ACE 权限模型。
 * 将全局用户组分配到 Space，组内所有成员自动成为 Space 普通成员。
 */
@Entity
@Table(name = "space_groups",
       uniqueConstraints = @UniqueConstraint(columnNames = {"space_id", "group_id"}))
public class SpaceGroup {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "space_id", nullable = false, length = 36)
    private String spaceId;

    @Column(name = "group_id", nullable = false, length = 36)
    private String groupId;

    @Column(name = "joined_at", updatable = false)
    private LocalDateTime joinedAt;

    @PrePersist
    protected void onCreate() {
        if (joinedAt == null) joinedAt = LocalDateTime.now();
    }

    public SpaceGroup() {}

    public SpaceGroup(String id, String spaceId, String groupId) {
        this.id = id;
        this.spaceId = spaceId;
        this.groupId = groupId;
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getSpaceId() { return spaceId; }
    public void setSpaceId(String spaceId) { this.spaceId = spaceId; }

    public String getGroupId() { return groupId; }
    public void setGroupId(String groupId) { this.groupId = groupId; }

    public LocalDateTime getJoinedAt() { return joinedAt; }
    public void setJoinedAt(LocalDateTime joinedAt) { this.joinedAt = joinedAt; }
}
