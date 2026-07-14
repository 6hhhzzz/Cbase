package com.kes.auth.service;

import com.kes.auth.model.AccessControlEntry;
import com.kes.auth.model.Role;
import com.kes.auth.repository.AceRepository;
import com.kes.auth.repository.RoleRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * RoleService 单元测试 — 角色 CRUD + 系统角色保护。
 */
@ExtendWith(MockitoExtension.class)
class RoleServiceTest {

    @Mock private RoleRepository roleRepo;
    @Mock private AceRepository aceRepo;

    private RoleService roleService;

    @BeforeEach
    void setUp() {
        roleService = new RoleService(roleRepo, aceRepo);
    }

    // ================================================================
    // listRoles / getRole
    // ================================================================

    @Test
    void listRoles_returnsAll() {
        Role admin = new Role("r-1", "Admin", "管理员", "{}", true);
        when(roleRepo.findAll()).thenReturn(List.of(admin));

        List<Role> result = roleService.listRoles();
        assertEquals(1, result.size());
    }

    @Test
    void getRole_found() {
        Role role = new Role("r-1", "Viewer", "", "{}", false);
        when(roleRepo.findById("r-1")).thenReturn(Optional.of(role));

        Role result = roleService.getRole("r-1");
        assertEquals("Viewer", result.getName());
    }

    @Test
    void getRole_notFoundThrowsException() {
        when(roleRepo.findById("r-99")).thenReturn(Optional.empty());

        BusinessException ex = assertThrows(BusinessException.class,
            () -> roleService.getRole("r-99"));
        assertEquals(ErrorCode.ROLE_NOT_FOUND.name(), ex.getErrorCode());
    }

    // ================================================================
    // createRole
    // ================================================================

    @Test
    void createRole_success() {
        when(roleRepo.findByName("Editor")).thenReturn(null);
        when(roleRepo.save(any())).thenAnswer(inv -> inv.getArgument(0));

        Role result = roleService.createRole("Editor", "编辑者", "{\"kb.read\":true}");

        assertEquals("Editor", result.getName());
        assertFalse(result.isSystem());
        assertEquals("{\"kb.read\":true}", result.getPermissions());
    }

    @Test
    void createRole_emptyNameThrowsException() {
        BusinessException ex = assertThrows(BusinessException.class,
            () -> roleService.createRole("", "", "{}"));
        assertEquals(ErrorCode.ROLE_NAME_EMPTY.name(), ex.getErrorCode());

        assertThrows(BusinessException.class,
            () -> roleService.createRole(null, "", "{}"));
    }

    @Test
    void createRole_duplicateNameThrowsException() {
        when(roleRepo.findByName("Admin")).thenReturn(new Role("r-1", "Admin", "", "{}", true));

        BusinessException ex = assertThrows(BusinessException.class,
            () -> roleService.createRole("Admin", "", "{}"));
        assertEquals(ErrorCode.ROLE_NAME_CONFLICT.name(), ex.getErrorCode());
    }

    // ================================================================
    // updateRole
    // ================================================================

    @Test
    void updateRole_systemRole_cannotChangePermissions() {
        Role systemRole = new Role("r-sys", "Admin", "管理员", "{\"admin\":true}", true);
        when(roleRepo.findById("r-sys")).thenReturn(Optional.of(systemRole));

        BusinessException ex = assertThrows(BusinessException.class,
            () -> roleService.updateRole("r-sys", null, null, "{\"admin\":false}"));
        assertEquals(ErrorCode.ROLE_SYSTEM_PROTECTED.name(), ex.getErrorCode());
    }

    @Test
    void updateRole_systemRole_canRename() {
        Role systemRole = new Role("r-sys", "Admin", "管理员", "{\"admin\":true}", true);
        when(roleRepo.findById("r-sys")).thenReturn(Optional.of(systemRole));
        when(roleRepo.findByName("超级管理员")).thenReturn(null);
        when(roleRepo.save(any())).thenAnswer(inv -> inv.getArgument(0));

        Role result = roleService.updateRole("r-sys", "超级管理员", "新描述", null);
        assertEquals("超级管理员", result.getName());
    }

    @Test
    void updateRole_customRole_canChangePermissions() {
        Role custom = new Role("r-custom", "Custom", "", "{}", false);
        when(roleRepo.findById("r-custom")).thenReturn(Optional.of(custom));
        when(roleRepo.save(any())).thenAnswer(inv -> inv.getArgument(0));

        Role result = roleService.updateRole("r-custom", null, null, "{\"kb.read\":true}");
        assertEquals("{\"kb.read\":true}", result.getPermissions());
    }

    @Test
    void updateRole_sameName_noConflict() {
        // 修改角色名称为同名不应触发冲突检测
        Role role = new Role("r-1", "Editor", "", "{}", false);
        when(roleRepo.findById("r-1")).thenReturn(Optional.of(role));
        when(roleRepo.save(any())).thenAnswer(inv -> inv.getArgument(0));

        assertDoesNotThrow(() -> roleService.updateRole("r-1", "Editor", null, null));
    }

    @Test
    void updateRole_duplicateNameThrowsException() {
        Role role = new Role("r-1", "OldName", "", "{}", false);
        Role existing = new Role("r-2", "NewName", "", "{}", false);
        when(roleRepo.findById("r-1")).thenReturn(Optional.of(role));
        when(roleRepo.findByName("NewName")).thenReturn(existing);

        BusinessException ex = assertThrows(BusinessException.class,
            () -> roleService.updateRole("r-1", "NewName", null, null));
        assertEquals(ErrorCode.ROLE_NAME_CONFLICT.name(), ex.getErrorCode());
    }

    // ================================================================
    // deleteRole
    // ================================================================

    @Test
    void deleteRole_systemRoleThrowsException() {
        Role systemRole = new Role("r-sys", "Admin", "", "{}", true);
        when(roleRepo.findById("r-sys")).thenReturn(Optional.of(systemRole));

        BusinessException ex = assertThrows(BusinessException.class,
            () -> roleService.deleteRole("r-sys"));
        assertEquals(ErrorCode.ROLE_SYSTEM_PROTECTED.name(), ex.getErrorCode());
    }

    @Test
    void deleteRole_inUseThrowsException() {
        Role custom = new Role("r-custom", "Custom", "", "{}", false);
        when(roleRepo.findById("r-custom")).thenReturn(Optional.of(custom));
        when(aceRepo.findByRoleId("r-custom")).thenReturn(List.of(new AccessControlEntry()));

        BusinessException ex = assertThrows(BusinessException.class,
            () -> roleService.deleteRole("r-custom"));
        assertEquals(ErrorCode.ROLE_IN_USE.name(), ex.getErrorCode());
    }

    @Test
    void deleteRole_success() {
        Role custom = new Role("r-custom", "Custom", "", "{}", false);
        when(roleRepo.findById("r-custom")).thenReturn(Optional.of(custom));
        when(aceRepo.findByRoleId("r-custom")).thenReturn(List.of());

        assertDoesNotThrow(() -> roleService.deleteRole("r-custom"));
        verify(roleRepo).delete(custom);
    }
}
