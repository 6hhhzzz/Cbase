package com.kes.rag.controller;

import com.kes.auth.service.FeedbackService;
import com.kes.auth.service.PermissionQueryService;
import com.kes.auth.service.PermissionService;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.model.ApiResponse;
import com.kes.common.util.JwtUtil;
import com.kes.conversation.model.Message;
import com.kes.conversation.service.ConversationService;
import com.kes.rag.client.AiServiceClient;
import com.kes.rag.model.FilterParams;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.*;

/**
 * 问答控制器 — v4 ACE RBAC，支持跨KB联合查询。
 * 从 Context Token 提取 Space ID，通过 {@link PermissionQueryService} 计算用户有权访问的 kb_ids。
 * 支持用户通过 excluded_kb_ids 排除特定 KB。
 */
@RestController
@RequestMapping("/api")
public class ChatController {

    private static final Logger log = LoggerFactory.getLogger(ChatController.class);
    private final ObjectMapper objectMapper;
    private static final int MAX_HISTORY_MESSAGES = 30;

    private final AiServiceClient aiServiceClient;
    private final JwtUtil jwtUtil;
    private final ConversationService conversationService;
    private final PermissionQueryService permissionQueryService;
    private final PermissionService permissionService;
    private final FeedbackService feedbackService;

    public ChatController(AiServiceClient aiServiceClient, JwtUtil jwtUtil,
                          ConversationService conversationService,
                          PermissionQueryService permissionQueryService,
                          PermissionService permissionService,
                          FeedbackService feedbackService,
                          ObjectMapper objectMapper) {
        this.aiServiceClient = aiServiceClient;
        this.jwtUtil = jwtUtil;
        this.conversationService = conversationService;
        this.permissionQueryService = permissionQueryService;
        this.permissionService = permissionService;
        this.feedbackService = feedbackService;
        this.objectMapper = objectMapper;
    }

    @PostMapping("/chat")
    public SseEmitter chat(@RequestBody com.kes.rag.model.ChatRequest req, Authentication auth) {
        String query = req.getQuery();
        String cid = req.getConversationId() != null ? req.getConversationId() : "";
        final String conversationId = cid.isBlank() ? UUID.randomUUID().toString() : cid;

        try {
            UUID.fromString(conversationId);
        } catch (IllegalArgumentException e) {
            throw BusinessException.invalidParameter("conversation_id 格式无效: " + conversationId);
        }

        if (query == null || query.isBlank()) {
            throw BusinessException.invalidParameter("query 为必填项");
        }

        // ---- 1. 从 Context Token 提取上下文 ----
        String token = (String) auth.getCredentials();
        String userId = auth.getName();
        String spaceId = jwtUtil.extractSpaceId(token);

        // 校验 Space 成员身份
        permissionService.requireSpaceMember(spaceId, userId);

        // ---- 2. 计算用户有权读取的 kb_ids ----
        List<String> kbIds = permissionQueryService.resolveAccessibleKbIds(
            spaceId, userId, "kb.read");

        // ---- 3. 处理用户排除的 KB ----
        List<String> excludedKbIds = req.getExcludedKbIds();
        if (excludedKbIds != null && !excludedKbIds.isEmpty()) {
            kbIds = new ArrayList<>(kbIds);
            kbIds.removeAll(excludedKbIds);
            log.info("排除 KB: user={}, excluded={}, remaining={}", userId, excludedKbIds, kbIds);
        }

        if (kbIds.isEmpty()) {
            throw BusinessException.invalidParameter("没有可用的知识库，请检查排除设置或联系管理员");
        }

        log.info("问答请求: user={}, space={}, kb_ids={}, query={}",
            userId, spaceId, kbIds, query.substring(0, Math.min(50, query.length())));

        // ---- 4. 从 PG 读取历史消息 ----
        List<Map<String, String>> historyMessages = new ArrayList<>();
        try {
            List<Message> dbMessages = conversationService.getMessages(conversationId);
            int start = Math.max(0, dbMessages.size() - MAX_HISTORY_MESSAGES);
            for (int i = start; i < dbMessages.size(); i++) {
                Message msg = dbMessages.get(i);
                String msgRole = msg.getRole();
                if ("user".equals(msgRole) || "assistant".equals(msgRole)) {
                    Map<String, String> m = new HashMap<>();
                    m.put("role", msgRole);
                    m.put("content", msg.getContent());
                    historyMessages.add(m);
                }
            }
        } catch (Exception e) {
            log.warn("读取历史消息失败（非致命）: {}", e.getMessage());
        }

        // ---- 5. 创建/获取会话 + 保存用户消息 ----
        String convKbId = req.getKbId() != null && !req.getKbId().isBlank()
            ? req.getKbId()
            : null;
        try {
            conversationService.getOrCreateConversation(conversationId, userId, query, convKbId, spaceId);
            conversationService.saveMessage(conversationId, "user", query, null);
        } catch (Exception e) {
            log.error("保存会话/用户消息失败: {}", e.getMessage(), e);
        }

        // ---- 6. 文档级权限解析（Phase 3） ----
        List<String> docIds = permissionQueryService.resolveAccessibleDocIds(spaceId, userId, kbIds);

        // ---- 7. 构建 FilterParams ----
        FilterParams filterParams = new FilterParams(kbIds, docIds);

        // ---- 8. 调用 Python AI Service (SSE 流) ----
        final StringBuilder fullContent = new StringBuilder();
        final String[] sourcesHolder = new String[1];

        SseEmitter emitter = new SseEmitter(120_000L);
        emitter.onTimeout(() -> log.warn("SSE 超时 (120s): conv={}", conversationId));
        emitter.onError(err -> log.error("SSE 异常: conv={}, error={}", conversationId, err.getMessage()));

        aiServiceClient.chat(query, filterParams, conversationId, historyMessages, 5)
            .publishOn(reactor.core.scheduler.Schedulers.boundedElastic())
            .subscribe(
                data -> handleSseData(emitter, data, fullContent, sourcesHolder),
                error -> handleSseError(emitter, error, conversationId, fullContent, sourcesHolder),
                () -> handleSseComplete(emitter, conversationId, fullContent, sourcesHolder)
            );

        return emitter;
    }

    // ---- SSE 回调处理 ----

    private void handleSseData(SseEmitter emitter, String data,
                                StringBuilder content, String[] sources) {
        try {
            String jsonStr = data.startsWith("data: ") ? data.substring(6).trim() : data.trim();
            try {
                Map<String, Object> chunk = objectMapper.readValue(jsonStr, Map.class);
                if (chunk.get("token") instanceof String t && !t.isEmpty()) content.append(t);
                if (Boolean.TRUE.equals(chunk.get("done")) && chunk.get("sources") != null)
                    sources[0] = objectMapper.writeValueAsString(chunk.get("sources"));
            } catch (Exception e) {
                log.debug("SSE chunk 非 JSON 数据");
            }
            emitter.send(SseEmitter.event().name("message").data(jsonStr, MediaType.APPLICATION_JSON));
        } catch (Exception e) {
            log.error("SSE 发送失败: {}", e.getMessage());
            emitter.completeWithError(e);
        }
    }

    private void handleSseError(SseEmitter emitter, Throwable error, String convId,
                                 StringBuilder content, String[] sources) {
        log.error("Python AI Service 调用失败: {}", error.getMessage());
        String finalContent = content != null && content.length() > 0
            ? content.toString()
            : "抱歉，AI 服务暂不可用，请稍后重试。";
        saveAssistantMessage(convId, finalContent, sources[0]);
        try {
            emitter.send(SseEmitter.event().name("message")
                .data("{\"token\":\"\",\"done\":true,\"sources\":" +
                      (sources[0] != null ? sources[0] : "[]") + "}", MediaType.APPLICATION_JSON));
            emitter.complete();
        } catch (Exception ex) {
            emitter.completeWithError(ex);
        }
    }

    private void handleSseComplete(SseEmitter emitter, String convId,
                                    StringBuilder content, String[] sources) {
        log.info("问答完成: conv={}", convId);
        String finalContent = content != null ? content.toString() : "";
        // 检测空响应：如果 LLM 未返回任何 token（可能在 Python 端已插入错误信息），
        // 保存消息时允许空内容的错误提示通过
        saveAssistantMessage(convId, finalContent, sources[0]);
        // 如果确实是空响应，在完成前发送一条错误提示
        if (finalContent.isEmpty()) {
            log.warn("assistant 回复为空: conv={}", convId);
            try {
                emitter.send(SseEmitter.event().name("message")
                    .data("{\"token\":\"抱歉，AI 服务响应为空，请检查 API Key 配置或稍后重试。\",\"done\":true,\"sources\":[]}",
                          MediaType.APPLICATION_JSON));
            } catch (Exception e) {
                log.error("发送空响应错误提示失败: {}", e.getMessage());
            }
        }
        emitter.complete();
    }

    private void saveAssistantMessage(String conversationId, String content, String sources) {
        if (content == null || content.isEmpty()) {
            // 保存错误提示作为 assistant 消息，让用户能看到错误信息
            content = "抱歉，AI 服务暂不可用。";
        }
        try {
            conversationService.saveMessage(conversationId, "assistant", content, sources);
            log.info("assistant 消息已保存: conv={}, length={}", conversationId, content.length());
        } catch (Exception e) {
            log.error("保存 assistant 消息失败: conv={}, error={}", conversationId, e.getMessage());
        }
    }

    /** 提交检索质量反馈（点赞/点踩） */
    @PostMapping("/chat/feedback")
    public ApiResponse<?> submitFeedback(@RequestBody Map<String, String> body) {
        String traceId = body.get("trace_id");
        String rating = body.get("rating");
        String reason = body.getOrDefault("reason", "");

        if (traceId == null || traceId.isBlank()) {
            return ApiResponse.error(ErrorCode.INVALID_REQUEST, "trace_id 不能为空");
        }
        if (!"like".equals(rating) && !"dislike".equals(rating)) {
            return ApiResponse.error(ErrorCode.INVALID_REQUEST, "rating 必须为 'like' 或 'dislike'");
        }

        feedbackService.submitFeedback(traceId, rating, reason);
        return ApiResponse.success(Map.of("status", "ok"));
    }
}
