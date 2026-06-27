package com.kes.auth.service;

import com.kes.auth.model.CreateUserRequest;
import com.kes.auth.model.UpdateUserRequest;
import com.kes.auth.model.User;
import com.kes.auth.repository.UserRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.service.AuditLogger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.util.List;
import java.util.UUID;

/**
 * 用户管理服务（全局管理员）。
 * 处理用户 CRUD、全局管理员设置、启用/禁用等操作。
 *
 * <p>从 {@link AdminService} 拆分而来，仅限全局超级管理员调用。
 *
 * <p>依赖：{@link PermissionService}（权限校验）、{@link AuditLogger}（操作记录）
 */
@Service
public class UserAdminService {

    private static final Logger log = LoggerFactory.getLogger(UserAdminService.class);
    private static final String GLOBAL = "00000000-0000-0000-0000-000000000000";

    private final UserRepository userRepo;
    private final KbPermissionCache permissionCache;
    private final PermissionService permService;
    private final AuditLogger auditLogger;
    private final PasswordEncoder passwordEncoder;

    public UserAdminService(UserRepository userRepo,
                            KbPermissionCache permissionCache,
                            PermissionService permService,
                            AuditLogger auditLogger,
                            PasswordEncoder passwordEncoder) {
        this.userRepo = userRepo;
        this.permissionCache = permissionCache;
        this.permService = permService;
        this.auditLogger = auditLogger;
        this.passwordEncoder = passwordEncoder;
    }

    /** 列出所有用户 */
    public List<User> listAllUsers(String operatorId) {
        permService.requireGlobalAdmin(operatorId);
        return userRepo.findAll();
    }

    /** 设置/取消全局管理员 */
    @Transactional
    public void setGlobalAdmin(String operatorId, String userId, boolean isGlobalAdmin) {
        permService.requireGlobalAdmin(operatorId);
        User user = userRepo.findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        user.setIsGlobalAdmin(isGlobalAdmin);
        userRepo.save(user);
        permissionCache.evict(userId, null);
        log.info("全局管理员 {}: operator={}, user={}", isGlobalAdmin ? "设置" : "取消", operatorId, userId);
    }

    /** 管理员创建单个用户 */
    @Transactional
    public User createUser(String operatorId, CreateUserRequest req) {
        permService.requireGlobalAdmin(operatorId);

        if (userRepo.existsByUsername(req.username())) {
            throw new BusinessException(ErrorCode.AUTH_USERNAME_EXISTS, "用户名已存在: " + req.username());
        }

        String userId = UUID.randomUUID().toString();
        String rawPassword = req.password() != null && !req.password().isBlank()
            ? req.password() : generateRandomPassword();

        User user = new User(userId, req.username(),
            passwordEncoder.encode(rawPassword), req.displayName());
        user.setEmail(req.email());
        user.setSource("import");
        user.setMustChangePassword(req.password() == null || req.password().isBlank());

        userRepo.save(user);
        auditLogger.log(operatorId, GLOBAL, "user.create", "user", userId,
            req.username(), "{\"source\":\"import\"}");
        log.info("管理员创建用户: operator={}, username={}", operatorId, req.username());
        return user;
    }

    /** 管理员编辑用户信息 */
    @Transactional
    public User updateUser(String operatorId, String userId, UpdateUserRequest req) {
        permService.requireGlobalAdmin(operatorId);
        User user = userRepo.findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

        if (req.displayName() != null) user.setDisplayName(req.displayName());
        if (req.email() != null) user.setEmail(req.email());
        if (req.status() != null) {
            if (!List.of("active", "disabled").contains(req.status())) {
                throw new BusinessException(ErrorCode.PARAM_INVALID, "无效状态: " + req.status());
            }
            user.setStatus(req.status());
            if ("disabled".equals(req.status())) {
                permissionCache.evict(userId, null);
            }
        }

        userRepo.save(user);
        auditLogger.log(operatorId, GLOBAL, "user.update", "user", userId,
            user.getUsername(), "{}");
        log.info("管理员编辑用户: operator={}, userId={}", operatorId, userId);
        return user;
    }

    /** 启用/禁用用户 */
    @Transactional
    public void setUserStatus(String operatorId, String userId, String status) {
        permService.requireGlobalAdmin(operatorId);
        if (!List.of("active", "disabled").contains(status)) {
            throw new BusinessException(ErrorCode.PARAM_INVALID, "无效状态: " + status);
        }

        User user = userRepo.findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        user.setStatus(status);
        userRepo.save(user);

        if ("disabled".equals(status)) {
            permissionCache.evict(userId, null);
        }

        auditLogger.log(operatorId, GLOBAL,
            "disabled".equals(status) ? "user.disable" : "user.enable",
            "user", userId, user.getUsername(), "{}");
        log.info("管理员{}用户: operator={}, userId={}",
            "disabled".equals(status) ? "禁用" : "启用", operatorId, userId);
    }

    // ================================================================
    // 私有辅助
    // ================================================================

    private static final SecureRandom RNG = new SecureRandom();
    private static final String PASSWORD_CHARS =
        "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789@#$%";

    private String generateRandomPassword() {
        StringBuilder sb = new StringBuilder(16);
        for (int i = 0; i < 16; i++) {
            sb.append(PASSWORD_CHARS.charAt(RNG.nextInt(PASSWORD_CHARS.length())));
        }
        return sb.toString();
    }
}
