package com.kes.common.event;

/**
 * KB 恢复事件。
 * 由 KbService 发布，DocumentEventListeners 监听处理文档恢复操作。
 * 监听器自行查询级联文档数据，避免 KbService 跨模块访问 DocumentMetaRepository。
 */
public record KbRestoredEvent(
    String kbId,
    String spaceId,
    String operatorId,
    String kbName
) {}
