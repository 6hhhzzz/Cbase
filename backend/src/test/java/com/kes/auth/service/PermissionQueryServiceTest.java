package com.kes.auth.service;

import com.kes.auth.model.AccessControlEntry;
import com.kes.auth.model.KnowledgeBase;
import com.kes.auth.repository.AceRepository;
import com.kes.auth.repository.KnowledgeBaseRepository;
import com.kes.document.service.DocumentPermissionService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * PermissionQueryService 单元测试 — v4 ACE 权限解析核心算法。
 *
 * 测试 resolveAccessibleKbIds 的各种场景：
 *   全局管理员 → 全量 | Space admin → 全量
 *   普通成员 → space_wide + ACE allow | deny 覆盖 allow
 *   缓存命中/未命中 | requiredPermission 过滤
 */
@ExtendWith(MockitoExtension.class)
class PermissionQueryServiceTest {

    @Mock private KnowledgeBaseRepository kbRepo;
    @Mock private AceRepository aceRepo;
    @Mock private KbPermissionCache permissionCache;
    @Mock private PermissionService permService;
    @Mock private DocumentPermissionService docPermissionService;

    private PermissionQueryService queryService;

    private static final String USER_ID = "user-001";
    private static final String SPACE_ID = "space-001";
    private static final String KB_SPACEWIDE = "kb-spacewide-001";
    private static final String KB_RESTRICTED = "kb-restricted-001";

    @BeforeEach
    void setUp() {
        queryService = new PermissionQueryService(
            kbRepo, aceRepo, permissionCache, permService, docPermissionService);
    }

    // ================================================================
    // 全局管理员
    // ================================================================

    @Test
    void globalAdmin_returnsAllKbs() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(true);
        when(kbRepo.findBySpaceIdAndDeletedAtIsNull(SPACE_ID))
            .thenReturn(List.of(
                kb(KB_SPACEWIDE), kb(KB_RESTRICTED)));

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID);

        assertEquals(2, result.size());
        assertTrue(result.contains(KB_SPACEWIDE));
        assertTrue(result.contains(KB_RESTRICTED));
        verify(permissionCache).put(eq(USER_ID), eq(SPACE_ID), any());
    }

    // ================================================================
    // Space 管理员
    // ================================================================

    @Test
    void spaceAdmin_returnsAllKbs() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(false);
        when(permService.getUserSpaceGroups(SPACE_ID, USER_ID)).thenReturn(Set.of("group-001"));
        when(permService.isSpaceAdmin(SPACE_ID, USER_ID)).thenReturn(true);
        when(kbRepo.findBySpaceIdAndDeletedAtIsNull(SPACE_ID))
            .thenReturn(List.of(kb(KB_SPACEWIDE), kb(KB_RESTRICTED)));

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID);

        assertEquals(2, result.size());
    }

    // ================================================================
    // 非 Space 成员
    // ================================================================

    @Test
    void nonMember_returnsEmpty() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(false);
        when(permService.getUserSpaceGroups(SPACE_ID, USER_ID)).thenReturn(Set.of());
        when(permService.isSpaceAdmin(SPACE_ID, USER_ID)).thenReturn(false);

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID);

        assertTrue(result.isEmpty());
    }

    // ================================================================
    // 普通成员 — space_wide KB
    // ================================================================

    @Test
    void member_canAccessSpaceWideKbs() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(false);
        when(permService.getUserSpaceGroups(SPACE_ID, USER_ID)).thenReturn(Set.of("group-001"));
        when(permService.isSpaceAdmin(SPACE_ID, USER_ID)).thenReturn(false);
        when(kbRepo.findSpaceWideKbIds(SPACE_ID)).thenReturn(List.of(KB_SPACEWIDE));
        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("group"), anyList()))
            .thenReturn(List.of());
        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("user"), anyList()))
            .thenReturn(List.of());

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID);

        assertEquals(1, result.size());
        assertTrue(result.contains(KB_SPACEWIDE));
    }

    // ================================================================
    // ACE allow — 成员通过 ACE 获得 restricted KB 访问权
    // ================================================================

    @Test
    void member_withAceAllow_canAccessRestrictedKb() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(false);
        when(permService.getUserSpaceGroups(SPACE_ID, USER_ID)).thenReturn(Set.of("group-001"));
        when(permService.isSpaceAdmin(SPACE_ID, USER_ID)).thenReturn(false);
        when(kbRepo.findSpaceWideKbIds(SPACE_ID)).thenReturn(List.of(KB_SPACEWIDE));

        // ACE allow: group-001 → KB_RESTRICTED
        AccessControlEntry allowAce = new AccessControlEntry(
            "ace-001", SPACE_ID, "kb", KB_RESTRICTED, "group", "group-001", "role-001", "allow", 0);
        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("group"), anyList()))
            .thenReturn(List.of(allowAce));
        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("user"), anyList()))
            .thenReturn(List.of());

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID);

        assertTrue(result.contains(KB_RESTRICTED));
        assertTrue(result.contains(KB_SPACEWIDE));
    }

    // ================================================================
    // ACE deny 覆盖 allow
    // ================================================================

    @Test
    void deny_overridesAllow() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(false);
        when(permService.getUserSpaceGroups(SPACE_ID, USER_ID)).thenReturn(Set.of("group-001"));
        when(permService.isSpaceAdmin(SPACE_ID, USER_ID)).thenReturn(false);
        when(kbRepo.findSpaceWideKbIds(SPACE_ID)).thenReturn(List.of());

        // ACE allow: group → KB_RESTRICTED
        AccessControlEntry allowAce = new AccessControlEntry(
            "ace-001", SPACE_ID, "kb", KB_RESTRICTED, "group", "group-001", "role-001", "allow", 0);
        // ACE deny: user → KB_RESTRICTED (deny 覆盖 allow)
        AccessControlEntry denyAce = new AccessControlEntry(
            "ace-002", SPACE_ID, "kb", KB_RESTRICTED, "user", USER_ID, "role-002", "deny", 10);

        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("group"), anyList()))
            .thenReturn(List.of(allowAce));
        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("user"), anyList()))
            .thenReturn(List.of(denyAce));

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID);

        assertFalse(result.contains(KB_RESTRICTED), "deny 应覆盖 allow，KB_RESTRICTED 应被排除");
    }

    // ================================================================
    // 缓存
    // ================================================================

    @Test
    void cacheHit_returnsCachedResult() {
        Set<String> cached = new LinkedHashSet<>(List.of(KB_SPACEWIDE));
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(cached);

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID);

        assertEquals(1, result.size());
        assertTrue(result.contains(KB_SPACEWIDE));
        verify(permService, never()).isGlobalAdmin(anyString());
    }

    // ================================================================
    // requiredPermission 过滤
    // ================================================================

    @Test
    void requiredPermission_filtersKbs() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(false);
        when(permService.getUserSpaceGroups(SPACE_ID, USER_ID)).thenReturn(Set.of("group-001"));
        when(permService.isSpaceAdmin(SPACE_ID, USER_ID)).thenReturn(false);
        when(kbRepo.findSpaceWideKbIds(SPACE_ID)).thenReturn(List.of(KB_SPACEWIDE));
        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("group"), anyList()))
            .thenReturn(List.of());
        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("user"), anyList()))
            .thenReturn(List.of());

        // 用户没有 "kb.write" 权限 → KB 被过滤
        when(permService.hasPermission(USER_ID, SPACE_ID, KB_SPACEWIDE, "kb.write"))
            .thenReturn(false);

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID, "kb.write");

        assertFalse(result.contains(KB_SPACEWIDE));
    }

    @Test
    void spaceAdmin_bypassesPermissionFilter() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(false);
        when(permService.getUserSpaceGroups(SPACE_ID, USER_ID)).thenReturn(Set.of("group-001"));
        when(permService.isSpaceAdmin(SPACE_ID, USER_ID)).thenReturn(true);
        when(kbRepo.findBySpaceIdAndDeletedAtIsNull(SPACE_ID))
            .thenReturn(List.of(kb(KB_SPACEWIDE), kb(KB_RESTRICTED)));

        // Space admin 绕过 requiredPermission 检查
        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID, "kb.write");

        assertEquals(2, result.size());
        verify(permService, never()).hasPermission(anyString(), anyString(), anyString(), anyString());
    }

    // ================================================================
    // applyAceEntries 逻辑 (via resolveAccessibleKbIds)
    // ================================================================

    @Test
    void aceEntries_correctlyApplied() {
        when(permissionCache.get(USER_ID, SPACE_ID)).thenReturn(null);
        when(permService.isGlobalAdmin(USER_ID)).thenReturn(false);
        when(permService.getUserSpaceGroups(SPACE_ID, USER_ID)).thenReturn(Set.of("group-001"));
        when(permService.isSpaceAdmin(SPACE_ID, USER_ID)).thenReturn(false);
        // 无 space_wide KB
        when(kbRepo.findSpaceWideKbIds(SPACE_ID)).thenReturn(List.of());

        // 两个 ACE allow，一个 deny
        AccessControlEntry allowKb1 = new AccessControlEntry(
            "ace-1", SPACE_ID, "kb", "kb-001", "group", "group-001", "r-1", "allow", 0);
        AccessControlEntry allowKb2 = new AccessControlEntry(
            "ace-2", SPACE_ID, "kb", "kb-002", "group", "group-001", "r-1", "allow", 0);
        AccessControlEntry denyKb1 = new AccessControlEntry(
            "ace-3", SPACE_ID, "kb", "kb-001", "group", "group-001", "r-2", "deny", 10);

        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("group"), anyList()))
            .thenReturn(List.of(allowKb1, allowKb2, denyKb1));
        when(aceRepo.findKbAcesByPrincipals(eq(SPACE_ID), eq("user"), anyList()))
            .thenReturn(List.of());

        List<String> result = queryService.resolveAccessibleKbIds(SPACE_ID, USER_ID);

        // kb-001 被 deny 覆盖
        assertFalse(result.contains("kb-001"));
        // kb-002 仅 allow
        assertTrue(result.contains("kb-002"));
    }

    // ---- helpers ----

    private KnowledgeBase kb(String id) {
        KnowledgeBase kb = new KnowledgeBase();
        kb.setId(id);
        kb.setName("KB " + id);
        kb.setSpaceId(SPACE_ID);
        return kb;
    }
}
