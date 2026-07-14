package com.kes.rag.client;

import com.kes.rag.model.FilterParams;
import io.netty.handler.timeout.ReadTimeoutHandler;
import io.netty.handler.timeout.WriteTimeoutHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Python AI Service HTTP 客户端 — v3 Space/KB RBAC。
 */
@Service
public class AiServiceClient {

    private final WebClient webClient;

    public AiServiceClient(@Value("${aiservice.base-url}") String baseUrl) {
        HttpClient httpClient = HttpClient.create()
            .responseTimeout(Duration.ofSeconds(120))
            .doOnConnected(conn ->
                conn.addHandlerLast(new ReadTimeoutHandler(120, TimeUnit.SECONDS))
                   .addHandlerLast(new WriteTimeoutHandler(30, TimeUnit.SECONDS)));

        this.webClient = WebClient.builder()
            .baseUrl(baseUrl)
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
    }

    /**
     * 调用 Python POST /v1/chat，返回 SSE 事件流。
     * v4: filter_params 包含 kb_ids + doc_ids（可选文档级过滤）。
     */
    public Flux<String> chat(String query, FilterParams filterParams, String conversationId,
                             List<Map<String, String>> historyMessages, int topK) {

        Map<String, Object> fp = new HashMap<>();
        fp.put("kb_ids", filterParams.kbIds());
        if (filterParams.docIds() != null) {
            fp.put("doc_ids", filterParams.docIds());
        }

        Map<String, Object> body = new HashMap<>();
        body.put("query", query);
        body.put("filter_params", fp);
        body.put("conversation_id", conversationId);
        body.put("history_messages", historyMessages);
        body.put("top_k", topK);

        return webClient.post()
            .uri("/v1/chat")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(body)
            .retrieve()
            .bodyToFlux(String.class);
    }

    /**
     * 同步文档状态到 Python knowledge_chunks 表。
     * 软删除时标记 chunks 为 soft_deleted，恢复时标记为 active。
     *
     * @return true 表示同步成功，false 表示 Python 服务不可达
     */
    public boolean updateDocumentStatus(String docId, String status) {
        try {
            Map<String, String> body = Map.of("doc_id", docId, "status", status);
            webClient.post()
                .uri("/v1/documents/status")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .bodyToMono(Void.class)
                .block(Duration.ofSeconds(10));
            return true;
        } catch (Exception e) {
            log.warn("同步文档状态到 Python 失败: docId={}, status={}, error={}",
                docId, status, e.getMessage());
            return false;
        }
    }

    /**
     * 通知 Python 永久删除文档的向量 chunks。
     *
     * @return true 表示删除成功，false 表示 Python 服务不可达
     */
    public boolean deleteDocumentChunks(String docId) {
        try {
            webClient.delete()
                .uri("/v1/documents/{docId}/chunks", docId)
                .retrieve()
                .bodyToMono(Void.class)
                .block(Duration.ofSeconds(10));
            return true;
        } catch (Exception e) {
            log.warn("通知 Python 删除 chunks 失败: docId={}, error={}",
                docId, e.getMessage());
            return false;
        }
    }

    /**
     * 通知 Python 批量永久删除文档的向量 chunks。
     *
     * @return true 表示删除成功，false 表示 Python 服务不可达
     */
    public boolean batchDeleteDocumentChunks(List<String> docIds) {
        try {
            webClient.post()
                .uri("/v1/documents/batch/chunks/delete")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("doc_ids", docIds))
                .retrieve()
                .bodyToMono(Void.class)
                .block(Duration.ofSeconds(30));
            return true;
        } catch (Exception e) {
            log.warn("通知 Python 批量删除 chunks 失败: count={}, error={}",
                docIds.size(), e.getMessage());
            return false;
        }
    }

    /**
     * v6: 模型连通性测试 — 转发给 Python /v1/admin/models/test。
     */
    public Mono<Map> testModelConnection(Map<String, Object> request) {
        return webClient.post()
            .uri("/v1/admin/models/test")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(Map.class);
    }

    /**
     * v6: 模型发现 — 转发给 Python /v1/admin/models/discover。
     */
    public Mono<Map> discoverModels(Map<String, Object> request) {
        return webClient.post()
            .uri("/v1/admin/models/discover")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(Map.class);
    }

    /**
     * v12: 获取模型配置文件内容 — 代理到 Python GET /v1/admin/models/config。
     */
    public Mono<Map> getModelsConfig() {
        return webClient.get()
            .uri("/v1/admin/models/config")
            .retrieve()
            .bodyToMono(Map.class);
    }

    /**
     * v12: 更新模型配置文件 — 代理到 Python PUT /v1/admin/models/config。
     */
    public Mono<Map> updateModelsConfig(String yamlContent) {
        return webClient.put()
            .uri("/v1/admin/models/config")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("yaml_content", yamlContent))
            .retrieve()
            .bodyToMono(Map.class);
    }

    private static final Logger log = LoggerFactory.getLogger(AiServiceClient.class);
}
