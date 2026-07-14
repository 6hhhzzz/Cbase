package com.kes.document.service;

import com.kes.common.event.AuditLogEvent;
import com.kes.common.event.DocumentPermanentlyDeletedEvent;
import com.kes.common.event.DocumentStatusChangedEvent;
import com.kes.common.exception.BusinessException;
import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentMetaRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 文档回收站服务 — 软删除、恢复、永久删除。
 *
 * <p>从 {@link DocumentService} 提取，职责聚焦于文档生命周期终结操作。
 * 跨模块副作用（AI 同步、ACE 清理、审计日志）通过 {@link ApplicationEventPublisher} 发布事件。</p>
 */
@Service
public class DocumentTrashService {

    private static final Logger log = LoggerFactory.getLogger(DocumentTrashService.class);

    private final DocumentMetaRepository docRepo;
    private final MinioStorageService minioStorage;
    private final ApplicationEventPublisher eventPublisher;

    public DocumentTrashService(DocumentMetaRepository docRepo,
                                MinioStorageService minioStorage,
                                ApplicationEventPublisher eventPublisher) {
        this.docRepo = docRepo;
        this.minioStorage = minioStorage;
        this.eventPublisher = eventPublisher;
    }

    /** 管理员软删除 — 直接生效，无需审批 */
    @Transactional
    public void softDelete(String docId) {
        DocumentMeta meta = docRepo.findById(docId)
            .orElseThrow(() -> BusinessException.documentNotFound(docId));

        LocalDateTime now = LocalDateTime.now();
        meta.setStatus("soft_deleted");
        meta.setDeletedAt(now);
        meta.setExpiresAt(now.plusDays(30));
        docRepo.save(meta);

        // AI 同步 → 事件
        eventPublisher.publishEvent(new DocumentStatusChangedEvent(docId, meta.getKbId(), "soft_deleted"));
        eventPublisher.publishEvent(new AuditLogEvent(meta.getUploadedBy(), meta.getSpaceId(),
            "doc.trash", "document", docId, meta.getFilename(), "{}"));

        log.info("文档已软删除: docId={}, expiresAt={}", docId, meta.getExpiresAt());
    }

    /** 恢复文档 */
    @Transactional
    public void restore(String docId) {
        DocumentMeta meta = docRepo.findById(docId)
            .orElseThrow(() -> BusinessException.documentNotFound(docId));

        meta.setStatus("active");
        meta.setDeletedAt(null);
        meta.setExpiresAt(null);
        docRepo.save(meta);

        eventPublisher.publishEvent(new DocumentStatusChangedEvent(docId, meta.getKbId(), "active"));
        eventPublisher.publishEvent(new AuditLogEvent(meta.getUploadedBy(), meta.getSpaceId(),
            "doc.restore", "document", docId, meta.getFilename(), "{}"));

        log.info("文档已恢复: docId={}", docId);
    }

    /** 永久删除文档 */
    @Transactional
    public void permanentDelete(String docId) {
        DocumentMeta meta = docRepo.findById(docId)
            .orElseThrow(() -> BusinessException.documentNotFound(docId));

        minioStorage.deleteFile(meta.getFilePath());

        String filename = meta.getFilename();
        String kbId = meta.getKbId();
        String spaceId = meta.getSpaceId();
        String uploadedBy = meta.getUploadedBy();
        docRepo.delete(meta);

        // AI chunks 删除 → rag 模块处理；ACE 清理 → auth 模块处理
        eventPublisher.publishEvent(new DocumentPermanentlyDeletedEvent(docId, kbId));
        eventPublisher.publishEvent(new AuditLogEvent(uploadedBy, spaceId,
            "doc.delete_permanent", "document", docId, filename, "{}"));

        log.info("文档永久删除: docId={}, file={}", docId, filename);
    }

    /** 批量软删除 — Controller 已做权鉴，Service 只做批量操作 */
    @Transactional
    public void batchSoftDelete(List<String> docIds) {
        List<DocumentMeta> metas = docRepo.findAllById(docIds);
        LocalDateTime now = LocalDateTime.now();

        for (DocumentMeta meta : metas) {
            meta.setStatus("soft_deleted");
            meta.setDeletedAt(now);
            meta.setExpiresAt(now.plusDays(30));
        }
        docRepo.saveAll(metas);

        for (DocumentMeta meta : metas) {
            eventPublisher.publishEvent(new DocumentStatusChangedEvent(
                meta.getId(), meta.getKbId(), "soft_deleted"));
            eventPublisher.publishEvent(new AuditLogEvent(meta.getUploadedBy(), meta.getSpaceId(),
                "doc.trash", "document", meta.getId(), meta.getFilename(), "{}"));
        }

        log.info("批量软删除完成: count={}", metas.size());
    }

    /** 批量永久删除 — Controller 已做权鉴，Service 只做批量操作 */
    @Transactional
    public void batchPermanentDelete(List<String> docIds) {
        List<DocumentMeta> metas = docRepo.findAllById(docIds);

        for (DocumentMeta meta : metas) {
            minioStorage.deleteFile(meta.getFilePath());

            String filename = meta.getFilename();
            String kbId = meta.getKbId();
            String spaceId = meta.getSpaceId();
            String uploadedBy = meta.getUploadedBy();

            eventPublisher.publishEvent(new DocumentPermanentlyDeletedEvent(meta.getId(), kbId));
            eventPublisher.publishEvent(new AuditLogEvent(uploadedBy, spaceId,
                "doc.delete_permanent", "document", meta.getId(), filename, "{}"));
        }

        docRepo.deleteAll(metas);
        log.info("批量永久删除完成: count={}", metas.size());
    }
}
