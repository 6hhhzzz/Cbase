package com.kes.auth.service;

import com.kes.auth.model.*;
import com.kes.auth.repository.*;
import com.kes.common.exception.BusinessException;
import com.kes.common.util.JwtUtil;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;

/**
 * AuthService 单元测试 — 认证核心流程。
 */
@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class AuthServiceTest {

    @Mock private UserRepository userRepo;
    @Mock private SpaceRepository spaceRepo;
    @Mock private KnowledgeBaseRepository kbRepo;
    @Mock private SpaceAdminRepository spaceAdminRepo;
    @Mock private SpaceGroupRepository spaceGroupRepo;
    @Mock private RefreshTokenRepository refreshTokenRepo;
    @Mock private PasswordEncoder passwordEncoder;
    @Mock private JwtUtil jwtUtil;
    @Mock private PermissionService permService;
    @Mock private GroupService groupService;

    private AuthService authService;

    @BeforeEach
    void setUp() {
        authService = new AuthService(
            userRepo, spaceRepo, kbRepo, spaceAdminRepo, spaceGroupRepo,
            refreshTokenRepo, passwordEncoder, jwtUtil,
            permService, groupService
        );
    }

    // ================================================================
    // 注册测试
    // ================================================================

    @Test
    void register_newUser_success() {
        when(userRepo.existsByUsername("newuser")).thenReturn(false);
        when(passwordEncoder.encode("password")).thenReturn("hashed");
        Space defaultSpace = new Space("space-1", "默认空间", "general", "desc", "newuser");
        when(spaceRepo.findAllByOrderByNameAsc()).thenReturn(List.of(defaultSpace));
        // 设置群组展开返回值，避免 NPE
        when(groupService.expandUserEffectiveGroups(anyString())).thenReturn(Set.of());
        when(permService.isGlobalAdmin(anyString())).thenReturn(false);
        when(spaceAdminRepo.findSpaceIdsByUserId(anyString())).thenReturn(List.of());
        when(spaceRepo.findById(anyString())).thenReturn(Optional.of(defaultSpace));

        UserInfo result = authService.register("newuser", "password", "新用户");
        assertNotNull(result);
        assertEquals("newuser", result.username());
    }

    @Test
    void register_existingUser_throws() {
        when(userRepo.existsByUsername("existing")).thenReturn(true);

        assertThrows(BusinessException.class,
            () -> authService.register("existing", "pass", "dup"));
    }

    // ================================================================
    // 登录测试
    // ================================================================

    @Test
    void login_validCredentials_returnsToken() {
        User user = new User("user-1", "testuser", "hashed", "Test");
        when(userRepo.findByUsername("testuser")).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("password", "hashed")).thenReturn(true);
        when(jwtUtil.generateRefreshToken("user-1")).thenReturn("refresh-token-xxx");
        when(groupService.expandUserEffectiveGroups("user-1")).thenReturn(Set.of());
        when(permService.isGlobalAdmin("user-1")).thenReturn(false);
        when(spaceAdminRepo.findSpaceIdsByUserId("user-1")).thenReturn(List.of());
        when(spaceRepo.findById(anyString())).thenReturn(Optional.empty());

        TokenResponse result = authService.login("testuser", "password");
        assertNotNull(result);
        assertEquals("refresh-token-xxx", result.refreshToken());
    }

    @Test
    void login_badPassword_throws() {
        User user = new User("user-1", "testuser", "hashed", "Test");
        when(userRepo.findByUsername("testuser")).thenReturn(Optional.of(user));
        when(passwordEncoder.matches("wrong", "hashed")).thenReturn(false);

        assertThrows(BusinessException.class,
            () -> authService.login("testuser", "wrong"));
    }

    // ================================================================
    // 切换 Space 测试
    // ================================================================

    @Test
    void switchSpace_validMember_returnsContextToken() {
        when(permService.getUserSpaceRole("space-1", "user-1")).thenReturn("admin");
        User user = new User("user-1", "testuser", "hashed", "Test");
        when(userRepo.findById("user-1")).thenReturn(Optional.of(user));
        when(jwtUtil.generateContextToken("user-1", "testuser", "space-1", "admin"))
            .thenReturn("context-token-xxx");

        TokenResponse result = authService.switchSpace("user-1", "space-1");
        assertNotNull(result);
        assertEquals("context-token-xxx", result.accessToken());
    }

    @Test
    void switchSpace_notMember_throws() {
        when(permService.getUserSpaceRole("space-1", "user-1")).thenReturn(null);

        assertThrows(BusinessException.class,
            () -> authService.switchSpace("user-1", "space-1"));
    }
}
