package com.kes.document.event;

import com.kes.common.event.*;
import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentMetaRepository;
import com.kes.document.service.MinioStorageService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 文档模块事件监听器。
 * 响应 KB 生命周期事件，级联操作文档。
 */
@Component
public class DocumentEventListeners {

    private static final Logger log = LoggerFactory.getLogger(DocumentEventListeners.class);

    private final DocumentMetaRepository docMetaRepo;
    private final MinioStorageService minioStorageService;

    public DocumentEventListeners(DocumentMetaRepository docMetaRepo,
                                  MinioStorageService minioStorageService) {
        this.docMetaRepo = docMetaRepo;
        this.minioStorageService = minioStorageService;
    }

    @Transactional
    @EventListener
    public void onKbSoftDeleted(KbSoftDeletedEvent event) {
        List<DocumentMeta> docs = docMetaRepo.findByKbIdAndStatus(event.kbId(), "active");
        LocalDateTime now = LocalDateTime.now();
        for (DocumentMeta doc : docs) {
            doc.setStatus("soft_deleted");
            doc.setDeletedAt(now);
            doc.setExpiresAt(now.plusDays(30));
            docMetaRepo.save(doc);
        }
        log.info("级联软删除文档: kbId={}, count={}", event.kbId(), docs.size());
    }

    @Transactional
    @EventListener
    public void onKbRestored(KbRestoredEvent event) {
        List<DocumentMeta> docs = docMetaRepo.findByKbIdAndStatus(event.kbId(), "soft_deleted");
        for (DocumentMeta doc : docs) {
            doc.setStatus("active");
            doc.setDeletedAt(null);
            doc.setExpiresAt(null);
            docMetaRepo.save(doc);
        }
        log.info("级联恢复文档: kbId={}, count={}", event.kbId(), docs.size());
    }

    @Transactional
    @EventListener
    public void onKbPermanentlyDeleted(KbPermanentlyDeletedEvent event) {
        // 查询该 KB 下所有文档，收集文件路径用于 MinIO 清理
        List<DocumentMeta> docs = docMetaRepo.findAllByKbId(event.kbId());
        for (DocumentMeta doc : docs) {
            minioStorageService.deleteFile(doc.getFilePath());
        }
        // 删除所有文档 DB 记录
        docMetaRepo.deleteAll(docs);
        log.info("级联永久删除文档: kbId={}, count={}", event.kbId(), docs.size());
    }
}
