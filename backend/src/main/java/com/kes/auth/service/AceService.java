package com.kes.auth.service;

import com.kes.auth.model.AccessControlEntry;
import com.kes.auth.repository.AceRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.service.AuditLogger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

/**
 * ACE（访问控制条目）管理服务。
 * 负责 Access Control Entries 的 CRUD，ACE 矩阵是 v4 权限模型的核心。
 *
 * <p>所有写操作需要 Space admin 权限（通过 {@link PermissionService} 校验）。
 */
@Service
public class AceService {

    private static final Logger log = LoggerFactory.getLogger(AceService.class);

    private final AceRepository aceRepo;
    private final KbPermissionCache permissionCache;
    private final PermissionService permService;
    private final AuditLogger auditLogger;

    public AceService(AceRepository aceRepo,
                      KbPermissionCache permissionCache,
                      PermissionService permService,
                      AuditLogger auditLogger) {
        this.aceRepo = aceRepo;
        this.permissionCache = permissionCache;
        this.permService = permService;
        this.auditLogger = auditLogger;
    }

    /** 查询 Space 中指定资源类型的所有 ACE 条目 */
    public List<AccessControlEntry> getAces(String spaceId, String resourceType) {
        return aceRepo.findBySpaceIdAndResourceType(spaceId,
            resourceType != null ? resourceType : "kb");
    }

    /** 创建 ACE 条目 — Space admin */
    @Transactional
    public AccessControlEntry createAce(String operatorId, String spaceId, String resourceType,
                                         String resourceId, String principalType, String principalId,
                                         String roleId, String effect, int priority) {
        permService.requireSpaceAdmin(spaceId, operatorId);

        if (aceRepo.existsBySpaceIdAndResourceTypeAndResourceIdAndPrincipalTypeAndPrincipalId(
            spaceId, resourceType, resourceId, principalType, principalId)) {
            throw new BusinessException(ErrorCode.ACE_ALREADY_EXISTS);
        }

        AccessControlEntry ace = new AccessControlEntry(
            UUID.randomUUID().toString(), spaceId, resourceType, resourceId,
            principalType, principalId, roleId,
            effect != null ? effect : "allow", priority);
        ace = aceRepo.save(ace);
        permissionCache.evictBySpace(spaceId);

        auditLogger.log(operatorId, spaceId, "ace.create", resourceType, ace.getId(), null,
            "{\"principal\":\"" + principalType + ":" + principalId + "\",\"effect\":\"" + ace.getEffect() + "\"}");
        log.info("ACE 创建: space={}, {}:{} → {}:{}, effect={}",
            spaceId, principalType, principalId, resourceType, resourceId, ace.getEffect());
        return ace;
    }

    /** 修改 ACE — Space admin */
    @Transactional
    public AccessControlEntry updateAce(String operatorId, String spaceId, String aceId,
                                         String roleId, String effect, Integer priority) {
        permService.requireSpaceAdmin(spaceId, operatorId);

        AccessControlEntry ace = aceRepo.findById(aceId)
            .orElseThrow(() -> new BusinessException(ErrorCode.ACE_NOT_FOUND));
        if (roleId != null) ace.setRoleId(roleId);
        if (effect != null) ace.setEffect(effect);
        if (priority != null) ace.setPriority(priority);
        ace = aceRepo.save(ace);
        permissionCache.evictBySpace(spaceId);

        log.info("ACE 更新: id={}, effect={}, role={}", aceId, ace.getEffect(), ace.getRoleId());
        return ace;
    }

    /** 删除 ACE — Space admin */
    @Transactional
    public void deleteAce(String operatorId, String spaceId, String aceId) {
        permService.requireSpaceAdmin(spaceId, operatorId);
        aceRepo.deleteById(aceId);
        permissionCache.evictBySpace(spaceId);

        auditLogger.log(operatorId, spaceId, "ace.delete", "ace", aceId, null, "{}");
        log.info("ACE 删除: id={}", aceId);
    }
}
