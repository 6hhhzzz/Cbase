package com.kes.common.event;

/**
 * 文档状态变更事件。
 * 由 DocumentService 发布，AiSyncEventListeners 监听同步 Python AI 服务。
 */
public record DocumentStatusChangedEvent(
    String docId,
    String kbId,
    String newStatus
) {}
