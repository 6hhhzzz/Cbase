package com.kes.common.aop;

import com.kes.auth.service.PermissionService;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 管理员权限守卫 AOP 切面 — 拦截 @RequireSpaceAdmin / @RequireGlobalAdmin 注解，
 * 委托给 {@link PermissionService} 校验权限。
 *
 * <p>支持的注解：
 * <ul>
 *   <li>{@link com.kes.common.annotation.RequireSpaceAdmin} — 当前 Space 管理员</li>
 *   <li>{@link com.kes.common.annotation.RequireGlobalAdmin} — 全局管理员</li>
 * </ul>
 */
@Aspect
@Component
public class AdminGuard {

    private static final Logger log = LoggerFactory.getLogger(AdminGuard.class);

    private final PermissionService permissionService;

    public AdminGuard(PermissionService permissionService) {
        this.permissionService = permissionService;
    }

    /** 当前 Space 管理员校验（新注解，替代旧 @RequireAdmin）。 */
    @Before("@annotation(com.kes.common.annotation.RequireSpaceAdmin)")
    public void checkSpaceAdmin() {
        permissionService.requireSpaceAdmin();
    }

    /** 全局管理员校验。 */
    @Before("@annotation(com.kes.common.annotation.RequireGlobalAdmin)")
    public void checkGlobalAdmin() {
        permissionService.requireGlobalAdmin();
    }
}
