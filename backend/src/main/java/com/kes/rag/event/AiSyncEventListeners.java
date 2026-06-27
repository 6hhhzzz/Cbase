package com.kes.rag.event;

import com.kes.common.event.DocumentPermanentlyDeletedEvent;
import com.kes.common.event.DocumentStatusChangedEvent;
import com.kes.rag.client.AiServiceClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * AI 同步事件监听器。
 * 响应文档状态变更和永久删除事件，同步 Python AI 服务的向量数据。
 * 使用 AFTER_COMMIT 确保 DB 事务成功后调用外部服务。
 */
@Component
public class AiSyncEventListeners {

    private static final Logger log = LoggerFactory.getLogger(AiSyncEventListeners.class);

    private final AiServiceClient aiServiceClient;

    public AiSyncEventListeners(AiServiceClient aiServiceClient) {
        this.aiServiceClient = aiServiceClient;
    }

    @EventListener
    public void onDocumentStatusChanged(DocumentStatusChangedEvent event) {
        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    boolean synced = aiServiceClient.updateDocumentStatus(event.docId(), event.newStatus());
                    if (!synced) {
                        log.warn("文档状态同步到 AI 失败: docId={}, status={}", event.docId(), event.newStatus());
                    }
                }
            }
        );
    }

    @EventListener
    public void onDocumentPermanentlyDeleted(DocumentPermanentlyDeletedEvent event) {
        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    boolean deleted = aiServiceClient.deleteDocumentChunks(event.docId());
                    if (!deleted) {
                        log.warn("AI chunks 删除失败: docId={}", event.docId());
                    }
                }
            }
        );
    }
}
