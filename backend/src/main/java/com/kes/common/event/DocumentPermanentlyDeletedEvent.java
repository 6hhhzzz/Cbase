package com.kes.common.event;

/**
 * 文档永久删除事件。
 * 由 DocumentService 发布，AiSyncEventListeners 处理向量数据删除，
 * KbCleanupEventListeners 处理 ACE 条目清理。
 */
public record DocumentPermanentlyDeletedEvent(
    String docId,
    String kbId
) {}
