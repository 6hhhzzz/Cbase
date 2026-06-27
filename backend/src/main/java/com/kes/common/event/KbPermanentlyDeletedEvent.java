package com.kes.common.event;

/**
 * KB 永久删除事件。
 * 由 KbService 发布，DocumentEventListeners 处理 MinIO 文件删除 + DB 清理，
 * KbCleanupEventListeners 处理 ACE 条目清理。
 * 监听器自行查询需要清理的文档和文件路径，避免 KbService 跨模块访问 DocumentMetaRepository。
 */
public record KbPermanentlyDeletedEvent(
    String kbId,
    String spaceId,
    String operatorId,
    String kbName
) {}
