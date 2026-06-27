package com.kes.auth.controller;

import com.kes.auth.model.ApiKey;
import com.kes.auth.service.ApiKeyService;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.model.ApiResponse;
import com.kes.common.util.ControllerAuthHelper;
import org.springframework.web.bind.annotation.*;

import java.util.*;

/**
 * MCP API 密钥管理 — 用户自助 CRUD + Token 交换。
 */
@RestController
@RequestMapping("/api/auth/mcp")
public class ApiKeyController {

    private final ApiKeyService apiKeyService;
    private final ControllerAuthHelper authHelper;

    public ApiKeyController(ApiKeyService apiKeyService,
                            ControllerAuthHelper authHelper) {
        this.apiKeyService = apiKeyService;
        this.authHelper = authHelper;
    }

    /** 列出当前用户的所有密钥 */
    @GetMapping("/keys")
    public ApiResponse<List<Map<String, Object>>> listKeys(
            @RequestHeader("Authorization") String authHeader) {
        String userId = extractUserId(authHeader);
        List<ApiKey> keys = apiKeyService.listKeys(userId);
        return ApiResponse.success(keys.stream().map(k -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", k.getId());
            m.put("name", k.getName());
            m.put("key_prefix", k.getKeyPrefix());
            m.put("expires_at", k.getExpiresAt());
            m.put("expired", k.isExpired());
            m.put("last_used_at", k.getLastUsedAt());
            m.put("created_at", k.getCreatedAt());
            m.put("revoked", k.isRevoked());
            m.put("scope_kb_ids", k.getScopeKbIds());
            return m;
        }).toList());
    }

    /** 创建密钥 */
    @PostMapping("/keys")
    public ApiResponse<Map<String, Object>> createKey(
            @RequestHeader("Authorization") String authHeader,
            @RequestBody Map<String, Object> body) {
        String userId = extractUserId(authHeader);
        String name = (String) body.getOrDefault("name", "MCP Agent");
        int expiresDays = body.containsKey("expires_days")
            ? ((Number) body.get("expires_days")).intValue() : 36500;

        String spaceId = extractSpaceId(authHeader);

        @SuppressWarnings("unchecked")
        List<String> scopeKbIds = (List<String>) body.get("scope_kb_ids");

        var created = apiKeyService.createKey(userId, spaceId, name, expiresDays, scopeKbIds);
        ApiKey key = created.entity();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", key.getId());
        result.put("name", key.getName());
        result.put("api_key", created.rawKey());  // 完整密钥，仅此一次
        result.put("key_prefix", key.getKeyPrefix());
        result.put("expires_at", key.getExpiresAt());
        result.put("expired", false);
        result.put("created_at", key.getCreatedAt());
        result.put("scope_kb_ids", key.getScopeKbIds());
        return ApiResponse.success(result);
    }

    /** 重命名密钥 */
    @PutMapping("/keys/{keyId}")
    public ApiResponse<?> renameKey(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String keyId,
            @RequestBody Map<String, String> body) {
        String userId = extractUserId(authHeader);
        apiKeyService.renameKey(userId, keyId, body.get("name"));
        return ApiResponse.success();
    }

    /** 撤销密钥 */
    @DeleteMapping("/keys/{keyId}")
    public ApiResponse<?> revokeKey(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String keyId) {
        String userId = extractUserId(authHeader);
        apiKeyService.revokeKey(userId, keyId);
        return ApiResponse.success(Map.of("message", "密钥已撤销"));
    }

    /** 延期密钥有效期 */
    @PostMapping("/keys/{keyId}/extend")
    public ApiResponse<Map<String, Object>> extendKey(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String keyId,
            @RequestBody Map<String, Object> body) {
        String userId = extractUserId(authHeader);
        int expiresDays = body.containsKey("expires_days")
            ? ((Number) body.get("expires_days")).intValue() : 36500;

        var result = apiKeyService.extendKey(userId, keyId, expiresDays);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("key_id", result.keyId());
        data.put("name", result.name());
        data.put("expires_at", result.newExpiresAt());
        return ApiResponse.success(data);
    }

    /** 修改密钥 KB 范围 */
    @PutMapping("/keys/{keyId}/scope")
    public ApiResponse<?> updateScope(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String keyId,
            @RequestBody Map<String, Object> body) {
        String userId = extractUserId(authHeader);
        String spaceId = extractSpaceId(authHeader);
        @SuppressWarnings("unchecked")
        List<String> scopeKbIds = (List<String>) body.get("scope_kb_ids");
        apiKeyService.updateScope(userId, spaceId, keyId, scopeKbIds);
        return ApiResponse.success(Map.of("message", "KB 范围已更新"));
    }

    /** API Key → context_token 交换（无需登录态，用 api_key 自身鉴权） */
    @PostMapping("/exchange")
    public ApiResponse<Map<String, Object>> exchange(
            @RequestBody Map<String, String> body) {
        String apiKey = body.get("api_key");
        String spaceId = body.get("space_id");
        if (apiKey == null || apiKey.isBlank()) {
            throw new BusinessException(ErrorCode.PARAM_MISSING, "api_key 不能为空");
        }
        if (spaceId == null || spaceId.isBlank()) {
            throw new BusinessException(ErrorCode.PARAM_MISSING, "space_id 不能为空");
        }

        var result = apiKeyService.exchange(apiKey, spaceId);
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("context_token", result.contextToken());
        data.put("refresh_token", result.refreshToken());
        data.put("scope_kb_ids", result.scopeKbIds());
        return ApiResponse.success(data);
    }

    private String extractUserId(String authHeader) {
        return authHelper.extractUserId(authHeader);
    }

    private String extractSpaceId(String authHeader) {
        return authHelper.extractSpaceId(authHeader);
    }
}
