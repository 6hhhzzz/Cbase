package com.kes.document.model;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * 文档元数据实体 — v3 Space/KB RBAC。
 */
@Entity
@Table(name = "document_meta")
public class DocumentMeta {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false, length = 255)
    private String filename;

    @Column(nullable = false, length = 16)
    private String fileType;

    @Column(nullable = false)
    private Long fileSize;

    @Column(nullable = false, length = 512)
    private String filePath;

    @Column(name = "kb_id", nullable = false, length = 36)
    private String kbId;

    /** v4 解耦：冗余存储 spaceId，避免跨模块查询 kb → space */
    @Column(name = "space_id", nullable = false, length = 36)
    private String spaceId;

    @Column(nullable = false, length = 16)
    private String status = "active";  // active | soft_deleted

    @Column(name = "deleted_at")
    private LocalDateTime deletedAt;

    @Column(name = "expires_at")
    private LocalDateTime expiresAt;

    @Column(name = "doc_effective_date", nullable = false)
    private LocalDate docEffectiveDate;

    @Column(name = "doc_expiry_date")
    private LocalDate docExpiryDate;

    @Column(name = "doc_version", length = 32)
    private String docVersion;

    @Column(length = 36)
    private String contributorId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "JSONB")
    private String tags;

    @Column(nullable = false, length = 16)
    private String approvalStatus = "approved";

    /** v4 ACE: 是否继承 KB 权限。false 时阻断继承，仅按 document ACE 判断。 */
    @Column(name = "inherit_permissions", nullable = false)
    private boolean inheritPermissions = true;

    @Column(nullable = false, length = 16)
    private String ingestStatus = "pending";

    @Column(nullable = false, length = 36)
    private String uploadedBy;

    @Column(updatable = false)
    private LocalDateTime createdAt;

    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    // ---- Getters / Setters ----

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getFilename() { return filename; }
    public void setFilename(String filename) { this.filename = filename; }

    public String getFileType() { return fileType; }
    public void setFileType(String fileType) { this.fileType = fileType; }

    public Long getFileSize() { return fileSize; }
    public void setFileSize(Long fileSize) { this.fileSize = fileSize; }

    public String getFilePath() { return filePath; }
    public void setFilePath(String filePath) { this.filePath = filePath; }

    public String getKbId() { return kbId; }
    public void setKbId(String kbId) { this.kbId = kbId; }

    public String getSpaceId() { return spaceId; }
    public void setSpaceId(String spaceId) { this.spaceId = spaceId; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public LocalDateTime getDeletedAt() { return deletedAt; }
    public void setDeletedAt(LocalDateTime deletedAt) { this.deletedAt = deletedAt; }

    public LocalDateTime getExpiresAt() { return expiresAt; }
    public void setExpiresAt(LocalDateTime expiresAt) { this.expiresAt = expiresAt; }

    public LocalDate getDocEffectiveDate() { return docEffectiveDate; }
    public void setDocEffectiveDate(LocalDate docEffectiveDate) { this.docEffectiveDate = docEffectiveDate; }

    public LocalDate getDocExpiryDate() { return docExpiryDate; }
    public void setDocExpiryDate(LocalDate docExpiryDate) { this.docExpiryDate = docExpiryDate; }

    public String getDocVersion() { return docVersion; }
    public void setDocVersion(String docVersion) { this.docVersion = docVersion; }

    public String getContributorId() { return contributorId; }
    public void setContributorId(String contributorId) { this.contributorId = contributorId; }

    public String getTags() { return tags; }
    public void setTags(String tags) { this.tags = tags; }

    public String getApprovalStatus() { return approvalStatus; }
    public void setApprovalStatus(String approvalStatus) { this.approvalStatus = approvalStatus; }

    public boolean isInheritPermissions() { return inheritPermissions; }
    public void setInheritPermissions(boolean inheritPermissions) { this.inheritPermissions = inheritPermissions; }

    public String getIngestStatus() { return ingestStatus; }
    public void setIngestStatus(String ingestStatus) { this.ingestStatus = ingestStatus; }

    public String getUploadedBy() { return uploadedBy; }
    public void setUploadedBy(String uploadedBy) { this.uploadedBy = uploadedBy; }

    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
