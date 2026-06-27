package com.kes.common.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 标记需要当前 Space 管理员权限的方法。
 * 配合 {@link com.kes.common.aop.AdminGuard} AOP 切面使用，
 * 从 SecurityContext 中的 Context Token 提取 spaceId 和 userId，
 * 校验 space_members 表中是否存在 admin 角色的成员关系。
 *
 * <p>用法：
 * <pre>{@code
 * @DeleteMapping("/{docId}")
 * @RequireSpaceAdmin
 * public ApiResponse<Void> delete(...) { ... }
 * }</pre>
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RequireSpaceAdmin {
}
