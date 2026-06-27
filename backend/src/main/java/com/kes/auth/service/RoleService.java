package com.kes.auth.service;

import com.kes.auth.model.AccessControlEntry;
import com.kes.auth.model.Role;
import com.kes.auth.repository.AceRepository;
import com.kes.auth.repository.RoleRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

/**
 * 角色管理服务 — v4 ACE 权限模型。
 * 管理员可自定义 KB 级别的角色（权限套餐）。
 * is_system = true 的系统角色不可删除、不可修改 permissions。
 */
@Service
public class RoleService {

    private static final Logger log = LoggerFactory.getLogger(RoleService.class);

    private final RoleRepository roleRepo;
    private final AceRepository aceRepo;

    public RoleService(RoleRepository roleRepo, AceRepository aceRepo) {
        this.roleRepo = roleRepo;
        this.aceRepo = aceRepo;
    }

    /** 列出所有角色 */
    public List<Role> listRoles() {
        return roleRepo.findAll();
    }

    /** 获取单个角色 */
    public Role getRole(String roleId) {
        return roleRepo.findById(roleId)
            .orElseThrow(() -> new BusinessException(ErrorCode.ROLE_NOT_FOUND, "角色不存在: " + roleId));
    }

    /** 创建自定义角色 */
    @Transactional
    public Role createRole(String name, String description, String permissions) {
        if (name == null || name.isBlank()) {
            throw new BusinessException(ErrorCode.ROLE_NAME_EMPTY);
        }
        Role existing = roleRepo.findByName(name);
        if (existing != null) {
            throw new BusinessException(ErrorCode.ROLE_NAME_CONFLICT, "角色名称已存在: " + name);
        }
        Role role = new Role(UUID.randomUUID().toString(), name,
            description != null ? description : "",
            permissions != null ? permissions : "{}",
            false);  // 用户创建的角色 is_system = false
        role = roleRepo.save(role);
        log.info("自定义角色创建: id={}, name={}", role.getId(), name);
        return role;
    }

    /** 修改角色 */
    @Transactional
    public Role updateRole(String roleId, String name, String description, String permissions) {
        Role role = getRole(roleId);

        if (role.isSystem()) {
            // 系统角色可改名和描述，但不能改 permissions
            if (permissions != null && !permissions.equals(role.getPermissions())) {
                throw new BusinessException(ErrorCode.ROLE_SYSTEM_PROTECTED, "系统角色的权限不可修改");
            }
        } else {
            // 自定义角色可改 permissions
            if (permissions != null) {
                role.setPermissions(permissions);
            }
        }

        if (name != null && !name.isBlank() && !name.equals(role.getName())) {
            Role existing = roleRepo.findByName(name);
            if (existing != null && !existing.getId().equals(roleId)) {
                throw new BusinessException(ErrorCode.ROLE_NAME_CONFLICT, "角色名称已存在: " + name);
            }
            role.setName(name);
        }
        if (description != null) {
            role.setDescription(description);
        }

        role = roleRepo.save(role);
        log.info("角色更新: id={}, name={}", roleId, role.getName());
        return role;
    }

    /** 删除角色 */
    @Transactional
    public void deleteRole(String roleId) {
        Role role = getRole(roleId);
        if (role.isSystem()) {
            throw new BusinessException(ErrorCode.ROLE_SYSTEM_PROTECTED, "系统角色不可删除");
        }

        // 检查是否有 ACE 引用该角色
        List<AccessControlEntry> refs = aceRepo.findByRoleId(roleId);
        if (!refs.isEmpty()) {
            throw new BusinessException(ErrorCode.ROLE_IN_USE,
                "该角色被 " + refs.size() + " 条 ACE 规则引用，无法删除。请先删除相关 ACE 规则");
        }

        roleRepo.delete(role);
        log.info("角色删除: id={}, name={}", roleId, role.getName());
    }
}
