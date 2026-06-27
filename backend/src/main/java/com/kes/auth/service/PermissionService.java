package com.kes.auth.service;

import com.kes.auth.model.*;
import com.kes.auth.repository.*;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.util.JwtUtil;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * 统一权限校验服务 — v4 ACE 权限模型。
 * 全项目唯一的权限决策点。
 *
 * <p>三层身份判定：
 * <ol>
 *   <li>全局超级管理员 — users.is_global_admin 或 user_groups.is_system_admin</li>
 *   <li>Space 管理员 — space_admins (owner | admin)</li>
 *   <li>Space 普通成员 — space_groups 关联的全局用户组（含嵌套展开）</li>
 * </ol>
 *
 * <p>KB 级别权限通过 ACE 表（access_control_entries）控制。
 */
@Service
public class PermissionService {

    private static final Logger log = LoggerFactory.getLogger(PermissionService.class);

    private final SpaceAdminRepository spaceAdminRepo;
    private final SpaceGroupRepository spaceGroupRepo;
    private final UserGroupMemberRepository groupMemberRepo;
    private final UserGroupRepository groupRepo;
    private final UserRepository userRepo;
    private final KnowledgeBaseRepository kbRepo;
    private final AceRepository aceRepo;
    private final RoleRepository roleRepo;
    private final JwtUtil jwtUtil;
    private final GroupService groupService;
    private final ObjectMapper objectMapper;

    public PermissionService(SpaceAdminRepository spaceAdminRepo,
                             SpaceGroupRepository spaceGroupRepo,
                             UserGroupMemberRepository groupMemberRepo,
                             UserGroupRepository groupRepo,
                             UserRepository userRepo,
                             KnowledgeBaseRepository kbRepo,
                             AceRepository aceRepo,
                             RoleRepository roleRepo,
                             JwtUtil jwtUtil,
                             GroupService groupService,
                             ObjectMapper objectMapper) {
        this.spaceAdminRepo = spaceAdminRepo;
        this.spaceGroupRepo = spaceGroupRepo;
        this.groupMemberRepo = groupMemberRepo;
        this.groupRepo = groupRepo;
        this.userRepo = userRepo;
        this.kbRepo = kbRepo;
        this.aceRepo = aceRepo;
        this.roleRepo = roleRepo;
        this.jwtUtil = jwtUtil;
        this.groupService = groupService;
        this.objectMapper = objectMapper;
    }

    // ============================================================
    // 全局超级管理员
    // ============================================================

    /** 当前用户必须是全局超级管理员 */
    public void requireGlobalAdmin() {
        String userId = getCurrentUserId();
        requireGlobalAdmin(userId);
    }

    public void requireGlobalAdmin(String userId) {
        if (!isGlobalAdmin(userId)) {
            throw new BusinessException(ErrorCode.GLOBAL_ADMIN_REQUIRED);
        }
    }

    /**
     * 判断用户是否为全局超级管理员。
     * 两个来源：users.is_global_admin = true 或 用户属于 is_system_admin = true 的组。
     */
    public boolean isGlobalAdmin(String userId) {
        // 来源 1: users.is_global_admin
        boolean userFlag = userRepo.findById(userId)
            .map(u -> u.getIsGlobalAdmin() != null && u.getIsGlobalAdmin())
            .orElse(false);
        if (userFlag) return true;

        // 来源 2: 用户属于 is_system_admin 的全局组
        List<String> userGroupIds = groupMemberRepo.findGroupIdsByUserId(userId);
        if (userGroupIds.isEmpty()) return false;

        return groupRepo.findAllById(userGroupIds).stream()
            .anyMatch(UserGroup::isSystemAdmin);
    }

    // ============================================================
    // Space 管理员 — 查 space_admins 表
    // ============================================================

    /** 当前用户必须是当前 Space 的管理员（owner 或 admin） */
    public void requireSpaceAdmin() {
        String spaceId = getCurrentSpaceId();
        String userId = getCurrentUserId();
        requireSpaceAdmin(spaceId, userId);
    }

    /** 指定用户必须是指定 Space 的管理员 */
    public void requireSpaceAdmin(String spaceId, String userId) {
        if (isGlobalAdmin(userId)) return;
        if (!isSpaceAdmin(spaceId, userId)) {
            throw new BusinessException(ErrorCode.SPACE_ADMIN_REQUIRED);
        }
    }

    public boolean isSpaceAdmin(String spaceId, String userId) {
        return spaceAdminRepo.existsBySpaceIdAndUserId(spaceId, userId);
    }

    // ============================================================
    // 细粒度权限（KB/文档级别）— v4 ACE + 自定义角色
    // ============================================================

    /**
     * 判断用户对指定 KB 是否有某项权限。
     * 全局管理员和 Space 管理员自动拥有所有权限。
     */
    public boolean hasPermission(String userId, String spaceId, String kbId,
                                  String requiredPermission) {
        if (isGlobalAdmin(userId)) return true;
        if (isSpaceAdmin(spaceId, userId)) return true;

        return collectPermissions(userId, spaceId, kbId).contains(requiredPermission);
    }

    /**
     * 收集用户在指定 KB 上的所有权限（来自匹配的 ACE 条目中的角色）。
     */
    public Set<String> collectPermissions(String userId, String spaceId, String kbId) {
        Set<String> allPerms = new HashSet<>();

        // 1. 获取用户有效组
        Set<String> effectiveGroups = groupService.expandUserEffectiveGroups(userId);

        // 2. 查询该 KB 的所有 ACE 条目
        List<AccessControlEntry> aces = aceRepo.findBySpaceIdAndResourceTypeAndResourceId(
            spaceId, "kb", kbId);

        // 3. 筛选匹配当前用户（含组）的 ACE 条目
        Set<String> roleIds = new HashSet<>();
        for (AccessControlEntry ace : aces) {
            boolean match = "user".equals(ace.getPrincipalType())
                && userId.equals(ace.getPrincipalId());
            if (!match) {
                match = "group".equals(ace.getPrincipalType())
                    && effectiveGroups.contains(ace.getPrincipalId());
            }
            if (match && ace.getRoleId() != null) {
                roleIds.add(ace.getRoleId());
            }
        }

        if (roleIds.isEmpty()) return allPerms;

        // 4. 加载角色，解析 permissions JSONB
        List<Role> roles = roleRepo.findAllById(roleIds);
        for (Role role : roles) {
            allPerms.addAll(parsePermissions(role.getPermissions()));
        }

        return allPerms;
    }

    /**
     * 解析 permissions JSON 字符串为权限集合。
     * 支持两种格式:
     *   - JSON 数组: ["kb.read","kb.write"]
     *   - JSON 对象: {"kb.read":true,"kb.write":true}
     */
    private Set<String> parsePermissions(String permissions) {
        if (permissions == null || permissions.isBlank()) return Set.of();
        try {
            // 尝试解析为 JSON 数组
            if (permissions.trim().startsWith("[")) {
                List<String> list = objectMapper.readValue(permissions,
                    new TypeReference<List<String>>() {});
                return new HashSet<>(list);
            }
            // 解析为 JSON 对象
            Map<String, Boolean> map = objectMapper.readValue(permissions,
                new TypeReference<Map<String, Boolean>>() {});
            Set<String> result = new HashSet<>();
            map.forEach((k, v) -> { if (Boolean.TRUE.equals(v)) result.add(k); });
            return result;
        } catch (Exception e) {
            log.warn("解析角色权限失败: {}", permissions, e);
            return Set.of();
        }
    }

    // ============================================================
    // Space Owner — 仅 owner 可执行的操作
    // ============================================================

    /** 当前用户必须是 Space 的 owner */
    public void requireSpaceOwner(String spaceId, String userId) {
        if (isGlobalAdmin(userId)) return;
        boolean isOwner = spaceAdminRepo.existsBySpaceIdAndUserIdAndRole(spaceId, userId, "owner");
        if (!isOwner) {
            throw new BusinessException(ErrorCode.SPACE_OWNER_REQUIRED, "仅 Space 拥有者 (owner) 可执行此操作");
        }
    }

    public boolean isSpaceOwner(String spaceId, String userId) {
        return spaceAdminRepo.existsBySpaceIdAndUserIdAndRole(spaceId, userId, "owner");
    }

    // ============================================================
    // Space 成员 — 查 space_groups + 组展开
    // ============================================================

    /** 当前用户必须是当前 Space 的成员（包括管理员和通过组的普通成员） */
    public void requireSpaceMember() {
        String spaceId = getCurrentSpaceId();
        String userId = getCurrentUserId();
        requireSpaceMember(spaceId, userId);
    }

    /** 指定用户必须是指定 Space 的成员 */
    public void requireSpaceMember(String spaceId, String userId) {
        if (isGlobalAdmin(userId)) return;
        if (isSpaceAdmin(spaceId, userId)) return;
        if (!isSpaceMember(spaceId, userId)) {
            throw new BusinessException(ErrorCode.SPACE_ACCESS_DENIED);
        }
    }

    /**
     * 判断用户是否为 Space 成员。
     * 成员身份来源：space_admins（管理员）或 space_groups（通过全局组）。
     */
    public boolean isSpaceMember(String spaceId, String userId) {
        // 管理员也算成员
        if (spaceAdminRepo.existsBySpaceIdAndUserId(spaceId, userId)) return true;

        // 获取用户在 Space 中的有效组
        return !getUserSpaceGroups(spaceId, userId).isEmpty();
    }

    /**
     * 获取用户在 Space 中的有效组 ID 列表（含嵌套展开）。
     * 返回用户在 space_groups 中匹配的 group_id 集合。
     */
    public Set<String> getUserSpaceGroups(String spaceId, String userId) {
        // 用户的有效全局组（含层级展开）
        Set<String> effectiveGroups = groupService.expandUserEffectiveGroups(userId);
        if (effectiveGroups.isEmpty()) return Set.of();

        // Space 的准入组
        List<String> spaceGroupIds = spaceGroupRepo.findGroupIdsBySpaceId(spaceId);

        // 交集：用户的有效组 ∩ Space 的准入组
        Set<String> result = new LinkedHashSet<>(effectiveGroups);
        result.retainAll(spaceGroupIds);
        return result;
    }

    // ============================================================
    // 用户在 Space 中的角色
    // ============================================================

    /**
     * 获取用户在当前 Space 中的最高角色。
     * 返回 "owner" | "admin" | "member" | null（非成员）。
     */
    public String getUserSpaceRole(String spaceId, String userId) {
        if (isGlobalAdmin(userId)) return "owner";

        Optional<SpaceAdmin> admin = spaceAdminRepo.findBySpaceIdAndUserId(spaceId, userId);
        if (admin.isPresent()) {
            return admin.get().getRole();  // owner 或 admin
        }

        if (!getUserSpaceGroups(spaceId, userId).isEmpty()) {
            return "member";
        }

        return null;
    }

    // ============================================================
    // 从 SecurityContext 提取身份信息
    // ============================================================

    /** 从 Spring SecurityContext 获取当前 userId（JWT subject） */
    public String getCurrentUserId() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated()) {
            throw BusinessException.forbidden("未登录或 Token 已过期");
        }
        return auth.getName();
    }

    /** 从当前 Context Token 中提取 spaceId */
    public String getCurrentSpaceId() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || auth.getCredentials() == null) {
            throw BusinessException.forbidden("未登录或缺少上下文 Token");
        }
        String token = (String) auth.getCredentials();
        String spaceId = jwtUtil.extractSpaceId(token);
        if (spaceId == null) {
            throw BusinessException.forbidden("无法从 Token 中提取 Space 上下文");
        }
        return spaceId;
    }

    /** 从当前 Context Token 中提取 role */
    public String getCurrentRole() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || auth.getCredentials() == null) {
            return null;
        }
        return jwtUtil.extractContextRole((String) auth.getCredentials());
    }
}
