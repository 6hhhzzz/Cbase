package com.kes.auth.config;

import com.kes.common.util.JwtUtil;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/**
 * JWT 认证过滤器 — v3 双 Token 机制。
 *
 * <p>支持两种 Token:
 * <ul>
 *   <li>Refresh Token — 用于 /api/auth/spaces 和 /api/auth/switch-space</li>
 *   <li>Context Token — 用于所有业务 API（含 space_id、role）</li>
 * </ul>
 */
@Component
public class JwtFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(JwtFilter.class);

    private final JwtUtil jwtUtil;

    public JwtFilter(JwtUtil jwtUtil) {
        this.jwtUtil = jwtUtil;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                     HttpServletResponse response,
                                     FilterChain chain) throws ServletException, IOException {
        String authHeader = request.getHeader("Authorization");
        String token = jwtUtil.extractBearerToken(authHeader);

        if (token != null && jwtUtil.isTokenValid(token)) {
            String userId = jwtUtil.extractUserId(token);

            List<SimpleGrantedAuthority> authorities = new ArrayList<>();
            try {
                if (jwtUtil.isContextToken(token)) {
                    String role = jwtUtil.extractContextRole(token);
                    if (role != null) {
                        authorities.add(new SimpleGrantedAuthority("ROLE_" + role.toUpperCase()));
                    }
                }
            } catch (Exception e) {
                log.debug("JWT role 提取失败: {}", e.getMessage());
            }

            UsernamePasswordAuthenticationToken auth =
                new UsernamePasswordAuthenticationToken(userId, token, authorities);
            SecurityContextHolder.getContext().setAuthentication(auth);
        } else if (token != null) {
            // Token 存在但无效（过期/篡改）→ 直接返回 401
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"code\":401,\"message\":\"Token 已过期或无效，请重新登录\"}");
            return;
        }

        chain.doFilter(request, response);
    }
}
