package com.kes.auth.service;

import com.kes.auth.model.KnowledgeBase;
import com.kes.auth.repository.KnowledgeBaseRepository;
import com.kes.common.dto.SpaceDtos.TrashItem;
import com.kes.common.event.*;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.service.AuditLogger;
import com.kes.document.model.DocumentMeta;
import com.kes.document.service.DocumentQueryService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.stream.Collectors;

/**
 * 知识库 (KB) 管理服务 — v4 解耦版。
 *
 * <p>负责 KB 全生命周期管理：创建、修改、软删除、恢复、永久删除、回收站查询。
 * 跨模块副作用（文档级联、AI 同步、ACE 清理）通过 {@link ApplicationEventPublisher} 发布事件，
 * 由对应模块的 {@code @EventListener} 处理。</p>
 *
 * <p>跨模块查询保留：为构建 {@link KbPermanentlyDeletedEvent} 载荷，
 * 保留对 {@link DocumentMeta} / {@link DocumentMetaRepository} 的只读依赖。</p>
 */
@Service
public class KbService {

    private static final Logger log = LoggerFactory.getLogger(KbService.class);

    private final KnowledgeBaseRepository kbRepo;
    private final KbPermissionCache permissionCache;
    private final PermissionService permService;
    private final DocumentQueryService documentQueryService;
    private final AuditLogger auditLogger;
    private final ApplicationEventPublisher eventPublisher;

    public KbService(KnowledgeBaseRepository kbRepo,
                     KbPermissionCache permissionCache,
                     PermissionService permService,
                     DocumentQueryService documentQueryService,
                     AuditLogger auditLogger,
                     ApplicationEventPublisher eventPublisher) {
        this.kbRepo = kbRepo;
        this.permissionCache = permissionCache;
        this.permService = permService;
        this.documentQueryService = documentQueryService;
        this.auditLogger = auditLogger;
        this.eventPublisher = eventPublisher;
    }

    // ================================================================
    // KB CRUD
    // ================================================================

    @Transactional
    public KnowledgeBase createKb(String operatorId, String spaceId, String name,
                                   String description, String visibility) {
        permService.requireSpaceAdmin(spaceId, operatorId);

        String kbId = UUID.randomUUID().toString();
        String vis = ("restricted".equals(visibility)) ? "restricted" : "space_wide";
        KnowledgeBase kb = new KnowledgeBase(kbId, spaceId, name,
            description != null ? description : "", vis, operatorId);
        kb = kbRepo.save(kb);

        permissionCache.evictBySpace(spaceId);

        auditLogger.log(operatorId, spaceId, "kb.create", "kb", kbId, name,
            "{\"visibility\":\"" + vis + "\"}");
        log.info("KB 创建: id={}, name={}, space={}, visibility={}", kbId, name, spaceId, vis);
        return kb;
    }

    public List<KnowledgeBase> listKbs(String spaceId) {
        return kbRepo.findBySpaceIdAndDeletedAtIsNull(spaceId);
    }

    /** 获取 Space 下所有活跃 KB（供 SpaceController 回收站等查询使用） */
    public List<KnowledgeBase> getActiveKbs(String spaceId) {
        return kbRepo.findBySpaceIdAndDeletedAtIsNull(spaceId);
    }

    @Transactional
    public void updateKb(String operatorId, String spaceId, String kbId, String name, String visibility) {
        KnowledgeBase kb = kbRepo.findById(kbId)
            .orElseThrow(() -> new BusinessException(ErrorCode.KB_NOT_FOUND));
        permService.requireSpaceAdmin(spaceId, operatorId);

        String oldVisibility = kb.getVisibility();
        if (name != null && !name.isBlank()) {
            kb.setName(name);
        }
        if (visibility != null && !visibility.isBlank()) {
            kb.setVisibility(visibility);
        }
        kbRepo.save(kb);

        if (!oldVisibility.equals(kb.getVisibility())) {
            permissionCache.evictBySpace(spaceId);
        }

        auditLogger.log(operatorId, spaceId, "kb.update", "kb", kbId, kb.getName(),
            "{\"old_visibility\":\"" + oldVisibility + "\",\"new_visibility\":\"" + kb.getVisibility() + "\"}");
        log.info("KB 修改: id={}, visibility: {} -> {}", kbId, oldVisibility, kb.getVisibility());
    }

    // ================================================================
    // KB 软删除 / 恢复 / 永久删除
    // ================================================================

    @Transactional
    public void softDeleteKb(String operatorId, String spaceId, String kbId) {
        KnowledgeBase kb = kbRepo.findById(kbId)
            .orElseThrow(() -> new BusinessException(ErrorCode.KB_NOT_FOUND));
        permService.requireSpaceAdmin(spaceId, operatorId);

        LocalDateTime now = LocalDateTime.now();
        kb.setDeletedAt(now);
        kbRepo.save(kb);
        permissionCache.evictBySpace(spaceId);

        // 级联文档 + AI 同步 → 事件（监听器自行查询文档数据）
        eventPublisher.publishEvent(new KbSoftDeletedEvent(kbId, spaceId, operatorId, kb.getName()));

        auditLogger.log(operatorId, spaceId, "kb.trash", "kb", kbId, kb.getName(), "{}");
        log.info("KB 软删除: id={}, name={}", kbId, kb.getName());
    }

    @Transactional
    public void restoreKb(String operatorId, String spaceId, String kbId) {
        KnowledgeBase kb = kbRepo.findById(kbId)
            .orElseThrow(() -> new BusinessException(ErrorCode.KB_NOT_FOUND));
        permService.requireSpaceAdmin(spaceId, operatorId);

        kb.setDeletedAt(null);
        kbRepo.save(kb);
        permissionCache.evictBySpace(spaceId);

        // 级联恢复文档 + AI 同步 → 事件（监听器自行查询文档数据）
        eventPublisher.publishEvent(new KbRestoredEvent(kbId, spaceId, operatorId, kb.getName()));

        auditLogger.log(operatorId, spaceId, "kb.restore", "kb", kbId, kb.getName(), "{}");
        log.info("KB 恢复: id={}, name={}", kbId, kb.getName());
    }

    @Transactional
    public void permanentDeleteKb(String operatorId, String spaceId, String kbId) {
        KnowledgeBase kb = kbRepo.findById(kbId)
            .orElseThrow(() -> new BusinessException(ErrorCode.KB_NOT_FOUND));
        permService.requireSpaceAdmin(spaceId, operatorId);

        String kbName = kb.getName();

        // 先删除 KB
        kbRepo.delete(kb);

        // 文档清理（MinIO + DB）→ document 模块监听器自行查询
        // ACE 清理 → auth 模块监听器处理
        // AI chunks 删除 → rag 模块监听器处理
        eventPublisher.publishEvent(new KbPermanentlyDeletedEvent(
            kbId, spaceId, operatorId, kbName));

        auditLogger.log(operatorId, spaceId, "kb.delete_permanent", "kb", kbId, kbName, "{}");
        log.info("KB 永久删除: id={}, name={}", kbId, kbName);
    }

    // ================================================================
    // 回收站
    // ================================================================

    public List<KnowledgeBase> getDeletedKbs(String spaceId) {
        return kbRepo.findBySpaceIdAndDeletedAtIsNotNull(spaceId);
    }

    /**
     * 获取 Space 回收站完整数据（含 KB 和文档的 TrashItem 列表）。
     * 在 Service 层完成跨模块数据聚合，Controller 无需直接依赖 DocumentService。
     */
    public Map<String, Object> getTrashData(String spaceId) {
        List<KnowledgeBase> deletedKbs = getDeletedKbs(spaceId);
        List<TrashItem> kbItems = deletedKbs.stream().map(kb ->
            new TrashItem("kb", kb.getId(), kb.getName(),
                null, null, null, kb.getDeletedAt(), null,
                kb.getDeletedAt() != null
                    ? (int) ChronoUnit.DAYS.between(LocalDateTime.now(),
                        kb.getDeletedAt().plusDays(30)) : null)
        ).toList();

        List<KnowledgeBase> activeKbs = getActiveKbs(spaceId);
        Map<String, String> kbNameMap = activeKbs.stream()
            .collect(Collectors.toMap(KnowledgeBase::getId, KnowledgeBase::getName));
        List<String> activeKbIds = activeKbs.stream().map(KnowledgeBase::getId).toList();

        List<DocumentMeta> deletedDocs = documentQueryService.getDeletedDocsInKbs(activeKbIds);
        List<TrashItem> docItems = deletedDocs.stream().map(doc ->
            new TrashItem("document", doc.getId(), doc.getFilename(),
                doc.getKbId(), kbNameMap.getOrDefault(doc.getKbId(), ""),
                doc.getFileType(), doc.getDeletedAt(), doc.getExpiresAt(),
                doc.getDeletedAt() != null
                    ? (int) ChronoUnit.DAYS.between(LocalDateTime.now(), doc.getDeletedAt().plusDays(30))
                    : null)
        ).toList();

        return Map.of("kb_items", kbItems, "doc_items", docItems);
    }
}
