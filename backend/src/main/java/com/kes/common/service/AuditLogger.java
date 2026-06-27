package com.kes.common.service;

import com.kes.common.event.AuditLogEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

/**
 * 统一审计日志服务。
 * 所有管理操作的审计日志通过此服务统一发布事件，由 auth 模块的
 * {@code AuditEventListeners} 监听并持久化。
 *
 * <p>使用方式：各业务 Service 注入 AuditLogger，调用 {@link #log} 发布事件。
 * 事件发布失败不会影响主流程。</p>
 */
@Service
public class AuditLogger {

    private static final Logger log = LoggerFactory.getLogger(AuditLogger.class);

    private final ApplicationEventPublisher eventPublisher;

    public AuditLogger(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    /**
     * 发布审计日志事件。
     *
     * @param operatorId 操作人 userId
     * @param spaceId    所属 Space
     * @param action     操作类型（如 space.create, kb.trash, ace.delete）
     * @param targetType 目标类型（如 space, kb, ace, user, group）
     * @param targetId   目标 ID
     * @param targetName 目标名称（可选）
     * @param details    JSON 格式的额外信息
     */
    public void log(String operatorId, String spaceId, String action,
                    String targetType, String targetId, String targetName, String details) {
        try {
            eventPublisher.publishEvent(new AuditLogEvent(
                operatorId, spaceId, action, targetType, targetId, targetName, details));
        } catch (Exception e) {
            log.warn("操作日志事件发布失败: action={}, error={}", action, e.getMessage());
        }
    }
}
