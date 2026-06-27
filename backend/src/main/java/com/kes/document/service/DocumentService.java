package com.kes.document.service;

import com.kes.common.event.AuditLogEvent;
import com.kes.common.event.DocumentPermanentlyDeletedEvent;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.document.model.DocumentApproval;
import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentMetaRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * 文档管理服务 — v3.2 Space/KB RBAC + 审批流程。
 *
 * <p>v4 解耦：跨模块副作用（AI 同步、ACE 清理、审计日志）通过 {@link ApplicationEventPublisher} 发布事件，
 * 由对应模块的 {@code @EventListener} 处理。不再直接依赖 auth/rag 模块的 Repository/Service。</p>
 *
 * <p>拆分后保留职责：文档上传、更新请求、管理员直接更新、入库消息发布。
 * 查询操作见 {@link DocumentQueryService}，审批操作见 {@link DocumentApprovalService}，
 * 软删除/恢复/永久删除见 {@link DocumentTrashService}，元数据更新见 {@link DocumentMetadataService}。</p>
 */
@Service
public class DocumentService {

    private static final Logger log = LoggerFactory.getLogger(DocumentService.class);
    private static final Set<String> ALLOWED_TYPES = Set.of("pdf", "docx", "xlsx", "md", "html", "txt");
    private static final long MAX_FILE_SIZE = 50L * 1024 * 1024;

    private final DocumentMetaRepository docRepo;
    private final MinioStorageService minioStorage;
    private final RabbitTemplate rabbitTemplate;
    private final ApplicationEventPublisher eventPublisher;
    private final DocumentQueryService queryService;
    private final DocumentApprovalService approvalService;

    public DocumentService(DocumentMetaRepository docRepo,
                           MinioStorageService minioStorage,
                           RabbitTemplate rabbitTemplate,
                           ApplicationEventPublisher eventPublisher,
                           DocumentQueryService queryService,
                           DocumentApprovalService approvalService) {
        this.docRepo = docRepo;
        this.minioStorage = minioStorage;
        this.rabbitTemplate = rabbitTemplate;
        this.eventPublisher = eventPublisher;
        this.queryService = queryService;
        this.approvalService = approvalService;
    }

    /** 上传文档 — 管理员直接通过，成员需审批 */
    public DocumentMeta upload(MultipartFile file, String kbId, String userId, String role,
                               LocalDate effectiveDate, LocalDate expiryDate, String version,
                               String spaceId) {
        String originalName = file.getOriginalFilename();
        String ext = getExtension(originalName);
        if (ext == null || !ALLOWED_TYPES.contains(ext)) {
            throw BusinessException.unsupportedFileType(ext);
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw BusinessException.fileTooLarge(MAX_FILE_SIZE);
        }

        String docId = UUID.randomUUID().toString();
        String objectKey = docId + "/" + originalName;

        try {
            minioStorage.uploadFile(objectKey, file.getInputStream(), file.getSize(), file.getContentType());
        } catch (Exception e) {
            log.error("MinIO 上传失败: docId={}, file={}", docId, originalName, e);
            throw new BusinessException(ErrorCode.DOC_UPLOAD_FAILED);
        }

        boolean isAdmin = "admin".equals(role);
        String approvalStatus = isAdmin ? "approved" : "pending";

        DocumentMeta meta = new DocumentMeta();
        meta.setId(docId);
        meta.setFilename(originalName);
        meta.setFileType(ext);
        meta.setFileSize(file.getSize());
        meta.setFilePath(objectKey);
        meta.setKbId(kbId);
        meta.setSpaceId(spaceId);
        meta.setContributorId(userId);
        meta.setApprovalStatus(approvalStatus);
        meta.setIngestStatus("pending");
        meta.setUploadedBy(userId);
        meta.setDocEffectiveDate(effectiveDate != null ? effectiveDate : LocalDate.now());
        meta.setDocExpiryDate(expiryDate);
        meta.setDocVersion(version);
        docRepo.save(meta);

        if (!isAdmin) {
            approvalService.createUploadApproval(docId, userId);
            log.info("文档上传待审批: docId={}, user={}", docId, userId);
        } else {
            publishIngestMessage(docId, objectKey, ext, kbId, userId, role,
                meta.getDocEffectiveDate(), meta.getDocExpiryDate(), meta.getDocVersion());
        }

        eventPublisher.publishEvent(new AuditLogEvent(userId, spaceId,
            "doc.upload", "document", docId, originalName, "{}"));

        return meta;
    }

    /** 请求更新文档 — 成员上传新文件，创建审批 */
    public DocumentApproval requestUpdate(String docId, MultipartFile file, String userId) {
        DocumentMeta meta = queryService.getById(docId);

        String originalName = file.getOriginalFilename();
        String ext = getExtension(originalName);
        if (ext == null || !ALLOWED_TYPES.contains(ext)) {
            throw BusinessException.unsupportedFileType(ext);
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            throw BusinessException.fileTooLarge(MAX_FILE_SIZE);
        }

        String pendingKey = docId + "/pending/" + UUID.randomUUID() + "/" + originalName;
        try {
            minioStorage.uploadFile(pendingKey, file.getInputStream(), file.getSize(), file.getContentType());
        } catch (Exception e) {
            log.error("更新文件上传失败: docId={}, file={}", docId, originalName, e);
            throw new BusinessException(ErrorCode.DOC_UPLOAD_FAILED);
        }

        DocumentApproval approval = approvalService.createUpdateApproval(docId, userId, pendingKey);

        meta.setApprovalStatus("pending");
        docRepo.save(meta);

        log.info("文档更新待审批: docId={}, user={}, pendingFile={}", docId, userId, pendingKey);
        return approval;
    }

    /** 管理员直接更新文档 — 无需审批，直接替换文件并重新入库 */
    @Transactional
    public DocumentMeta adminUpdate(String docId, MultipartFile file, String reviewerId) {
        DocumentMeta meta = queryService.getById(docId);

        String originalName = file.getOriginalFilename();
        String ext = getExtension(originalName);
        if (ext == null || !ALLOWED_TYPES.contains(ext)) {
            throw BusinessException.unsupportedFileType(ext);
        }

        String newKey = docId + "/" + originalName;
        try {
            minioStorage.uploadFile(newKey, file.getInputStream(), file.getSize(), file.getContentType());
        } catch (Exception e) {
            log.error("管理员更新文件上传失败: docId={}", docId, e);
            throw new BusinessException(ErrorCode.DOC_UPLOAD_FAILED, "文件存储失败");
        }

        // 删除旧 chunks → 发布事件，由 rag 模块处理
        eventPublisher.publishEvent(new DocumentPermanentlyDeletedEvent(docId, meta.getKbId()));
        meta.setFilename(originalName);
        meta.setFileType(ext);
        meta.setFileSize(file.getSize());
        meta.setFilePath(newKey);
        meta.setApprovalStatus("approved");
        meta.setIngestStatus("pending");
        docRepo.save(meta);

        publishIngestMessage(docId, newKey, ext, meta.getKbId(), meta.getContributorId(), "admin",
            meta.getDocEffectiveDate(), meta.getDocExpiryDate(), meta.getDocVersion());

        eventPublisher.publishEvent(new AuditLogEvent(reviewerId, meta.getSpaceId(),
            "doc.update", "document", docId, meta.getFilename(), "{}"));
        log.info("管理员直接更新文档: docId={}, newFile={}", docId, originalName);
        return meta;
    }

    // ================================================================
    // 内部方法
    // ================================================================

    private void publishIngestMessage(String docId, String filePath, String fileType,
                                       String kbId, String userId, String role,
                                       LocalDate effectiveDate, LocalDate expiryDate,
                                       String version) {
        Map<String, Object> mqMessage = new LinkedHashMap<>();
        mqMessage.put("doc_id", docId);
        mqMessage.put("file_path", filePath);
        mqMessage.put("file_type", fileType);

        Map<String, Object> mqMeta = new LinkedHashMap<>();
        mqMeta.put("kb_id", kbId);
        mqMeta.put("contributor_id", userId);
        mqMeta.put("uploader_role", role);
        mqMeta.put("effective_date", effectiveDate != null ? effectiveDate.toString() : null);
        mqMeta.put("expiry_date", expiryDate != null ? expiryDate.toString() : null);
        mqMeta.put("version", version);
        mqMessage.put("metadata", mqMeta);

        rabbitTemplate.convertAndSend("kes.document", "document.ingest", mqMessage);
        log.info("文档入库消息已投递: docId={}", docId);
    }

    private String getExtension(String filename) {
        if (filename == null || !filename.contains(".")) return null;
        return filename.substring(filename.lastIndexOf('.') + 1).toLowerCase();
    }
}
