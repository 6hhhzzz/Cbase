package com.kes.auth.service;

import com.kes.auth.repository.GroupAdminRepository;
import com.kes.auth.repository.UserGroupMemberRepository;
import com.kes.auth.repository.UserGroupRepository;
import com.kes.auth.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

/**
 * GroupService 单元测试 — v9 嵌套建组（委托给 GroupHierarchyService）。
 */
@ExtendWith(MockitoExtension.class)
class GroupServiceTest {

    @Mock private UserGroupRepository groupRepo;
    @Mock private UserGroupMemberRepository memberRepo;
    @Mock private UserRepository userRepo;
    @Mock private GroupAdminRepository groupAdminRepo;
    @Mock private GroupHierarchyService hierarchyService;

    private GroupService groupService;

    @BeforeEach
    void setUp() {
        groupService = new GroupService(groupRepo, memberRepo, userRepo, groupAdminRepo, hierarchyService);
    }

    @Test
    void findOrCreateGroupPath_createsNestedGroups() {
        when(hierarchyService.findOrCreateGroupPath("公司/技术中心/后端组", "admin-1"))
            .thenReturn("g-003");

        String leafId = groupService.findOrCreateGroupPath("公司/技术中心/后端组", "admin-1");

        assertEquals("g-003", leafId);
        verify(hierarchyService).findOrCreateGroupPath("公司/技术中心/后端组", "admin-1");
    }

    @Test
    void findOrCreateGroupPath_reusesExistingGroups() {
        when(hierarchyService.findOrCreateGroupPath("公司/技术中心/后端组", "admin-1"))
            .thenReturn("g-003");

        String leafId = groupService.findOrCreateGroupPath("公司/技术中心/后端组", "admin-1");

        assertEquals("g-003", leafId);
        verify(hierarchyService).findOrCreateGroupPath("公司/技术中心/后端组", "admin-1");
    }

    @Test
    void findOrCreateGroupPath_singleLevelGroup() {
        when(hierarchyService.findOrCreateGroupPath("独立项目组", "admin-1"))
            .thenReturn("g-001");

        String leafId = groupService.findOrCreateGroupPath("独立项目组", "admin-1");

        assertEquals("g-001", leafId);
        verify(hierarchyService).findOrCreateGroupPath("独立项目组", "admin-1");
    }

    @Test
    void findOrCreateGroupPath_emptyPath_throwsException() {
        when(hierarchyService.findOrCreateGroupPath("", "admin-1"))
            .thenThrow(new RuntimeException("组路径不能为空"));
        when(hierarchyService.findOrCreateGroupPath(null, "admin-1"))
            .thenThrow(new RuntimeException("组路径不能为空"));

        assertThrows(Exception.class, () ->
            groupService.findOrCreateGroupPath("", "admin-1"));
        assertThrows(Exception.class, () ->
            groupService.findOrCreateGroupPath(null, "admin-1"));
    }
}
