package com.kes.document.model;

import java.time.LocalDateTime;

/**
 * 审批列表项 DTO — 聚合审批记录与文档元数据，供前端审批页面使用。
 *
 * <p>Jackson SNAKE_CASE 序列化:
 * approvalId → approval_id, documentId → document_id, fileType → file_type,
 * submittedBy → submitted_by (display_name from users table), submittedAt → submitted_at,
 * actionType → action_type
 */
public record ApprovalItem(
    String approvalId,
    String documentId,
    String filename,
    String fileType,
    String submittedBy,
    LocalDateTime submittedAt,
    String status,
    String actionType
) {}
