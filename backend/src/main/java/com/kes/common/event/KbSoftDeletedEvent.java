package com.kes.common.event;

/**
 * KB 软删除事件。
 * 由 KbService 发布，DocumentEventListeners 监听处理文档级联操作。
 * 监听器自行查询级联文档数据，避免 KbService 跨模块访问 DocumentMetaRepository。
 */
public record KbSoftDeletedEvent(
    String kbId,
    String spaceId,
    String operatorId,
    String kbName
) {}
