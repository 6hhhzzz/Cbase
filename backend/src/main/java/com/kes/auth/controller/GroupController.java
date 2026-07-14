package com.kes.auth.controller;

import com.kes.auth.model.GroupAdmin;
import com.kes.auth.model.UserGroup;
import com.kes.auth.service.GroupService;
import com.kes.common.dto.SpaceDtos.AdminInfo;
import com.kes.common.dto.SpaceDtos.GroupDetailInfo;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.model.ApiResponse;
import com.kes.common.util.ControllerAuthHelper;
import org.springframework.web.bind.annotation.*;

import java.util.*;
import java.util.stream.Collectors;

/**
 * 全局用户组管理控制器 — v4 ACE 权限模型。
 */
@RestController
@RequestMapping("/api/groups")
public class GroupController {

    private final GroupService groupService;
    private final ControllerAuthHelper authHelper;

    public GroupController(GroupService groupService, ControllerAuthHelper authHelper) {
        this.groupService = groupService;
        this.authHelper = authHelper;
    }

    /** 创建全局用户组 */
    @PostMapping
    public ApiResponse<Map<String, String>> createGroup(
            @RequestHeader("Authorization") String authHeader,
            @RequestBody Map<String, String> body) {
        String userId = extractUserId(authHeader);
        UserGroup group = groupService.createGroup(
            body.get("name"),
            body.get("description"),
            body.get("parent_group_id"),
            userId);
        return ApiResponse.success(Map.of("group_id", group.getId(), "name", group.getName()));
    }

    /** 列出用户组（?parent_id= 筛选子组，不传则列出根组） */
    @GetMapping
    public ApiResponse<List<GroupDetailInfo>> listGroups(
            @RequestParam(name = "parent_id", required = false) String parentId) {
        List<UserGroup> groups;
        if (parentId != null && !parentId.isBlank()) {
            groups = groupService.listChildGroups(parentId);
        } else {
            groups = groupService.listRootGroups();
        }
        List<GroupDetailInfo> result = groups.stream()
            .map(this::toDto).collect(Collectors.toList());
        return ApiResponse.success(result);
    }

    @GetMapping("/{groupId}")
    public ApiResponse<GroupDetailInfo> getGroup(@PathVariable String groupId) {
        return ApiResponse.success(toDto(groupService.getGroup(groupId)));
    }

    @PutMapping("/{groupId}")
    public ApiResponse<GroupDetailInfo> updateGroup(
            @PathVariable String groupId, @RequestBody Map<String, Object> body) {
        Boolean isSA = body.containsKey("is_system_admin")
            ? (Boolean) body.get("is_system_admin") : null;
        UserGroup group = groupService.updateGroup(groupId,
            (String) body.get("name"), (String) body.get("description"),
            (String) body.get("parent_group_id"), isSA);
        return ApiResponse.success(toDto(group));
    }

    /** 删除用户组 */
    @DeleteMapping("/{groupId}")
    public ApiResponse<?> deleteGroup(@PathVariable String groupId) {
        groupService.deleteGroup(groupId);
        return ApiResponse.success();
    }

    // ---- Group 管理员管理 ----

    @GetMapping("/{groupId}/admins")
    public ApiResponse<List<AdminInfo>> getAdmins(@PathVariable String groupId) {
        List<GroupAdmin> admins = groupService.getGroupAdmins(groupId);
        return ApiResponse.success(admins.stream().map(a ->
            new AdminInfo(a.getUserId(), "", "", a.getRole(), a.getGrantedBy(), null)
        ).toList());
    }

    @PostMapping("/{groupId}/admins")
    public ApiResponse<?> addAdmin(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String groupId,
            @RequestBody Map<String, String> body) {
        String operatorId = extractUserId(authHeader);
        String userId = body.get("user_id");
        if (userId == null || userId.isBlank()) throw new BusinessException(ErrorCode.PARAM_MISSING, "user_id 为必填项");
        groupService.addGroupAdmin(operatorId, groupId, userId,
            body.getOrDefault("role", "admin"));
        return ApiResponse.success();
    }

    @DeleteMapping("/{groupId}/admins/{userId}")
    public ApiResponse<?> removeAdmin(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String groupId,
            @PathVariable String userId) {
        String operatorId = extractUserId(authHeader);
        groupService.removeGroupAdmin(operatorId, groupId, userId);
        return ApiResponse.success();
    }

    // ---- 组成员管理 ----

    /** 获取组成员列表（含用户名和显示名） */
    @GetMapping("/{groupId}/members")
    public ApiResponse<List<Map<String, String>>> getMembers(@PathVariable String groupId) {
        return ApiResponse.success(groupService.getDirectMembers(groupId));
    }

    /** 添加成员 */
    @PostMapping("/{groupId}/members")
    public ApiResponse<?> addMember(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String groupId,
            @RequestBody Map<String, String> body) {
        String operatorId = extractUserId(authHeader);
        if (!groupService.canManageGroup(groupId, operatorId))
            throw new BusinessException(ErrorCode.GROUP_ADMIN_REQUIRED, "无权限管理该组成员");
        String userId = body.get("user_id");
        if (userId == null || userId.isBlank()) {
            throw new BusinessException(ErrorCode.PARAM_MISSING, "user_id 为必填项");
        }
        groupService.addMember(groupId, userId);
        return ApiResponse.success();
    }

    /** 移除成员 */
    @DeleteMapping("/{groupId}/members/{userId}")
    public ApiResponse<?> removeMember(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String groupId,
            @PathVariable String userId) {
        String operatorId = extractUserId(authHeader);
        if (!groupService.canManageGroup(groupId, operatorId))
            throw new BusinessException(ErrorCode.GROUP_ADMIN_REQUIRED, "无权限管理该组成员");
        groupService.removeMember(groupId, userId);
        return ApiResponse.success();
    }

    // ----

    private GroupDetailInfo toDto(UserGroup g) {
        long memberCount = groupService.countMembers(g.getId());
        return new GroupDetailInfo(g.getId(), g.getName(), g.getDescription(),
            g.getParentGroupId(), g.isSystemAdmin(), memberCount, g.getCreatedAt());
    }

    private String extractUserId(String authHeader) {
        return authHelper.extractUserId(authHeader);
    }
}
