package com.kes.auth.service;

import com.kes.auth.model.*;
import com.kes.auth.repository.*;
import com.kes.common.exception.BusinessException;
import com.kes.common.service.AuditLogger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/**
 * AdminService 用户管理单元测试 — v7 用户管理增强。
 * <p>用户 CRUD 测试委托给 {@link UserAdminService}，批量导入测试委托给 {@link UserImportService}。
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class AdminServiceTest {

    @Mock private UserRepository userRepo;
    @Mock private SpaceRepository spaceRepo;
    @Mock private KbPermissionCache permissionCache;
    @Mock private PermissionService permService;
    @Mock private AdminActionLogRepository auditLogRepo;
    @Mock private AuditLogger auditLogger;
    @Mock private PasswordEncoder passwordEncoder;
    @Mock private GroupService groupService;

    private UserAdminService userAdminService;
    private UserImportService userImportService;

    private static final String ADMIN_ID = "admin-001";
    private static final String USER_ID = "user-001";

    @BeforeEach
    void setUp() {
        userAdminService = new UserAdminService(
            userRepo, permissionCache, permService, auditLogger, passwordEncoder
        );
        userImportService = new UserImportService(
            userRepo, auditLogger, passwordEncoder, groupService, permService
        );
    }

    // ================================================================
    // createUser (UserAdminService)
    // ================================================================

    @Test
    void createUser_success() {
        when(userRepo.existsByUsername("newuser")).thenReturn(false);
        when(passwordEncoder.encode("password123")).thenReturn("hashed_pw");

        CreateUserRequest req = new CreateUserRequest("newuser", "新用户",
            "newuser@example.com", "password123");
        User result = userAdminService.createUser(ADMIN_ID, req);

        assertNotNull(result);
        assertEquals("newuser", result.getUsername());
        assertEquals("新用户", result.getDisplayName());
        assertEquals("newuser@example.com", result.getEmail());
        assertEquals("import", result.getSource());
        assertEquals("active", result.getStatus());
        assertFalse(result.getMustChangePassword());
        verify(userRepo).save(any(User.class));
        verify(auditLogger).log(eq(ADMIN_ID), eq("00000000-0000-0000-0000-000000000000"), eq("user.create"),
            eq("user"), anyString(), eq("newuser"), anyString());
    }

    @Test
    void createUser_autoGeneratePassword() {
        when(userRepo.existsByUsername("newuser")).thenReturn(false);
        when(passwordEncoder.encode(anyString())).thenReturn("hashed_pw");

        // 密码为空 → 自动生成
        CreateUserRequest req = new CreateUserRequest("newuser", "新用户",
            "newuser@example.com", null);
        User result = userAdminService.createUser(ADMIN_ID, req);

        assertTrue(result.getMustChangePassword());
        assertEquals("import", result.getSource());
        verify(passwordEncoder).encode(anyString());
    }

    @Test
    void createUser_duplicateUsername_throws() {
        when(userRepo.existsByUsername("duplicate")).thenReturn(true);
        CreateUserRequest req = new CreateUserRequest("duplicate", "重复用户",
            "dup@example.com", "password123");

        BusinessException ex = assertThrows(BusinessException.class,
            () -> userAdminService.createUser(ADMIN_ID, req));
        assertEquals("AUTH_USERNAME_EXISTS", ex.getErrorCode());
        assertTrue(ex.getMessage().contains("duplicate"));
    }

    @Test
    void createUser_nonAdmin_throws() {
        doThrow(new BusinessException(403, "仅全局管理员可操作"))
            .when(permService).requireGlobalAdmin("normal-user");

        CreateUserRequest req = new CreateUserRequest("newuser", "新用户",
            "newuser@example.com", "password123");
        assertThrows(BusinessException.class,
            () -> userAdminService.createUser("normal-user", req));
    }

    // ================================================================
    // updateUser (UserAdminService)
    // ================================================================

    @Test
    void updateUser_success() {
        User existing = new User(USER_ID, "olduser", "pw", "旧名");
        existing.setEmail("old@example.com");
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(existing));

        UpdateUserRequest req = new UpdateUserRequest("新名", "new@example.com", null);
        User result = userAdminService.updateUser(ADMIN_ID, USER_ID, req);

        assertEquals("新名", result.getDisplayName());
        assertEquals("new@example.com", result.getEmail());
        verify(userRepo).save(existing);
        verify(auditLogger).log(eq(ADMIN_ID), eq("00000000-0000-0000-0000-000000000000"), eq("user.update"),
            eq("user"), eq(USER_ID), anyString(), anyString());
    }

    @Test
    void updateUser_setDisabledStatus() {
        User existing = new User(USER_ID, "olduser", "pw", "旧名");
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(existing));

        UpdateUserRequest req = new UpdateUserRequest(null, null, "disabled");
        User result = userAdminService.updateUser(ADMIN_ID, USER_ID, req);

        assertEquals("disabled", result.getStatus());
        verify(permissionCache).evict(USER_ID, null);
    }

    @Test
    void updateUser_notFound_throws() {
        when(userRepo.findById("no-such")).thenReturn(Optional.empty());
        UpdateUserRequest req = new UpdateUserRequest("名", "e@e.com", null);

        BusinessException ex = assertThrows(BusinessException.class,
            () -> userAdminService.updateUser(ADMIN_ID, "no-such", req));
        assertEquals("USER_NOT_FOUND", ex.getErrorCode());
    }

    // ================================================================
    // setUserStatus (UserAdminService)
    // ================================================================

    @Test
    void setUserStatus_disable_then_enable() {
        User user = new User(USER_ID, "testuser", "pw", "测试");
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(user));

        // 禁用
        userAdminService.setUserStatus(ADMIN_ID, USER_ID, "disabled");
        assertEquals("disabled", user.getStatus());
        verify(permissionCache, times(1)).evict(USER_ID, null);

        // 启用
        userAdminService.setUserStatus(ADMIN_ID, USER_ID, "active");
        assertEquals("active", user.getStatus());
    }

    @Test
    void setUserStatus_invalidStatus_throws() {
        User user = new User(USER_ID, "testuser", "pw", "测试");
        when(userRepo.findById(USER_ID)).thenReturn(Optional.of(user));

        assertThrows(BusinessException.class,
            () -> userAdminService.setUserStatus(ADMIN_ID, USER_ID, "deleted"));
    }

    // ================================================================
    // batchImportUsers (UserImportService)
    // ================================================================

    @Test
    void batchImport_success() {
        when(userRepo.existsByUsername(anyString())).thenReturn(false);
        when(passwordEncoder.encode(anyString())).thenReturn("hashed");

        String csv = "username,display_name,email\n"
            + "alice,爱丽丝,alice@example.com\n"
            + "bob,鲍勃,bob@example.com\n";

        MockMultipartFile file = new MockMultipartFile(
            "file", "users.csv", "text/csv", csv.getBytes());

        BatchImportResult result = userImportService.batchImportUsers(ADMIN_ID, file);

        assertEquals(2, result.total());
        assertEquals(2, result.success());
        assertEquals(0, result.failed());
        assertTrue(result.errors().isEmpty());
        verify(userRepo, times(2)).save(any(User.class));
    }

    @Test
    void batchImport_partialFailure() {
        when(userRepo.existsByUsername("alice")).thenReturn(false);
        when(userRepo.existsByUsername("sh")).thenReturn(false);
        when(userRepo.existsByUsername("dup")).thenReturn(true);
        when(userRepo.existsByUsername("bad")).thenReturn(false);
        when(passwordEncoder.encode(anyString())).thenReturn("hashed");

        String csv = "username,display_name,email\n"
            + "alice,爱丽丝,alice@example.com\n"
            + ",无名,no-name@example.com\n"            // 用户名为空 → 失败
            + "sh,短,short@example.com\n"              // 用户名太短(<3) → 失败
            + "dup,重复,dup@example.com\n"              // 重复 → 失败
            + "bad,好用户,good@example.com\n";          // 成功

        MockMultipartFile file = new MockMultipartFile(
            "file", "users.csv", "text/csv", csv.getBytes());

        BatchImportResult result = userImportService.batchImportUsers(ADMIN_ID, file);

        assertEquals(5, result.total());
        assertEquals(2, result.success());
        assertEquals(3, result.failed());
        assertEquals(3, result.errors().size());
    }

    @Test
    void batchImport_emptyCsv_throws() {
        MockMultipartFile file = new MockMultipartFile(
            "file", "empty.csv", "text/csv", "".getBytes());

        assertThrows(BusinessException.class,
            () -> userImportService.batchImportUsers(ADMIN_ID, file));
    }

    @Test
    void batchImport_missingHeaders_throws() {
        String csv = "name,full_name\n张三,张三丰\n";

        MockMultipartFile file = new MockMultipartFile(
            "file", "bad.csv", "text/csv", csv.getBytes());

        BusinessException ex = assertThrows(BusinessException.class,
            () -> userImportService.batchImportUsers(ADMIN_ID, file));
        assertEquals("CSV_MISSING_COLUMN", ex.getErrorCode());
        assertTrue(ex.getMessage().contains("username"));
    }
}
