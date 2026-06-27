package com.kes.document.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.kes.document.model.DocumentMeta;
import com.kes.document.repository.DocumentMetaRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * 文档入库回调消费者 — 接收 Python AI Service 的 ETL 完成通知，
 * 更新 document_meta 表的 ingest_status。
 *
 * <p>对应 mq/client.py 中 publish_callback 发布的 document.ingest.callback 消息。
 */
@Service
public class IngestCallbackConsumer {

    private static final Logger log = LoggerFactory.getLogger(IngestCallbackConsumer.class);
    private final ObjectMapper objectMapper;

    private final DocumentMetaRepository docRepo;

    public IngestCallbackConsumer(DocumentMetaRepository docRepo, ObjectMapper objectMapper) {
        this.docRepo = docRepo;
        this.objectMapper = objectMapper;
    }

    /**
     * 消费 Python ETL 完成回调。
     *
     * <p>消息格式 (JSON):
     * <pre>
     * {
     *   "doc_id": "uuid",
     *   "status": "completed" | "failed",
     *   "error_message": "...",
     *   "chunks_created": 5,
     *   "tokens_used": 0
     * }
     * </pre>
     */
    @RabbitListener(
        bindings = @org.springframework.amqp.rabbit.annotation.QueueBinding(
            value = @org.springframework.amqp.rabbit.annotation.Queue(
                value = "document.ingest.callback",
                durable = "true"
            ),
            exchange = @org.springframework.amqp.rabbit.annotation.Exchange(
                value = "kes.document",
                type = "topic",
                durable = "true"
            ),
            key = "document.ingest.callback"
        )
    )
    public void handleCallback(Message message) {
        try {
            // 由 Python aio_pika 发送，body 是 UTF-8 编码的 JSON
            String jsonBody = new String(message.getBody(), StandardCharsets.UTF_8);
            @SuppressWarnings("unchecked")
            Map<String, Object> msg = objectMapper.readValue(jsonBody, Map.class);
            String docId = (String) msg.get("doc_id");
            String status = (String) msg.get("status");
            String errorMsg = (String) msg.get("error_message");
            Integer chunksCreated = (Integer) msg.get("chunks_created");

            if (docId == null) {
                log.warn("收到无效的回调消息: doc_id 为空");
                return;
            }

            DocumentMeta meta = docRepo.findById(docId).orElse(null);
            if (meta == null) {
                log.warn("回调的文档不存在: doc_id={}", docId);
                return;
            }

            meta.setIngestStatus(status != null ? status : "failed");
            docRepo.save(meta);

            if ("completed".equals(status)) {
                log.info("文档入库完成: doc_id={}, file={}, chunks={}",
                    docId, meta.getFilename(), chunksCreated);
            } else {
                log.warn("文档入库失败: doc_id={}, file={}, error={}",
                    docId, meta.getFilename(), errorMsg);
            }

        } catch (Exception e) {
            log.error("处理入库回调消息失败: {}", e.getMessage(), e);
        }
    }
}
