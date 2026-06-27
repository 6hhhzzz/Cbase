package com.kes.auth.controller;

import com.kes.auth.model.*;
import com.kes.auth.service.AuthService;
import com.kes.auth.service.PermissionQueryService;
import com.kes.common.dto.SpaceDtos.KbAccessInfo;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.model.ApiResponse;
import com.kes.common.util.ControllerAuthHelper;
import com.kes.common.util.JwtUtil;
import jakarta.validation.Valid;
import java.util.*;
import org.springframework.web.bind.annotation.*;

/**
 * 认证控制器 — v4 Space/KB RBAC。
 *
 * <p>DDD 分层合规：Controller 仅负责参数接收和结果返回，
 * 所有 Repository 访问均委托给 Service 层。
 */
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;
    private final PermissionQueryService permissionQueryService;
    private final JwtUtil jwtUtil;
    private final ControllerAuthHelper authHelper;

    public AuthController(AuthService authService,
                          PermissionQueryService permissionQueryService,
                          JwtUtil jwtUtil,
                          ControllerAuthHelper authHelper) {
        this.authService = authService;
        this.permissionQueryService = permissionQueryService;
        this.jwtUtil = jwtUtil;
        this.authHelper = authHelper;
    }

    /** 用户注册 */
    @PostMapping("/register")
    public ApiResponse<UserInfo> register(@Valid @RequestBody RegisterRequest req) {
        UserInfo user = authService.register(
            req.username(), req.password(), req.displayName()
        );
        return ApiResponse.success(user);
    }

    /** 用户登录 — 返回 Refresh Token */
    @PostMapping("/login")
    public ApiResponse<TokenResponse> login(@Valid @RequestBody LoginRequest req) {
        TokenResponse token = authService.login(req.username(), req.password());
        return ApiResponse.success(token);
    }

    /** 刷新 Refresh Token */
    @PostMapping("/refresh")
    public ApiResponse<TokenResponse> refresh(@RequestBody Map<String, String> body) {
        String refreshToken = body.get("refresh_token");
        if (refreshToken == null || refreshToken.isBlank()) {
            throw new BusinessException(ErrorCode.PARAM_MISSING, "refresh_token 为必填项");
        }
        TokenResponse token = authService.refresh(refreshToken);
        return ApiResponse.success(token);
    }

    /** 获取用户的所有 Space 列表 */
    @GetMapping("/spaces")
    public ApiResponse<List<UserInfo.SpaceInfo>> getSpaces(
            @RequestHeader(value = "Authorization", required = false) String authHeader) {
        String userId = extractUserIdOrNull(authHeader);
        if (userId == null) {
            throw new BusinessException(ErrorCode.AUTH_NOT_LOGGED_IN);
        }
        List<UserInfo.SpaceInfo> spaces = authService.getSpaces(userId);
        return ApiResponse.success(spaces);
    }

    /** 切换 Space — 签发 Context Token */
    @PostMapping("/switch-space")
    public ApiResponse<TokenResponse> switchSpace(
            @RequestHeader(value = "Authorization", required = false) String authHeader,
            @RequestBody Map<String, String> body) {
        String token = jwtUtil.extractBearerToken(authHeader);
        if (token == null || !jwtUtil.isTokenValid(token)) {
            throw new BusinessException(ErrorCode.AUTH_NOT_LOGGED_IN);
        }

        String spaceId = body.get("space_id");
        if (spaceId == null) {
            throw new BusinessException(ErrorCode.PARAM_MISSING, "space_id 为必填项");
        }

        String userId = jwtUtil.extractUserId(token);
        TokenResponse ctxToken = authService.switchSpace(userId, spaceId);
        return ApiResponse.success(ctxToken);
    }

    /** 获取当前 Space 下用户有权限的所有 KB（含名称和 visibility） */
    @GetMapping("/accessible-kbs")
    public ApiResponse<List<KbAccessInfo>> getAccessibleKBs(
            @RequestHeader(value = "Authorization", required = false) String authHeader) {
        String token = jwtUtil.extractBearerToken(authHeader);
        if (token == null || !jwtUtil.isTokenValid(token))
            throw new BusinessException(ErrorCode.AUTH_NOT_LOGGED_IN);

        String userId = jwtUtil.extractUserId(token);
        String spaceId = jwtUtil.extractSpaceId(token);

        List<KbAccessInfo> result = permissionQueryService.resolveAccessibleKbInfoList(spaceId, userId);
        return ApiResponse.success(result);
    }

    /** 按用户名前缀搜索用户 */
    @GetMapping("/users/search")
    public ApiResponse<List<Map<String, String>>> searchUsers(
            @RequestHeader("Authorization") String authHeader,
            @RequestParam("q") String query) {
        String token = jwtUtil.extractBearerToken(authHeader);
        if (token == null || !jwtUtil.isTokenValid(token)) {
            throw new BusinessException(ErrorCode.AUTH_NOT_LOGGED_IN);
        }

        String prefix = query != null ? query.trim() : "";
        return ApiResponse.success(authService.searchUsers(prefix));
    }

    /** 修改密码 */
    @PutMapping("/password")
    public ApiResponse<?> changePassword(
            @RequestHeader("Authorization") String authHeader,
            @RequestBody Map<String, String> body) {
        String userId = extractUserIdOrNull(authHeader);
        if (userId == null) {
            throw new BusinessException(ErrorCode.AUTH_NOT_LOGGED_IN);
        }
        authService.changePassword(userId,
            body.get("old_password"), body.get("new_password"));
        return ApiResponse.success();
    }

    private String extractUserIdOrNull(String authHeader) {
        try {
            return authHelper.extractUserId(authHeader);
        } catch (BusinessException e) {
            return null;
        }
    }
}
