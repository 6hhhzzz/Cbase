package com.kes.auth.config;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Spring Security 配置 — 无状态 JWT 认证（proposal 2.2 / 6.1）。
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    private final JwtFilter jwtFilter;

    public SecurityConfig(JwtFilter jwtFilter) {
        this.jwtFilter = jwtFilter;
    }

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // 异步分派（SSE 流式响应期间）不再重复鉴权，避免 "response already committed" 异常
                .dispatcherTypeMatchers(DispatcherType.ASYNC).permitAll()
                // 认证接口无需鉴权
                .requestMatchers("/api/auth/**").permitAll()
                // 文件下载/预览接口在控制器内部手动验证 JWT（兼容 window.open 无 Authorization header）
                .requestMatchers(request -> "GET".equals(request.getMethod())
                    && request.getRequestURI().matches(".*/api/documents/[^/]+/file")
                ).permitAll()
                // 其余 /api/** 需认证
                .requestMatchers("/api/**").authenticated()
                // 健康检查等放行
                .anyRequest().permitAll()
            )
            .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
