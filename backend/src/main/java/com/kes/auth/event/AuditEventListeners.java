package com.kes.auth.event;

import com.kes.auth.model.AdminActionLog;
import com.kes.auth.repository.AdminActionLogRepository;
import com.kes.common.event.AuditLogEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * 审计日志事件监听器。
 * 监听 AuditLogEvent，持久化 AdminActionLog 实体。
 */
@Component
public class AuditEventListeners {

    private static final Logger log = LoggerFactory.getLogger(AuditEventListeners.class);

    private final AdminActionLogRepository auditLogRepo;

    public AuditEventListeners(AdminActionLogRepository auditLogRepo) {
        this.auditLogRepo = auditLogRepo;
    }

    @EventListener
    public void onAuditLogEvent(AuditLogEvent event) {
        try {
            AdminActionLog logEntry = new AdminActionLog(
                event.operatorId(),
                event.spaceId(),
                event.action(),
                event.targetType(),
                event.targetId(),
                event.targetName(),
                event.details()
            );
            auditLogRepo.save(logEntry);
        } catch (Exception e) {
            log.warn("操作日志记录失败: action={}, error={}", event.action(), e.getMessage());
        }
    }
}
