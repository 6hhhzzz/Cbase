package com.kes.auth.service;

import com.kes.auth.model.AccessControlEntry;
import com.kes.auth.repository.AceRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.service.AuditLogger;
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
 * AceService 单元测试 — ACE 矩阵 CRUD 操作。
 */
@ExtendWith(MockitoExtension.class)
class AceServiceTest {

    @Mock private AceRepository aceRepo;
    @Mock private KbPermissionCache permissionCache;
    @Mock private PermissionService permService;
    @Mock private AuditLogger auditLogger;

    private AceService aceService;

    private static final String OPERATOR = "user-001";
    private static final String SPACE_ID = "space-001";
    private static final String ACE_ID = "ace-001";

    @BeforeEach
    void setUp() {
        aceService = new AceService(aceRepo, permissionCache, permService, auditLogger);
    }

    // ================================================================
    // getAces
    // ================================================================

    @Test
    void getAces_defaultResourceTypeKb() {
        when(aceRepo.findBySpaceIdAndResourceType(SPACE_ID, "kb")).thenReturn(List.of());

        List<AccessControlEntry> result = aceService.getAces(SPACE_ID, null);
        assertEquals(0, result.size());
        verify(aceRepo).findBySpaceIdAndResourceType(SPACE_ID, "kb");
    }

    @Test
    void getAces_specificResourceType() {
        when(aceRepo.findBySpaceIdAndResourceType(SPACE_ID, "document")).thenReturn(List.of());

        List<AccessControlEntry> result = aceService.getAces(SPACE_ID, "document");
        assertEquals(0, result.size());
    }

    // ================================================================
    // createAce
    // ================================================================

    @Test
    void createAce_success() {
        doNothing().when(permService).requireSpaceAdmin(SPACE_ID, OPERATOR);
        when(aceRepo.existsBySpaceIdAndResourceTypeAndResourceIdAndPrincipalTypeAndPrincipalId(
            anyString(), anyString(), anyString(), anyString(), anyString())).thenReturn(false);
        when(aceRepo.save(any())).thenAnswer(inv -> inv.getArgument(0));

        AccessControlEntry result = aceService.createAce(
            OPERATOR, SPACE_ID, "kb", "kb-001", "group", "group-001", "role-001", "allow", 0);

        assertNotNull(result);
        assertEquals("kb", result.getResourceType());
        assertEquals("allow", result.getEffect());
        verify(permissionCache).evictBySpace(SPACE_ID);
    }

    @Test
    void createAce_defaultEffectAllow() {
        doNothing().when(permService).requireSpaceAdmin(SPACE_ID, OPERATOR);
        when(aceRepo.existsBySpaceIdAndResourceTypeAndResourceIdAndPrincipalTypeAndPrincipalId(
            anyString(), anyString(), anyString(), anyString(), anyString())).thenReturn(false);
        when(aceRepo.save(any())).thenAnswer(inv -> inv.getArgument(0));

        AccessControlEntry result = aceService.createAce(
            OPERATOR, SPACE_ID, "kb", "kb-001", "user", "user-002", "role-001", null, 0);

        assertEquals("allow", result.getEffect());
    }

    @Test
    void createAce_duplicateThrowsException() {
        doNothing().when(permService).requireSpaceAdmin(SPACE_ID, OPERATOR);
        when(aceRepo.existsBySpaceIdAndResourceTypeAndResourceIdAndPrincipalTypeAndPrincipalId(
            anyString(), anyString(), anyString(), anyString(), anyString())).thenReturn(true);

        BusinessException ex = assertThrows(BusinessException.class, () ->
            aceService.createAce(OPERATOR, SPACE_ID, "kb", "kb-001", "group", "group-001",
                "role-001", "allow", 0));
        assertEquals(ErrorCode.ACE_ALREADY_EXISTS.name(), ex.getErrorCode());
    }

    @Test
    void createAce_nonAdminThrowsException() {
        doThrow(new BusinessException(ErrorCode.SPACE_ADMIN_REQUIRED))
            .when(permService).requireSpaceAdmin(SPACE_ID, OPERATOR);

        assertThrows(BusinessException.class, () ->
            aceService.createAce(OPERATOR, SPACE_ID, "kb", "kb-001", "group", "group-001",
                "role-001", "allow", 0));
    }

    // ================================================================
    // updateAce
    // ================================================================

    @Test
    void updateAce_success() {
        doNothing().when(permService).requireSpaceAdmin(SPACE_ID, OPERATOR);
        AccessControlEntry existing = new AccessControlEntry(
            ACE_ID, SPACE_ID, "kb", "kb-001", "group", "group-001", "role-001", "allow", 0);
        when(aceRepo.findById(ACE_ID)).thenReturn(Optional.of(existing));
        when(aceRepo.save(any())).thenReturn(existing);

        AccessControlEntry result = aceService.updateAce(
            OPERATOR, SPACE_ID, ACE_ID, "role-002", "deny", 10);

        assertEquals("deny", result.getEffect());
        assertEquals(10, result.getPriority());
        verify(permissionCache).evictBySpace(SPACE_ID);
    }

    @Test
    void updateAce_partialUpdate() {
        doNothing().when(permService).requireSpaceAdmin(SPACE_ID, OPERATOR);
        AccessControlEntry existing = new AccessControlEntry(
            ACE_ID, SPACE_ID, "kb", "kb-001", "group", "group-001", "role-001", "allow", 0);
        when(aceRepo.findById(ACE_ID)).thenReturn(Optional.of(existing));
        when(aceRepo.save(any())).thenReturn(existing);

        // 只更新 effect，不更新 roleId 和 priority
        AccessControlEntry result = aceService.updateAce(OPERATOR, SPACE_ID, ACE_ID, null, "deny", null);

        assertEquals("deny", result.getEffect());
        assertEquals("role-001", result.getRoleId()); // 未变
    }

    @Test
    void updateAce_notFoundThrowsException() {
        doNothing().when(permService).requireSpaceAdmin(SPACE_ID, OPERATOR);
        when(aceRepo.findById("nonexistent")).thenReturn(Optional.empty());

        BusinessException ex = assertThrows(BusinessException.class, () ->
            aceService.updateAce(OPERATOR, SPACE_ID, "nonexistent", null, null, null));
        assertEquals(ErrorCode.ACE_NOT_FOUND.name(), ex.getErrorCode());
    }

    // ================================================================
    // deleteAce
    // ================================================================

    @Test
    void deleteAce_success() {
        doNothing().when(permService).requireSpaceAdmin(SPACE_ID, OPERATOR);
        doNothing().when(aceRepo).deleteById(ACE_ID);

        assertDoesNotThrow(() -> aceService.deleteAce(OPERATOR, SPACE_ID, ACE_ID));
        verify(permissionCache).evictBySpace(SPACE_ID);
    }
}
