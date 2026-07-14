package com.kes.common.util;

import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

/**
 * Controller 层共享鉴权工具 — 从 JWT / SecurityContext 提取 userId 和 spaceId。
 *
 * <p>消除 Auth / Space / Admin / ApiKey / Group 等 Controller 中重复的 extractUserId 和 extractSpaceId 方法。</p>
 */
@Component
public class ControllerAuthHelper {

    private static final Logger log = LoggerFactory.getLogger(ControllerAuthHelper.class);

    private final JwtUtil jwtUtil;

    public ControllerAuthHelper(JwtUtil jwtUtil) {
        this.jwtUtil = jwtUtil;
    }

    /** 从 SecurityContext 或 Auth Header 中提取 userId。 */
    public String extractUserId(String authHeader) {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof String userId) {
            log.warn("[DIAG] extractUserId via SecurityContext principal={} authClass={}",
                userId, auth.getClass().getSimpleName());
            return userId;
        }
        String token = jwtUtil.extractBearerToken(authHeader);
        if (token != null && jwtUtil.isTokenValid(token)) {
            String uid = jwtUtil.extractUserId(token);
            log.warn("[DIAG] extractUserId via token uid={} (auth={})", uid, auth);
            return uid;
        }
        log.warn("[DIAG] extractUserId NO AUTH (auth={}, token={})", auth, token != null);
        throw new BusinessException(ErrorCode.AUTH_NOT_LOGGED_IN);
    }

    /** 从 SecurityContext 或 Auth Header 中提取 spaceId。 */
    public String extractSpaceId(String authHeader) {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof String) {
            Object spaceIdObj = auth.getDetails();
            if (spaceIdObj instanceof String sid) return sid;
        }
        String token = jwtUtil.extractBearerToken(authHeader);
        if (token != null && jwtUtil.isTokenValid(token)) {
            return jwtUtil.extractSpaceId(token);
        }
        throw new BusinessException(ErrorCode.AUTH_NOT_LOGGED_IN);
    }
}
