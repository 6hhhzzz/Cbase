package com.kes.common.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 标记需要全局管理员权限的方法。
 * 配合 {@link com.kes.common.aop.AdminGuard} AOP 切面使用，
 * 校验 users.is_global_admin 字段。
 *
 * <p>用法：
 * <pre>{@code
 * @GetMapping("/spaces")
 * @RequireGlobalAdmin
 * public ApiResponse<List<?>> getAllSpaces() { ... }
 * }</pre>
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RequireGlobalAdmin {
}
