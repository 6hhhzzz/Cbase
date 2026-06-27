package com.kes.auth.service;

import com.kes.auth.model.*;
import com.kes.auth.repository.*;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.util.JwtUtil;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 认证服务 — 负责用户注册、登录、令牌刷新、密码修改和 Space 切换。
 *
 * <p>v4 重构：Space/KB/ACE/全局管理/权限查询的职责已分离到独立的 Service：
 * <ul>
 *   <li>{@link SpaceService} — Space 生命周期、管理员、准入组</li>
 *   <li>{@link KbService} — KB 全生命周期管理</li>
 *   <li>{@link AceService} — ACE 矩阵管理</li>
 *   <li>{@link PermissionQueryService} — KB/文档权限查询</li>
 *   <li>{@link AdminService} — 全局管理员操作</li>
 * </ul>
 */
@Service
public class AuthService {

    private static final Logger log = LoggerFactory.getLogger(AuthService.class);

    private final UserRepository userRepo;
    private final SpaceRepository spaceRepo;
    private final KnowledgeBaseRepository kbRepo;
    private final SpaceAdminRepository spaceAdminRepo;
    private final SpaceGroupRepository spaceGroupRepo;
    private final RefreshTokenRepository refreshTokenRepo;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtil jwtUtil;
    private final PermissionService permService;
    private final GroupService groupService;

    public AuthService(UserRepository userRepo,
                       SpaceRepository spaceRepo,
                       KnowledgeBaseRepository kbRepo,
                       SpaceAdminRepository spaceAdminRepo,
                       SpaceGroupRepository spaceGroupRepo,
                       RefreshTokenRepository refreshTokenRepo,
                       PasswordEncoder passwordEncoder,
                       JwtUtil jwtUtil,
                       PermissionService permService,
                       GroupService groupService) {
        this.userRepo = userRepo;
        this.spaceRepo = spaceRepo;
        this.kbRepo = kbRepo;
        this.spaceAdminRepo = spaceAdminRepo;
        this.spaceGroupRepo = spaceGroupRepo;
        this.refreshTokenRepo = refreshTokenRepo;
        this.passwordEncoder = passwordEncoder;
        this.jwtUtil = jwtUtil;
        this.permService = permService;
        this.groupService = groupService;
    }

    // ================================================================
    // 注册 / 登录 / 刷新 / 密码修改
    // ================================================================

    /** 用户注册 — 自动创建默认 Space，创建者成为 owner */
    @Transactional
    public UserInfo register(String username, String password, String displayName) {
        if (userRepo.existsByUsername(username)) {
            throw BusinessException.usernameExists(username);
        }

        String userId = UUID.randomUUID().toString();
        User user = new User(userId, username, passwordEncoder.encode(password), displayName);
        userRepo.save(user);

        // 查找或创建默认 Space
        Space defaultSpace = spaceRepo.findAllByOrderByNameAsc().stream()
            .findFirst()
            .orElseGet(() -> {
                Space s = new Space(
                    UUID.randomUUID().toString(), "默认空间", "general",
                    "系统自动创建的默认空间", userId);
                return spaceRepo.save(s);
            });

        // 创建者自动成为 Space 的 owner
        spaceAdminRepo.save(new SpaceAdmin(defaultSpace.getId(), userId, "owner", null));

        // 新建 Space 时自动创建默认 KB
        boolean isNewSpace = defaultSpace.getCreatedBy().equals(userId);
        if (isNewSpace) {
            KnowledgeBase defaultKb = new KnowledgeBase(
                UUID.randomUUID().toString(), defaultSpace.getId(), "默认知识库",
                "系统自动创建的默认知识库", "space_wide", userId);
            kbRepo.save(defaultKb);
        }

        log.info("用户注册成功: username={}, space={}, role=owner", username, defaultSpace.getId());
        return buildUserInfo(user);
    }

    /** 用户登录 */
    @Transactional
    public TokenResponse login(String username, String password) {
        User user = userRepo.findByUsername(username)
            .orElseThrow(BusinessException::badCredentials);

        if (!passwordEncoder.matches(password, user.getPassword())) {
            throw BusinessException.badCredentials();
        }

        String refreshToken = jwtUtil.generateRefreshToken(user.getId());
        RefreshToken rt = new RefreshToken();
        rt.setUserId(user.getId());
        rt.setToken(refreshToken);
        rt.setExpiresAt(LocalDateTime.now().plusSeconds(604800));
        refreshTokenRepo.save(rt);

        UserInfo userInfo = buildUserInfo(user);
        log.info("用户登录成功: username={}", username);
        return new TokenResponse(null, refreshToken, 0, userInfo);
    }

    /** 刷新 Refresh Token */
    @Transactional
    public TokenResponse refresh(String refreshTokenStr) {
        RefreshToken rt = refreshTokenRepo.findByToken(refreshTokenStr)
            .orElseThrow(BusinessException::tokenExpired);

        if (rt.isExpired()) {
            refreshTokenRepo.delete(rt);
            throw BusinessException.tokenExpired();
        }

        User user = userRepo.findById(rt.getUserId())
            .orElseThrow(BusinessException::tokenExpired);

        UserInfo userInfo = buildUserInfo(user);
        String newRefreshToken = jwtUtil.generateRefreshToken(user.getId());

        refreshTokenRepo.delete(rt);
        RefreshToken newRt = new RefreshToken();
        newRt.setUserId(user.getId());
        newRt.setToken(newRefreshToken);
        newRt.setExpiresAt(LocalDateTime.now().plusSeconds(604800));
        refreshTokenRepo.save(newRt);

        return new TokenResponse(null, newRefreshToken, 0, userInfo);
    }

    /** 修改密码 */
    @Transactional
    public void changePassword(String userId, String oldPassword, String newPassword) {
        User user = userRepo.findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        if (!passwordEncoder.matches(oldPassword, user.getPassword())) {
            throw new BusinessException(ErrorCode.AUTH_WRONG_PASSWORD);
        }
        if (newPassword == null || newPassword.length() < 6) {
            throw new BusinessException(ErrorCode.AUTH_PASSWORD_TOO_SHORT);
        }
        user.setPassword(passwordEncoder.encode(newPassword));
        userRepo.save(user);
        log.info("密码已修改: userId={}", userId);
    }

    // ================================================================
    // Space 切换 / 列表
    // ================================================================

    /** 切换 Space — 签发 Context Token */
    public TokenResponse switchSpace(String userId, String spaceId) {
        String spaceRole = permService.getUserSpaceRole(spaceId, userId);
        if (spaceRole == null) {
            throw new BusinessException(ErrorCode.SPACE_ACCESS_DENIED, "无权访问该空间: " + spaceId);
        }

        User user = userRepo.findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

        String contextToken = jwtUtil.generateContextToken(
            userId, user.getUsername(), spaceId, spaceRole);

        log.info("切换 Space: user={}, space={}, role={}", userId, spaceId, spaceRole);
        return new TokenResponse(contextToken, null, 1800, null);
    }

    /** 获取用户所属的所有 Space */
    public List<UserInfo.SpaceInfo> getSpaces(String userId) {
        Map<String, String> spaceRoles = new LinkedHashMap<>();

        // 来源 1: space_admins（管理员身份）
        List<String> adminSpaceIds = spaceAdminRepo.findSpaceIdsByUserId(userId);
        for (String sid : adminSpaceIds) {
            SpaceAdmin sa = spaceAdminRepo.findBySpaceIdAndUserId(sid, userId).orElse(null);
            if (sa != null) {
                spaceRoles.merge(sid, sa.getRole(), (old, newRole) ->
                    "owner".equals(old) ? old : newRole);
            }
        }

        // 来源 2: space_groups（普通成员身份，通过用户组）
        Set<String> userGroups = groupService.expandUserEffectiveGroups(userId);
        for (String gid : userGroups) {
            List<SpaceGroup> sgs = spaceGroupRepo.findByGroupId(gid);
            for (SpaceGroup sg : sgs) {
                spaceRoles.putIfAbsent(sg.getSpaceId(), "member");
            }
        }

        // 来源 3: 全局管理员可以看到所有活跃 Space
        if (permService.isGlobalAdmin(userId)) {
            List<Space> allSpaces = spaceRepo.findAllActive();
            for (Space s : allSpaces) {
                spaceRoles.putIfAbsent(s.getId(), "admin");
            }
        }

        return spaceRoles.entrySet().stream()
            .map(e -> {
                Space space = spaceRepo.findById(e.getKey()).orElse(null);
                String name = space != null ? space.getName() : e.getKey();
                return new UserInfo.SpaceInfo(e.getKey(), name, e.getValue());
            })
            .toList();
    }

    // ================================================================
    // 用户搜索
    // ================================================================

    /** 按用户名前缀搜索用户（供 Controller 使用） */
    public List<Map<String, String>> searchUsers(String prefix) {
        if (prefix == null || prefix.trim().length() < 1) {
            return List.of();
        }
        return userRepo.findTop10ByUsernameStartingWith(prefix.trim())
            .stream()
            .map(u -> Map.of(
                "user_id", u.getId(),
                "username", u.getUsername(),
                "display_name", u.getDisplayName() != null ? u.getDisplayName() : ""
            ))
            .collect(Collectors.toList());
    }

    // ================================================================
    // 内部方法
    // ================================================================

    private UserInfo buildUserInfo(User user) {
        List<UserInfo.SpaceInfo> spaces = getSpaces(user.getId());
        boolean isGA = permService.isGlobalAdmin(user.getId());
        return new UserInfo(user.getId(), user.getUsername(), user.getDisplayName(), isGA, spaces);
    }
}
