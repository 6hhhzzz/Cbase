package com.kes.common.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.LocalDateTime;

/** Space 管理相关响应 DTO。 */
public final class SpaceDtos {

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record AdminInfo(
        String userId, String username, String displayName,
        String role, String grantedBy, LocalDateTime createdAt
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record GroupInfo(
        String id, String groupId, String groupName, boolean isSystemAdmin, LocalDateTime joinedAt
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record AceInfo(
        String id, String resourceType, String resourceId,
        String principalType, String principalId,
        String roleId, String effect, Integer priority,
        LocalDateTime createdAt
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record KbInfo(
        String kbId, String name, String description,
        String visibility, String createdBy, LocalDateTime createdAt
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record TrashItem(
        String type, String id, String name,
        String kbId, String kbName, String fileType,
        LocalDateTime deletedAt, LocalDateTime expiresAt,
        Integer daysRemaining
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record AuditLogInfo(
        Object id, String operatorId, String operatorName,
        String action, String targetType, String targetId, String targetName,
        String details, LocalDateTime createdAt
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record UserInfo(
        String userId, String username, String displayName,
        boolean isGlobalAdmin, String email, String status, LocalDateTime createdAt
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record KbAccessInfo(
        String kbId, String name, String description, String visibility,
        String spaceType
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record RoleInfo(
        String id, String name, String description, String permissions,
        boolean isSystem, LocalDateTime createdAt
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record GroupDetailInfo(
        String groupId, String name, String description, String parentGroupId,
        boolean isSystemAdmin, long memberCount, LocalDateTime createdAt
    ) {}

    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record SpaceSummary(
        String spaceId, String name, String typeLabel, String status,
        String createdBy, LocalDateTime lastAccessedAt, LocalDateTime createdAt
    ) {}

    private SpaceDtos() {}
}
