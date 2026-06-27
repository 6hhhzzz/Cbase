package com.kes.common.event;

/**
 * 审计日志事件。
 * 由各 Service 通过 AuditLogger 发布，AuditEventListeners 监听持久化到 admin_action_logs 表。
 */
public record AuditLogEvent(
    String operatorId,
    String spaceId,
    String action,
    String targetType,
    String targetId,
    String targetName,
    String details
) {}
