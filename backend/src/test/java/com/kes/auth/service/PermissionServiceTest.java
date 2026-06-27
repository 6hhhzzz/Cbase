package com.kes.auth.service;

import com.kes.auth.model.User;
import com.kes.auth.model.UserGroup;
import com.kes.auth.repository.*;
import com.kes.common.exception.BusinessException;
import com.kes.common.util.JwtUtil;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

/**
 * PermissionService 单元测试 — v4 ACE 三层权限校验。
 */
@ExtendWith(MockitoExtension.class)
class PermissionServiceTest {

    @Mock private SpaceAdminRepository spaceAdminRepo;
    @Mock private SpaceGroupRepository spaceGroupRepo;
    @Mock private UserGroupMemberRepository groupMemberRepo;
    @Mock private UserGroupRepository groupRepo;
    @Mock private UserRepository userRepo;
    @Mock private KnowledgeBaseRepository kbRepo;
    @Mock private AceRepository aceRepo;
    @Mock private RoleRepository roleRepo;
    @Mock private JwtUtil jwtUtil;
    @Mock private GroupService groupService;
    @Mock private ObjectMapper objectMapper;

    private PermissionService permissionService;

    private static final String USER_ID = "user-001";
    private static final String SPACE_ID = "space-001";
    private static final String GROUP_ID = "group-001";

    @BeforeEach
    void setUp() {
        permissionService = new PermissionService(
            spaceAdminRepo, spaceGroupRepo, groupMemberRepo,
            groupRepo, userRepo, kbRepo, aceRepo, roleRepo,
            jwtUtil, groupService, objectMapper
        );
    }

    // ================================================================
    // 全局管理员测试
    // ================================================================

    @Test
    void isGlobalAdmin_userFlag_true() {
        User user = new User(USER_ID, "admin", "pass", "Admin");
        user.setIsGlobalAdmin(true);
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(user));

        assertTrue(permissionService.isGlobalAdmin(USER_ID));
    }

    @Test
    void isGlobalAdmin_systemAdminGroup_true() {
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(new User()));
        when(groupMemberRepo.findGroupIdsByUserId(USER_ID))
            .thenReturn(List.of(GROUP_ID));
        UserGroup sysGroup = new UserGroup();
        sysGroup.setSystemAdmin(true);
        when(groupRepo.findAllById(List.of(GROUP_ID)))
            .thenReturn(List.of(sysGroup));

        assertTrue(permissionService.isGlobalAdmin(USER_ID));
    }

    @Test
    void isGlobalAdmin_regularUser_false() {
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(new User()));
        when(groupMemberRepo.findGroupIdsByUserId(USER_ID)).thenReturn(List.of());

        assertFalse(permissionService.isGlobalAdmin(USER_ID));
    }

    @Test
    void requireGlobalAdmin_throwsWhenNotAdmin() {
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(new User()));
        when(groupMemberRepo.findGroupIdsByUserId(USER_ID)).thenReturn(List.of());

        assertThrows(BusinessException.class,
            () -> permissionService.requireGlobalAdmin(USER_ID));
    }

    // ================================================================
    // Space 管理员测试
    // ================================================================

    @Test
    void isSpaceAdmin_true() {
        when(spaceAdminRepo.existsBySpaceIdAndUserId(SPACE_ID, USER_ID))
            .thenReturn(true);

        assertTrue(permissionService.isSpaceAdmin(SPACE_ID, USER_ID));
    }

    @Test
    void isSpaceAdmin_false() {
        when(spaceAdminRepo.existsBySpaceIdAndUserId(SPACE_ID, USER_ID))
            .thenReturn(false);

        assertFalse(permissionService.isSpaceAdmin(SPACE_ID, USER_ID));
    }

    @Test
    void requireSpaceAdmin_globalAdminBypasses() {
        User user = new User(USER_ID, "admin", "pass", "Admin");
        user.setIsGlobalAdmin(true);
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(user));

        // 全局管理员应跳过 space_admin 检查，不抛异常
        assertDoesNotThrow(() ->
            permissionService.requireSpaceAdmin(SPACE_ID, USER_ID));
    }

    @Test
    void requireSpaceAdmin_throwsWhenNotAdmin() {
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(new User()));
        when(groupMemberRepo.findGroupIdsByUserId(USER_ID)).thenReturn(List.of());
        when(spaceAdminRepo.existsBySpaceIdAndUserId(SPACE_ID, USER_ID))
            .thenReturn(false);

        assertThrows(BusinessException.class,
            () -> permissionService.requireSpaceAdmin(SPACE_ID, USER_ID));
    }

    // ================================================================
    // Space Owner 测试
    // ================================================================

    @Test
    void requireSpaceOwner_throwsWhenNotOwner() {
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(new User()));
        when(groupMemberRepo.findGroupIdsByUserId(USER_ID)).thenReturn(List.of());
        when(spaceAdminRepo.existsBySpaceIdAndUserIdAndRole(SPACE_ID, USER_ID, "owner"))
            .thenReturn(false);

        assertThrows(BusinessException.class,
            () -> permissionService.requireSpaceOwner(SPACE_ID, USER_ID));
    }

    // ================================================================
    // Space 成员测试
    // ================================================================

    @Test
    void isSpaceMember_adminIsMember() {
        when(spaceAdminRepo.existsBySpaceIdAndUserId(SPACE_ID, USER_ID))
            .thenReturn(true);

        assertTrue(permissionService.isSpaceMember(SPACE_ID, USER_ID));
    }

    @Test
    void isSpaceMember_viaGroup_true() {
        when(spaceAdminRepo.existsBySpaceIdAndUserId(SPACE_ID, USER_ID))
            .thenReturn(false);
        when(groupService.expandUserEffectiveGroups(USER_ID))
            .thenReturn(Set.of(GROUP_ID));
        when(spaceGroupRepo.findGroupIdsBySpaceId(SPACE_ID))
            .thenReturn(List.of(GROUP_ID));

        assertTrue(permissionService.isSpaceMember(SPACE_ID, USER_ID));
    }

    @Test
    void isSpaceMember_noAccess_false() {
        when(spaceAdminRepo.existsBySpaceIdAndUserId(SPACE_ID, USER_ID))
            .thenReturn(false);
        when(groupService.expandUserEffectiveGroups(USER_ID))
            .thenReturn(Set.of());

        assertFalse(permissionService.isSpaceMember(SPACE_ID, USER_ID));
    }

    // ================================================================
    // Space 角色测试
    // ================================================================

    @Test
    void getUserSpaceRole_globalAdmin_returnsOwner() {
        User user = new User(USER_ID, "admin", "pass", "Admin");
        user.setIsGlobalAdmin(true);
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(user));

        assertEquals("owner", permissionService.getUserSpaceRole(SPACE_ID, USER_ID));
    }

    @Test
    void getUserSpaceRole_notAMember_returnsNull() {
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(new User()));
        when(groupMemberRepo.findGroupIdsByUserId(USER_ID)).thenReturn(List.of());
        when(spaceAdminRepo.findBySpaceIdAndUserId(SPACE_ID, USER_ID))
            .thenReturn(Optional.empty());
        when(groupService.expandUserEffectiveGroups(USER_ID))
            .thenReturn(Set.of());

        assertNull(permissionService.getUserSpaceRole(SPACE_ID, USER_ID));
    }
}
