package com.kes.auth.model;

import java.util.List;

/**
 * 用户信息 — v3 Space/KB RBAC。
 */
public record UserInfo(
    String id,
    String username,
    String displayName,
    boolean isGlobalAdmin,
    List<SpaceInfo> spaces
) {
    /**
     * 单个 Space 的简要信息（用于前端渲染 Space 选择页）。
     */
    public record SpaceInfo(
        String spaceId,
        String spaceName,
        String role
    ) {}
}
