package com.kes.document.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * 文档审批实体 — v3.2 扩展 action_type。
 * Member 的上传/更新/删除操作后状态为 pending，Admin 审批通过/打回。
 */
@Entity
@Table(name = "document_approvals")
public class DocumentApproval {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "document_id", nullable = false, length = 36)
    private String documentId;

    @Column(name = "submitted_by", nullable = false, length = 36)
    private String submittedBy;

    @Column(name = "submitted_at", updatable = false)
    private LocalDateTime submittedAt;

    @Column(name = "reviewed_by", length = 36)
    private String reviewedBy;

    @Column(name = "reviewed_at")
    private LocalDateTime reviewedAt;

    @Column(nullable = false, length = 16)
    private String status = "pending";  // pending | approved | rejected

    @Column(name = "review_comment", columnDefinition = "TEXT")
    private String reviewComment;

    @Column(name = "action_type", nullable = false, length = 16)
    private String actionType = "upload";  // upload | update | delete

    @Column(name = "pending_file_path", length = 512)
    private String pendingFilePath;

    @Column(name = "pending_metadata", columnDefinition = "JSONB")
    private String pendingMetadata;

    @PrePersist
    protected void onCreate() {
        submittedAt = LocalDateTime.now();
    }

    public DocumentApproval() {}

    public DocumentApproval(String id, String documentId, String submittedBy, String actionType) {
        this.id = id;
        this.documentId = documentId;
        this.submittedBy = submittedBy;
        this.actionType = actionType;
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getDocumentId() { return documentId; }
    public void setDocumentId(String documentId) { this.documentId = documentId; }

    public String getSubmittedBy() { return submittedBy; }
    public void setSubmittedBy(String submittedBy) { this.submittedBy = submittedBy; }

    public LocalDateTime getSubmittedAt() { return submittedAt; }

    public String getReviewedBy() { return reviewedBy; }
    public void setReviewedBy(String reviewedBy) { this.reviewedBy = reviewedBy; }

    public LocalDateTime getReviewedAt() { return reviewedAt; }
    public void setReviewedAt(LocalDateTime reviewedAt) { this.reviewedAt = reviewedAt; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getReviewComment() { return reviewComment; }
    public void setReviewComment(String reviewComment) { this.reviewComment = reviewComment; }

    public String getActionType() { return actionType; }
    public void setActionType(String actionType) { this.actionType = actionType; }

    public String getPendingFilePath() { return pendingFilePath; }
    public void setPendingFilePath(String pendingFilePath) { this.pendingFilePath = pendingFilePath; }

    public String getPendingMetadata() { return pendingMetadata; }
    public void setPendingMetadata(String pendingMetadata) { this.pendingMetadata = pendingMetadata; }
}
