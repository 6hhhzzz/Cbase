package com.kes.auth.service;

import com.kes.auth.model.AdminActionLog;
import com.kes.auth.model.Space;
import com.kes.auth.model.User;
import com.kes.auth.repository.AdminActionLogRepository;
import com.kes.auth.repository.SpaceRepository;
import com.kes.auth.repository.UserRepository;
import com.kes.common.dto.SpaceDtos.AuditLogInfo;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.service.AuditLogger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 全局管理员服务。
 * 处理跨 Space 的全局管理操作，仅限全局超级管理员调用。
 * 用户管理相关操作已拆分到 {@link UserAdminService} 和 {@link UserImportService}。
 *
 * <p>依赖：{@link PermissionService}（权限校验）、{@link AuditLogger}（操作记录）
 */
@Service
public class AdminService {

    private static final Logger log = LoggerFactory.getLogger(AdminService.class);

    private final UserRepository userRepo;
    private final SpaceRepository spaceRepo;
    private final PermissionService permService;
    private final AdminActionLogRepository auditLogRepo;
    private final AuditLogger auditLogger;

    public AdminService(UserRepository userRepo,
                        SpaceRepository spaceRepo,
                        PermissionService permService,
                        AdminActionLogRepository auditLogRepo,
                        AuditLogger auditLogger) {
        this.userRepo = userRepo;
        this.spaceRepo = spaceRepo;
        this.permService = permService;
        this.auditLogRepo = auditLogRepo;
        this.auditLogger = auditLogger;
    }

    // ================================================================
    // Space 全局管理
    // ================================================================

    /** 列出所有活跃 Space */
    public List<Space> getAllSpaces(String operatorId) {
        permService.requireGlobalAdmin(operatorId);
        return spaceRepo.findAllActive();
    }

    /** 归档任意 Space */
    @Transactional
    public void globalArchiveSpace(String operatorId, String spaceId) {
        permService.requireGlobalAdmin(operatorId);
        Space space = spaceRepo.findById(spaceId)
            .orElseThrow(() -> new BusinessException(ErrorCode.SPACE_NOT_FOUND));
        space.setStatus("archived");
        spaceRepo.save(space);
        auditLogger.log(operatorId, spaceId, "space.archive", "space", spaceId, space.getName(), "{}");
        log.info("全局管理员归档 Space: id={}", spaceId);
    }

    /** 软删除任意 Space */
    @Transactional
    public void globalDeleteSpace(String operatorId, String spaceId) {
        permService.requireGlobalAdmin(operatorId);
        Space space = spaceRepo.findById(spaceId)
            .orElseThrow(() -> new BusinessException(ErrorCode.SPACE_NOT_FOUND));
        space.setDeletedAt(LocalDateTime.now());
        spaceRepo.save(space);
        auditLogger.log(operatorId, spaceId, "space.trash", "space", spaceId, space.getName(), "{}");
        log.info("全局管理员软删除 Space: id={}", spaceId);
    }

    /** 恢复软删除的 Space */
    @Transactional
    public void globalRestoreSpace(String operatorId, String spaceId) {
        permService.requireGlobalAdmin(operatorId);
        Space space = spaceRepo.findById(spaceId)
            .orElseThrow(() -> new BusinessException(ErrorCode.SPACE_NOT_FOUND));
        space.setDeletedAt(null);
        space.setStatus("active");
        spaceRepo.save(space);
        auditLogger.log(operatorId, spaceId, "space.restore", "space", spaceId, space.getName(), "{}");
        log.info("全局管理员恢复 Space: id={}", spaceId);
    }

    // ================================================================
    // 操作日志查询（跨 Space 通用）
    // ================================================================

    /**
     * 查询 Space 的操作日志。
     * 需要 Space admin 权限。
     */
    public Page<AdminActionLog> getAuditLogs(String spaceId, String operatorId, int page, int size) {
        permService.requireSpaceAdmin(spaceId, operatorId);
        Pageable pageable = PageRequest.of(page, size);
        return auditLogRepo.findBySpaceIdOrderByCreatedAtDesc(spaceId, pageable);
    }

    /**
     * 查询 Space 的操作日志（含操作人显示名，供 Controller 使用）。
     * 在 Service 层完成 operatorName 解析，Controller 无需访问 Repository。
     */
    public Page<AuditLogInfo> getAuditLogsWithOperatorNames(String spaceId, String operatorId, int page, int size) {
        Page<AdminActionLog> logs = getAuditLogs(spaceId, operatorId, page, size);
        List<AuditLogInfo> items = logs.getContent().stream().map(log ->
            new AuditLogInfo(log.getId(), log.getOperatorId(),
                userRepo.findById(log.getOperatorId()).map(User::getDisplayName).orElse(log.getOperatorId()),
                log.getAction(), log.getTargetType(), log.getTargetId(), log.getTargetName(),
                log.getDetails(), log.getCreatedAt())
        ).toList();
        return new PageImpl<>(items, logs.getPageable(), logs.getTotalElements());
    }
}
