package com.kes.auth.controller;

import com.kes.auth.model.Role;
import com.kes.auth.service.RoleService;
import com.kes.common.dto.SpaceDtos.RoleInfo;
import com.kes.common.model.ApiResponse;
import org.springframework.web.bind.annotation.*;

import java.util.*;

/**
 * 角色管理控制器 — v4 ACE 权限模型。
 */
@RestController
@RequestMapping("/api/roles")
public class RoleController {

    private final RoleService roleService;

    public RoleController(RoleService roleService) {
        this.roleService = roleService;
    }

    @GetMapping
    public ApiResponse<List<RoleInfo>> listRoles() {
        return ApiResponse.success(roleService.listRoles().stream()
            .map(this::toDto).toList());
    }

    @GetMapping("/{roleId}")
    public ApiResponse<RoleInfo> getRole(@PathVariable String roleId) {
        return ApiResponse.success(toDto(roleService.getRole(roleId)));
    }

    @PostMapping
    public ApiResponse<Map<String, String>> createRole(@RequestBody Map<String, String> body) {
        Role role = roleService.createRole(
            body.get("name"), body.get("description"), body.get("permissions"));
        return ApiResponse.success(Map.of("role_id", role.getId(), "name", role.getName()));
    }

    @PutMapping("/{roleId}")
    public ApiResponse<RoleInfo> updateRole(@PathVariable String roleId,
            @RequestBody Map<String, String> body) {
        Role role = roleService.updateRole(roleId,
            body.get("name"), body.get("description"), body.get("permissions"));
        return ApiResponse.success(toDto(role));
    }

    @DeleteMapping("/{roleId}")
    public ApiResponse<?> deleteRole(@PathVariable String roleId) {
        roleService.deleteRole(roleId);
        return ApiResponse.success();
    }

    private RoleInfo toDto(Role r) {
        return new RoleInfo(r.getId(), r.getName(), r.getDescription(),
            r.getPermissions(), r.isSystem(), r.getCreatedAt());
    }
}
