package com.kes.conversation.controller;

import com.kes.auth.service.PermissionService;
import com.kes.common.model.ApiResponse;
import com.kes.common.util.JwtUtil;
import com.kes.conversation.model.Conversation;
import com.kes.conversation.model.Message;
import com.kes.conversation.service.ConversationService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 会话控制器 — v3.1 Space/KB 隔离，支持跨KB联合查询。
 */
@RestController
@RequestMapping("/api/conversations")
public class ConversationController {

    private final ConversationService conversationService;
    private final JwtUtil jwtUtil;
    private final PermissionService permissionService;

    public ConversationController(ConversationService conversationService, JwtUtil jwtUtil,
                                   PermissionService permissionService) {
        this.conversationService = conversationService;
        this.jwtUtil = jwtUtil;
        this.permissionService = permissionService;
    }

    /** v3.1: 查询当前用户在指定 Space 中的会话列表（kb_id 变为可选） */
    @GetMapping
    public ApiResponse<Map<String, Object>> list(
            @RequestParam(value = "kb_id", required = false) String kbId,
            Authentication auth) {
        String token = (String) auth.getCredentials();
        String userId = auth.getName();
        String spaceId = jwtUtil.extractSpaceId(token);
        permissionService.requireSpaceMember(spaceId, userId);
        List<Conversation> convs;
        if (kbId != null && !kbId.isBlank()) {
            // 按 KB 过滤（兼容旧前端）
            convs = conversationService.listConversations(auth.getName(), kbId);
        } else {
            // 默认按 Space 过滤
            convs = conversationService.listConversationsBySpace(auth.getName(), spaceId);
        }
        return ApiResponse.success(Map.of("items", convs));
    }

    @GetMapping("/{convId}/messages")
    public ApiResponse<Map<String, Object>> messages(@PathVariable String convId) {
        List<Message> msgs = conversationService.getMessages(convId);
        return ApiResponse.success(Map.of("items", msgs));
    }

    @DeleteMapping("/{convId}")
    public ApiResponse<Void> delete(@PathVariable String convId, Authentication auth) {
        conversationService.deleteConversation(convId, auth.getName());
        return ApiResponse.success();
    }
}
