package com.kes.auth.controller;

import com.kes.auth.model.CreateUserRequest;
import com.kes.auth.model.UpdateUserRequest;
import com.kes.auth.model.Space;
import com.kes.auth.model.User;
import com.kes.auth.service.AdminService;
import com.kes.auth.service.UserAdminService;
import com.kes.auth.service.UserImportService;
import com.kes.common.annotation.RequireGlobalAdmin;
import com.kes.common.dto.SpaceDtos.*;
import com.kes.common.model.ApiResponse;
import com.kes.common.util.ControllerAuthHelper;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.*;

/**
 * 全局管理员控制器。
 * 仅 users.is_global_admin = TRUE 的用户可访问。
 *
 * <p>v4 重构：委托给 {@link AdminService}。
 * <p>用户管理委托给 {@link UserAdminService} 和 {@link UserImportService}。
 */
@RestController
@RequestMapping("/api/admin")
public class AdminController {


    private final AdminService adminService;
    private final UserAdminService userAdminService;
    private final UserImportService userImportService;
    private final ControllerAuthHelper authHelper;

    public AdminController(AdminService adminService,
                           UserAdminService userAdminService,
                           UserImportService userImportService,
                           ControllerAuthHelper authHelper) {
        this.adminService = adminService;
        this.userAdminService = userAdminService;
        this.userImportService = userImportService;
        this.authHelper = authHelper;
    }

    /** 列出所有 Space（仅全局管理员可见） */
    @GetMapping("/spaces")
    @RequireGlobalAdmin
    public ApiResponse<List<SpaceSummary>> getAllSpaces(
            @RequestHeader("Authorization") String authHeader) {
        List<Space> spaces = adminService.getAllSpaces(extractUserId(authHeader));
        return ApiResponse.success(spaces.stream().map(s ->
            new SpaceSummary(s.getId(), s.getName(), s.getTypeLabel(), s.getStatus(),
                s.getCreatedBy(), s.getLastAccessedAt(), s.getCreatedAt())
        ).toList());
    }

    /** 归档任意 Space */
    @PostMapping("/spaces/{spaceId}/archive")
    @RequireGlobalAdmin
    public ApiResponse<?> archiveSpace(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId) {
        String userId = extractUserId(authHeader);
        adminService.globalArchiveSpace(userId, spaceId);
        return ApiResponse.success();
    }

    /** 全局管理员软删除 Space */
    @DeleteMapping("/spaces/{spaceId}")
    @RequireGlobalAdmin
    public ApiResponse<?> deleteSpace(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId) {
        String userId = extractUserId(authHeader);
        adminService.globalDeleteSpace(userId, spaceId);
        return ApiResponse.success();
    }

    /** 恢复 Space */
    @PostMapping("/spaces/{spaceId}/restore")
    @RequireGlobalAdmin
    public ApiResponse<?> restoreSpace(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId) {
        String userId = extractUserId(authHeader);
        adminService.globalRestoreSpace(userId, spaceId);
        return ApiResponse.success();
    }

    // ================================================================
    // 用户管理（全局管理员）
    // ================================================================

    /** 列出所有用户 */
    @GetMapping("/users")
    @RequireGlobalAdmin
    public ApiResponse<List<UserInfo>> listUsers(
            @RequestHeader("Authorization") String authHeader) {
        List<User> users = userAdminService.listAllUsers(extractUserId(authHeader));
        return ApiResponse.success(users.stream().map(u ->
            new UserInfo(u.getId(), u.getUsername(), u.getDisplayName(),
                u.getIsGlobalAdmin() != null && u.getIsGlobalAdmin(), u.getCreatedAt())
        ).toList());
    }

    /** 设置/取消全局管理员 */
    @PutMapping("/users/{userId}/global-admin")
    @RequireGlobalAdmin
    public ApiResponse<?> setGlobalAdmin(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String userId,
            @RequestBody Map<String, Boolean> body) {
        String operatorId = extractUserId(authHeader);
        boolean isGA = Boolean.TRUE.equals(body.get("is_global_admin"));
        userAdminService.setGlobalAdmin(operatorId, userId, isGA);
        return ApiResponse.success();
    }

    // ---- v7 用户管理增强 ----

    /** 管理员创建单个用户 */
    @PostMapping("/users")
    @RequireGlobalAdmin
    public ApiResponse<Map<String, Object>> createUser(
            @RequestHeader("Authorization") String authHeader,
            @Valid @RequestBody CreateUserRequest req) {
        String operatorId = extractUserId(authHeader);
        User user = userAdminService.createUser(operatorId, req);
        Map<String, Object> result = new HashMap<>();
        result.put("user_id", user.getId());
        result.put("username", user.getUsername());
        result.put("display_name", user.getDisplayName());
        result.put("email", user.getEmail());
        result.put("status", user.getStatus());
        result.put("must_change_password", user.getMustChangePassword());
        result.put("created_at", user.getCreatedAt());
        return ApiResponse.success(result);
    }

    /** 管理员编辑用户信息 */
    @PutMapping("/users/{userId}")
    @RequireGlobalAdmin
    public ApiResponse<Map<String, Object>> updateUser(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String userId,
            @Valid @RequestBody UpdateUserRequest req) {
        String operatorId = extractUserId(authHeader);
        User user = userAdminService.updateUser(operatorId, userId, req);
        Map<String, Object> result = new HashMap<>();
        result.put("user_id", user.getId());
        result.put("username", user.getUsername());
        result.put("display_name", user.getDisplayName());
        result.put("email", user.getEmail());
        result.put("status", user.getStatus());
        result.put("updated_at", user.getUpdatedAt());
        return ApiResponse.success(result);
    }

    /** 启用/禁用用户 */
    @PutMapping("/users/{userId}/status")
    @RequireGlobalAdmin
    public ApiResponse<?> setUserStatus(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String userId,
            @RequestBody Map<String, String> body) {
        String operatorId = extractUserId(authHeader);
        String status = body.get("status");
        userAdminService.setUserStatus(operatorId, userId, status);
        return ApiResponse.success();
    }

    /** 批量导入用户（CSV） */
    @PostMapping("/users/batch")
    @RequireGlobalAdmin
    public ApiResponse<?> batchImportUsers(
            @RequestHeader("Authorization") String authHeader,
            @RequestParam("file") MultipartFile file) {
        String operatorId = extractUserId(authHeader);
        var result = userImportService.batchImportUsers(operatorId, file);
        return ApiResponse.success(result);
    }

    private String extractUserId(String authHeader) {
        return authHelper.extractUserId(authHeader);
    }
}
