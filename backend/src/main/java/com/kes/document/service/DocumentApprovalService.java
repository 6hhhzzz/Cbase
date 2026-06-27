package com.kes.document.service;

import com.kes.common.event.AuditLogEvent;
import com.kes.common.event.DocumentPermanentlyDeletedEvent;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.document.model.ApprovalItem;
import com.kes.document.model.DocumentApproval;
import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentApprovalRepository;
import com.kes.document.repository.DocumentMetaRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 文档审批服务 — 审批流程管理（上传/更新/删除的审批请求、审批处理）。
 *
 * <p>从 {@link DocumentService} 提取，职责聚焦于审批生命周期。
 * 审批通过后的实际操作（入库消息、软删除等）委托给对应的 Service。</p>
 */
@Service
public class DocumentApprovalService {

    private static final Logger log = LoggerFactory.getLogger(DocumentApprovalService.class);

    private final DocumentApprovalRepository approvalRepo;
    private final DocumentMetaRepository docRepo;
    private final RabbitTemplate rabbitTemplate;
    private final ApplicationEventPublisher eventPublisher;
    private final DocumentTrashService trashService;

    public DocumentApprovalService(DocumentApprovalRepository approvalRepo,
                                   DocumentMetaRepository docRepo,
                                   RabbitTemplate rabbitTemplate,
                                   ApplicationEventPublisher eventPublisher,
                                   DocumentTrashService trashService) {
        this.approvalRepo = approvalRepo;
        this.docRepo = docRepo;
        this.rabbitTemplate = rabbitTemplate;
        this.eventPublisher = eventPublisher;
        this.trashService = trashService;
    }

    // ================================================================
    // 审批创建（供 DocumentService 委托调用）
    // ================================================================

    /** 创建上传审批记录 */
    public DocumentApproval createUploadApproval(String docId, String userId) {
        DocumentApproval approval = new DocumentApproval(
            UUID.randomUUID().toString(), docId, userId, "upload");
        return approvalRepo.save(approval);
    }

    /** 创建更新审批记录（含 pending 文件路径） */
    public DocumentApproval createUpdateApproval(String docId, String userId, String pendingFilePath) {
        DocumentApproval approval = new DocumentApproval(
            UUID.randomUUID().toString(), docId, userId, "update");
        approval.setPendingFilePath(pendingFilePath);
        return approvalRepo.save(approval);
    }

    // ================================================================
    // 审批流
    // ================================================================

    /** 请求删除文档 — 成员发起，创建审批 */
    public DocumentApproval requestDelete(String docId, String userId) {
        DocumentMeta meta = docRepo.findById(docId)
            .orElseThrow(() -> BusinessException.documentNotFound(docId));

        DocumentApproval approval = new DocumentApproval(
            UUID.randomUUID().toString(), docId, userId, "delete");
        approvalRepo.save(approval);

        meta.setApprovalStatus("pending");
        docRepo.save(meta);

        log.info("文档删除待审批: docId={}, user={}", docId, userId);
        return approval;
    }

    /** 查询待审批列表 */
    public List<ApprovalItem> pendingApprovals(String kbId) {
        List<Object[]> rows = approvalRepo.findByKbId(kbId);
        return rows.stream().map(row -> new ApprovalItem(
            (String) row[0],
            (String) row[1],
            (String) row[2],
            (String) row[3],
            (String) row[4],
            convertToLocalDateTime(row[5]),
            (String) row[6],
            row.length > 7 ? (String) row[7] : "upload"
        )).toList();
    }

    /** 审批通过 */
    @Transactional
    public void approve(String approvalId, String reviewerId) {
        DocumentApproval approval = approvalRepo.findById(approvalId)
            .orElseThrow(() -> new BusinessException(ErrorCode.DOC_APPROVAL_NOT_FOUND));
        String actionType = approval.getActionType() != null ? approval.getActionType() : "upload";

        approval.setStatus("approved");
        approval.setReviewedBy(reviewerId);
        approval.setReviewedAt(LocalDateTime.now());
        approvalRepo.save(approval);

        DocumentMeta meta = docRepo.findById(approval.getDocumentId()).orElse(null);
        if (meta == null) return;

        switch (actionType) {
            case "update" -> executeUpdateApproval(approval, meta, reviewerId);
            case "delete" -> executeDeleteApproval(approval, meta, reviewerId);
            default -> executeUploadApproval(meta, reviewerId);
        }

        log.info("文档审批通过: docId={}, action={}, reviewer={}",
            approval.getDocumentId(), actionType, reviewerId);
    }

    /** 审批打回 */
    public void reject(String approvalId, String reviewerId, String comment) {
        DocumentApproval approval = approvalRepo.findById(approvalId)
            .orElseThrow(() -> new BusinessException(ErrorCode.DOC_APPROVAL_NOT_FOUND));
        String actionType = approval.getActionType() != null ? approval.getActionType() : "upload";

        approval.setStatus("rejected");
        approval.setReviewedBy(reviewerId);
        approval.setReviewedAt(LocalDateTime.now());
        approval.setReviewComment(comment);
        approvalRepo.save(approval);

        docRepo.findById(approval.getDocumentId()).ifPresent(meta -> {
            meta.setApprovalStatus("rejected");
            docRepo.save(meta);

            String la = switch (actionType) {
                case "update" -> "doc.reject_update";
                case "delete" -> "doc.reject_delete";
                default -> "doc.reject";
            };
            eventPublisher.publishEvent(new AuditLogEvent(reviewerId, meta.getSpaceId(),
                la, "document", meta.getId(), meta.getFilename(),
                "{\"comment\":\"" + (comment != null ? comment.replace("\\", "\\\\").replace("\"", "\\\"") : "") + "\"}"));
        });
        log.info("文档审批打回: docId={}, action={}, reviewer={}",
            approval.getDocumentId(), actionType, reviewerId);
    }

    // ================================================================
    // 内部方法
    // ================================================================

    private void executeUploadApproval(DocumentMeta meta, String reviewerId) {
        meta.setApprovalStatus("approved");
        docRepo.save(meta);
        publishIngestMessage(meta.getId(), meta.getFilePath(), meta.getFileType(),
            meta.getKbId(), meta.getContributorId(), "admin",
            meta.getDocEffectiveDate(), meta.getDocExpiryDate(), meta.getDocVersion());
        eventPublisher.publishEvent(new AuditLogEvent(reviewerId, meta.getSpaceId(),
            "doc.approve", "document", meta.getId(), meta.getFilename(), "{\"action\":\"upload\"}"));
    }

    private void executeUpdateApproval(DocumentApproval approval, DocumentMeta meta, String reviewerId) {
        String pendingPath = approval.getPendingFilePath();
        if (pendingPath == null || pendingPath.isBlank()) {
            log.error("更新审批无 pending 文件: approvalId={}", approval.getId());
            return;
        }

        // 删除旧 chunks → 事件
        eventPublisher.publishEvent(new DocumentPermanentlyDeletedEvent(meta.getId(), meta.getKbId()));

        String newFilename = pendingPath.substring(pendingPath.lastIndexOf('/') + 1);
        meta.setFilename(newFilename);
        meta.setFilePath(pendingPath);
        meta.setFileType(newFilename.contains(".") ? newFilename.substring(newFilename.lastIndexOf('.') + 1).toLowerCase() : null);
        meta.setApprovalStatus("approved");
        meta.setIngestStatus("pending");
        docRepo.save(meta);

        publishIngestMessage(meta.getId(), pendingPath, meta.getFileType(),
            meta.getKbId(), meta.getContributorId(), "admin",
            meta.getDocEffectiveDate(), meta.getDocExpiryDate(), meta.getDocVersion());

        eventPublisher.publishEvent(new AuditLogEvent(reviewerId, meta.getSpaceId(),
            "doc.approve_update", "document", meta.getId(), newFilename, "{}"));
    }

    private void executeDeleteApproval(DocumentApproval approval, DocumentMeta meta, String reviewerId) {
        trashService.softDelete(meta.getId());
        meta.setApprovalStatus("approved");
        docRepo.save(meta);
        eventPublisher.publishEvent(new AuditLogEvent(reviewerId, meta.getSpaceId(),
            "doc.approve_delete", "document", meta.getId(), meta.getFilename(), "{}"));
    }

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

    private java.time.LocalDateTime convertToLocalDateTime(Object value) {
        if (value == null) return null;
        if (value instanceof java.time.LocalDateTime ldt) return ldt;
        if (value instanceof java.sql.Timestamp ts) return ts.toLocalDateTime();
        if (value instanceof java.util.Date d)
            return d.toInstant().atZone(java.time.ZoneId.systemDefault()).toLocalDateTime();
        return null;
    }
}
