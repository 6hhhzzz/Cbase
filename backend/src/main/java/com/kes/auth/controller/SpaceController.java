package com.kes.auth.controller;

import com.kes.auth.model.*;
import com.kes.auth.service.*;
import com.kes.common.annotation.RequireSpaceAdmin;
import com.kes.common.dto.SpaceDtos;
import com.kes.common.dto.SpaceDtos.*;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.model.ApiResponse;
import com.kes.common.util.ControllerAuthHelper;
import org.springframework.data.domain.Page;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Space 管理控制器 — v4 ACE 权限模型。
 *
 * <p>DDD 分层合规：Controller 仅负责参数接收和结果返回，
 * 所有业务逻辑和 Repository 访问均委托给 Service 层。
 */
@RestController
@RequestMapping("/api/spaces")
public class SpaceController {

    private final SpaceService spaceService;
    private final KbService kbService;
    private final AceService aceService;
    private final AdminService adminService;
    private final ControllerAuthHelper authHelper;

    public SpaceController(SpaceService spaceService, KbService kbService,
                           AceService aceService, AdminService adminService,
                           ControllerAuthHelper authHelper) {
        this.spaceService = spaceService;
        this.kbService = kbService;
        this.aceService = aceService;
        this.adminService = adminService;
        this.authHelper = authHelper;
    }

    @PostMapping
    public ApiResponse<Map<String, String>> createSpace(
            @RequestHeader("Authorization") String authHeader,
            @RequestBody Map<String, String> body) {
        String userId = extractUserId(authHeader);
        Space space = spaceService.createSpace(userId,
            body.get("name"), body.getOrDefault("type_label", "general"),
            body.getOrDefault("description", ""),
            body.getOrDefault("space_type", "default"));
        return ApiResponse.success(Map.of("space_id", space.getId(), "name", space.getName()));
    }

    // ================================================================
    // Space 管理员管理
    // ================================================================

    @GetMapping("/{spaceId}/admins")
    @RequireSpaceAdmin
    public ApiResponse<List<AdminInfo>> getAdmins(@PathVariable String spaceId) {
        return ApiResponse.success(spaceService.getAdminsWithUserInfo(spaceId));
    }

    @PostMapping("/{spaceId}/admins")
    public ApiResponse<?> addAdmin(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @RequestBody Map<String, String> body) {
        String operatorId = extractUserId(authHeader);
        String targetUserId = body.get("user_id");
        if (targetUserId == null || targetUserId.isBlank())
            throw new BusinessException(ErrorCode.PARAM_MISSING, "user_id 为必填项");
        spaceService.addSpaceAdmin(operatorId, spaceId, targetUserId,
            body.getOrDefault("role", "admin"));
        return ApiResponse.success();
    }

    @DeleteMapping("/{spaceId}/admins/{userId}")
    public ApiResponse<?> removeAdmin(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @PathVariable String userId) {
        spaceService.removeSpaceAdmin(extractUserId(authHeader), spaceId, userId);
        return ApiResponse.success();
    }

    @PostMapping("/{spaceId}/transfer-ownership")
    public ApiResponse<?> transferOwnership(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @RequestBody Map<String, String> body) {
        String newOwnerUserId = body.get("user_id");
        if (newOwnerUserId == null || newOwnerUserId.isBlank())
            throw new BusinessException(ErrorCode.PARAM_MISSING, "user_id 为必填项");
        spaceService.transferOwnership(extractUserId(authHeader), spaceId, newOwnerUserId);
        return ApiResponse.success();
    }

    // ================================================================
    // Space 准入组管理
    // ================================================================

    @GetMapping("/{spaceId}/groups")
    @RequireSpaceAdmin
    public ApiResponse<List<GroupInfo>> getGroups(@PathVariable String spaceId) {
        return ApiResponse.success(spaceService.getGroupsWithName(spaceId));
    }

    @PostMapping("/{spaceId}/groups")
    @RequireSpaceAdmin
    public ApiResponse<?> addGroup(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @RequestBody Map<String, String> body) {
        String groupId = body.get("group_id");
        if (groupId == null || groupId.isBlank())
            throw new BusinessException(ErrorCode.PARAM_MISSING, "group_id 为必填项");
        spaceService.addSpaceGroup(extractUserId(authHeader), spaceId, groupId);
        return ApiResponse.success();
    }

    @DeleteMapping("/{spaceId}/groups/{groupId}")
    @RequireSpaceAdmin
    public ApiResponse<?> removeGroup(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @PathVariable String groupId) {
        spaceService.removeSpaceGroup(extractUserId(authHeader), spaceId, groupId);
        return ApiResponse.success();
    }

    // ================================================================
    // ACE 矩阵管理
    // ================================================================

    @GetMapping("/{spaceId}/aces")
    @RequireSpaceAdmin
    public ApiResponse<List<AceInfo>> getAces(@PathVariable String spaceId,
            @RequestParam(name = "resource_type", defaultValue = "kb") String resourceType) {
        List<AccessControlEntry> aces = aceService.getAces(spaceId, resourceType);
        List<AceInfo> result = aces.stream().map(ace ->
            new AceInfo(ace.getId(), ace.getResourceType(), ace.getResourceId(),
                ace.getPrincipalType(), ace.getPrincipalId(),
                ace.getRoleId(), ace.getEffect(), ace.getPriority(), ace.getCreatedAt())
        ).toList();
        return ApiResponse.success(result);
    }

    @PostMapping("/{spaceId}/aces")
    @RequireSpaceAdmin
    public ApiResponse<Map<String, String>> createAce(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @RequestBody Map<String, Object> body) {
        String operatorId = extractUserId(authHeader);
        AccessControlEntry ace = aceService.createAce(operatorId, spaceId,
            (String) body.getOrDefault("resource_type", "kb"),
            (String) body.get("resource_id"),
            (String) body.getOrDefault("principal_type", "group"),
            (String) body.get("principal_id"),
            (String) body.get("role_id"),
            (String) body.getOrDefault("effect", "allow"),
            body.containsKey("priority") ? ((Number) body.get("priority")).intValue() : 0);
        return ApiResponse.success(Map.of("ace_id", ace.getId()));
    }

    @PutMapping("/{spaceId}/aces/{aceId}")
    @RequireSpaceAdmin
    public ApiResponse<?> updateAce(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @PathVariable String aceId,
            @RequestBody Map<String, Object> body) {
        aceService.updateAce(extractUserId(authHeader), spaceId, aceId,
            (String) body.get("role_id"), (String) body.get("effect"),
            body.containsKey("priority") ? ((Number) body.get("priority")).intValue() : null);
        return ApiResponse.success();
    }

    @DeleteMapping("/{spaceId}/aces/{aceId}")
    @RequireSpaceAdmin
    public ApiResponse<?> deleteAce(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @PathVariable String aceId) {
        aceService.deleteAce(extractUserId(authHeader), spaceId, aceId);
        return ApiResponse.success();
    }

    // ================================================================
    // Space 成员视图
    // ================================================================

    @GetMapping("/{spaceId}/members")
    @RequireSpaceAdmin
    public ApiResponse<Map<String, Object>> getMembers(@PathVariable String spaceId) {
        List<SpaceAdmin> admins = spaceService.getSpaceAdmins(spaceId);
        List<Map<String, Object>> adminList = admins.stream().map(a -> Map.of(
            "user_id", (Object) a.getUserId(), "role", a.getRole(), "type", "admin"
        )).collect(Collectors.toList());

        List<SpaceGroup> groups = spaceService.getSpaceGroups(spaceId);
        List<Map<String, Object>> groupList = new ArrayList<>();
        for (SpaceGroup sg : groups)
            groupList.add(Map.of("group_id", sg.getGroupId(), "joined_at", sg.getJoinedAt()));

        return ApiResponse.success(Map.of("admins", adminList, "groups", groupList));
    }

    // ================================================================
    // Space 归档 + KB 管理 + 回收站 + 审计日志
    // ================================================================

    @PostMapping("/{spaceId}/archive")
    @RequireSpaceAdmin
    public ApiResponse<?> archiveSpace(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId) {
        spaceService.archiveSpace(extractUserId(authHeader), spaceId);
        return ApiResponse.success();
    }

    @PostMapping("/{spaceId}/kbs")
    @RequireSpaceAdmin
    public ApiResponse<Map<String, String>> createKb(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @RequestBody Map<String, String> body) {
        KnowledgeBase kb = kbService.createKb(extractUserId(authHeader), spaceId,
            body.get("name"), body.get("description"), body.get("visibility"));
        return ApiResponse.success(Map.of(
            "kb_id", kb.getId(), "name", kb.getName(), "visibility", kb.getVisibility()));
    }

    @GetMapping("/{spaceId}/kbs")
    @RequireSpaceAdmin
    public ApiResponse<List<KbInfo>> listKbs(@PathVariable String spaceId) {
        List<KnowledgeBase> kbs = kbService.listKbs(spaceId);
        List<KbInfo> result = kbs.stream().map(kb ->
            new KbInfo(kb.getId(), kb.getName(), kb.getDescription(),
                kb.getVisibility(), kb.getCreatedBy(), kb.getCreatedAt())
        ).toList();
        return ApiResponse.success(result);
    }

    @PutMapping("/{spaceId}/kbs/{kbId}")
    public ApiResponse<?> updateKb(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @PathVariable String kbId,
            @RequestBody Map<String, String> body) {
        kbService.updateKb(extractUserId(authHeader), spaceId, kbId,
            body.get("name"), body.get("visibility"));
        return ApiResponse.success();
    }

    @PutMapping("/{spaceId}/kbs/{kbId}/metadata")
    public ApiResponse<?> updateKbMetadata(
            @RequestHeader(value = "Authorization", required = false) String authHeader,
            @RequestHeader(value = "X-Internal-Call", required = false) String internalCall,
            @PathVariable String spaceId, @PathVariable String kbId,
            @RequestBody Map<String, Object> body) {
        String userId;
        if ("true".equals(internalCall)) {
            // Python 内部调用，取 KB 创建者作为操作人
            userId = kbService.getKbCreator(kbId);
        } else {
            userId = extractUserId(authHeader);
        }
        kbService.updateKbMetadata(userId, spaceId, kbId, body);
        return ApiResponse.success();
    }

    @DeleteMapping("/{spaceId}/kbs/{kbId}")
    public ApiResponse<?> deleteKb(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @PathVariable String kbId,
            @RequestParam(defaultValue = "false") boolean permanent) {
        if (permanent) kbService.permanentDeleteKb(extractUserId(authHeader), spaceId, kbId);
        else kbService.softDeleteKb(extractUserId(authHeader), spaceId, kbId);
        return ApiResponse.success();
    }

    @PostMapping("/{spaceId}/kbs/{kbId}/restore")
    public ApiResponse<?> restoreKb(@RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId, @PathVariable String kbId) {
        kbService.restoreKb(extractUserId(authHeader), spaceId, kbId);
        return ApiResponse.success();
    }

    // ---- 回收站 ----

    @GetMapping("/{spaceId}/trash")
    @RequireSpaceAdmin
    public ApiResponse<Map<String, Object>> getTrash(@PathVariable String spaceId) {
        return ApiResponse.success(kbService.getTrashData(spaceId));
    }

    // ---- 操作日志 ----

    @GetMapping("/{spaceId}/audit-logs")
    @RequireSpaceAdmin
    public ApiResponse<Map<String, Object>> getAuditLogs(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String spaceId,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        String userId = extractUserId(authHeader);
        Page<AuditLogInfo> logs = adminService.getAuditLogsWithOperatorNames(spaceId, userId, page, size);
        return ApiResponse.success(Map.of(
            "items", logs.getContent(), "total_pages", logs.getTotalPages(),
            "total_elements", logs.getTotalElements()));
    }

    // ----

    private String extractUserId(String authHeader) {
        return authHelper.extractUserId(authHeader);
    }
}
