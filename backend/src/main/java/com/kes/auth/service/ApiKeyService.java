package com.kes.auth.service;

import com.kes.auth.model.ApiKey;
import com.kes.auth.repository.ApiKeyRepository;
import com.kes.auth.repository.UserRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.service.AuditLogger;
import com.kes.common.util.JwtUtil;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.*;

/**
 * MCP API 密钥服务 — 用户自助管理，用于外部 Agent 接入。
 */
@Service
public class ApiKeyService {

    private static final Logger log = LoggerFactory.getLogger(ApiKeyService.class);
    private static final String KEY_PREFIX = "kes_mcp_";
    private static final SecureRandom RNG = new SecureRandom();

    private final ApiKeyRepository apiKeyRepo;
    private final UserRepository userRepo;
    private final JwtUtil jwtUtil;
    private final AuditLogger auditLogger;
    private final PermissionQueryService permissionQueryService;

    public ApiKeyService(ApiKeyRepository apiKeyRepo, UserRepository userRepo,
                         JwtUtil jwtUtil, AuditLogger auditLogger,
                         PermissionQueryService permissionQueryService) {
        this.apiKeyRepo = apiKeyRepo;
        this.userRepo = userRepo;
        this.jwtUtil = jwtUtil;
        this.auditLogger = auditLogger;
        this.permissionQueryService = permissionQueryService;
    }

    /** 创建密钥。scopeKbIds 为 null 表示继承用户完整权限。scope 必须在创建者当前权限范围内。 */
    @Transactional
    public CreatedKey createKey(String userId, String spaceId, String name,
                                 int expiresDays, List<String> scopeKbIds) {
        if (apiKeyRepo.existsByUserIdAndName(userId, name)) {
            throw new BusinessException(ErrorCode.API_KEY_NAME_CONFLICT);
        }

        // 校验 scope ⊆ 创建者当前 ACE 权限
        validateScope(userId, spaceId, scopeKbIds);

        String rawKey = generateRawKey();
        String keyHash = sha256(rawKey);
        String keyPrefix = rawKey.substring(0, 15);

        ApiKey entity = new ApiKey(
            UUID.randomUUID().toString(), userId, name, keyHash, keyPrefix,
            LocalDateTime.now().plusDays(expiresDays)
        );
        if (scopeKbIds != null && !scopeKbIds.isEmpty()) {
            entity.setScopeKbIds(toJsonString(scopeKbIds));
        }
        apiKeyRepo.save(entity);
        log.info("API 密钥已创建: userId={}, name={}, prefix={}, scope={}",
            userId, name, keyPrefix, entity.getScopeKbIds());

        String details = "expires_days=" + expiresDays;
        if (entity.getScopeKbIds() != null) {
            details += " scope=" + entity.getScopeKbIds();
        }
        auditLogger.log(userId, null, "api_key.create", "api_key",
            entity.getId(), name, details);

        return new CreatedKey(entity, rawKey);
    }

    /** 列出用户的所有密钥。 */
    public List<ApiKey> listKeys(String userId) {
        return apiKeyRepo.findByUserIdOrderByCreatedAtDesc(userId);
    }

    /** 重命名密钥。 */
    @Transactional
    public void renameKey(String userId, String keyId, String newName) {
        ApiKey key = getOwnedKey(userId, keyId);

        // 检查同名（排除自身）
        if (!key.getName().equals(newName) && apiKeyRepo.existsByUserIdAndName(userId, newName)) {
            throw new BusinessException(ErrorCode.API_KEY_NAME_CONFLICT);
        }

        String oldName = key.getName();
        key.setName(newName);
        apiKeyRepo.save(key);
        log.info("API 密钥已重命名: userId={}, {} -> {}", userId, oldName, newName);

        auditLogger.log(userId, null, "api_key.rename", "api_key",
            keyId, newName, "old_name=" + oldName);
    }

    /** 撤销密钥。已撤销的密钥不可再次撤销。 */
    @Transactional
    public void revokeKey(String userId, String keyId) {
        ApiKey key = getOwnedKey(userId, keyId);
        if (key.isRevoked()) {
            throw new BusinessException(ErrorCode.API_KEY_REVOKED);
        }

        key.setRevokedAt(LocalDateTime.now());
        apiKeyRepo.save(key);
        log.info("API 密钥已撤销: userId={}, prefix={}, name={}",
            userId, key.getKeyPrefix(), key.getName());

        auditLogger.log(userId, null, "api_key.revoke", "api_key",
            keyId, key.getName(), null);
    }

    /** 延期密钥有效期。已撤销的不可延期，已过期但未撤销的可延期。 */
    @Transactional
    public ExtendResult extendKey(String userId, String keyId, int expiresDays) {
        ApiKey key = getOwnedKey(userId, keyId);
        if (key.isRevoked()) {
            throw new BusinessException(ErrorCode.API_KEY_REVOKED, "已撤销的密钥无法延期");
        }

        LocalDateTime oldExpiry = key.getExpiresAt();
        LocalDateTime newExpiry = LocalDateTime.now().plusDays(expiresDays);
        key.setExpiresAt(newExpiry);
        apiKeyRepo.save(key);

        log.info("API 密钥已延期: userId={}, name={}, {} -> {}",
            userId, key.getName(), oldExpiry, newExpiry);

        auditLogger.log(userId, null, "api_key.extend", "api_key",
            keyId, key.getName(),
            "expires_days=" + expiresDays + " old=" + oldExpiry + " new=" + newExpiry);

        return new ExtendResult(key.getId(), key.getName(), newExpiry);
    }

    /** 修改密钥的 KB 范围。已撤销的不可修改。scope 必须在创建者当前权限范围内。 */
    @Transactional
    public void updateScope(String userId, String spaceId, String keyId,
                             List<String> scopeKbIds) {
        ApiKey key = getOwnedKey(userId, keyId);
        if (key.isRevoked()) {
            throw new BusinessException(ErrorCode.API_KEY_REVOKED, "已撤销的密钥无法修改范围");
        }

        // 校验 scope ⊆ 创建者当前 ACE 权限
        validateScope(userId, spaceId, scopeKbIds);

        String oldScope = key.getScopeKbIds();
        key.setScopeKbIds(scopeKbIds != null && !scopeKbIds.isEmpty()
            ? toJsonString(scopeKbIds) : null);
        apiKeyRepo.save(key);

        log.info("API 密钥范围已更新: userId={}, name={}, {} -> {}",
            userId, key.getName(), oldScope, key.getScopeKbIds());

        auditLogger.log(userId, null, "api_key.update_scope", "api_key",
            keyId, key.getName(), "old=" + oldScope + " new=" + key.getScopeKbIds());
    }

    /** 校验 scopeKbIds 必须是用户当前 ACE 权限的子集。 */
    private void validateScope(String userId, String spaceId, List<String> scopeKbIds) {
        if (scopeKbIds == null || scopeKbIds.isEmpty()) {
            return; // null 表示无限制，不需要校验
        }
        List<String> aceKbIds = permissionQueryService.resolveAccessibleKbIds(spaceId, userId);
        Set<String> aceSet = new HashSet<>(aceKbIds);
        List<String> invalid = scopeKbIds.stream()
            .filter(kb -> !aceSet.contains(kb))
            .toList();
        if (!invalid.isEmpty()) {
            throw new BusinessException(ErrorCode.KB_ACCESS_DENIED,
                "以下知识库不在你的权限范围内，无法用于限定 Key 范围: " + String.join(", ", invalid));
        }
    }

    /** API Key → 签发 context_token + refresh_token + scope_kb_ids。 */
    public ExchangeResult exchange(String rawKey, String spaceId) {
        String hash = sha256(rawKey);
        ApiKey key = apiKeyRepo.findByKeyHash(hash)
            .orElseThrow(() -> new BusinessException(ErrorCode.API_KEY_NOT_FOUND, "无效的 API 密钥"));
        if (!key.isValid()) {
            throw new BusinessException(
                key.isRevoked() ? ErrorCode.API_KEY_REVOKED : ErrorCode.API_KEY_EXPIRED);
        }
        key.setLastUsedAt(LocalDateTime.now());
        apiKeyRepo.save(key);

        String userId = key.getUserId();
        var user = userRepo.findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        String contextToken = jwtUtil.generateContextToken(
            userId, user.getUsername(), spaceId, "member");
        String refreshToken = jwtUtil.generateRefreshToken(userId);
        log.info("MCP Token 交换成功: userId={}, spaceId={}, scope={}",
            userId, spaceId, key.getScopeKbIds());
        return new ExchangeResult(contextToken, refreshToken, key.getScopeKbIds());
    }

    // ---- 私有辅助 ----

    /** 查询密钥并校验所有权。 */
    private ApiKey getOwnedKey(String userId, String keyId) {
        ApiKey key = apiKeyRepo.findById(keyId)
            .orElseThrow(() -> new BusinessException(ErrorCode.API_KEY_NOT_FOUND, "密钥不存在"));
        if (!key.getUserId().equals(userId)) {
            throw new BusinessException(ErrorCode.API_KEY_UNAUTHORIZED);
        }
        return key;
    }

    private String generateRawKey() {
        StringBuilder sb = new StringBuilder(KEY_PREFIX);
        for (int i = 0; i < 24; i++) {
            sb.append("abcdefghjkmnpqrstuvwxyz23456789".charAt(
                RNG.nextInt(30)));
        }
        return sb.toString();
    }

    private static String sha256(String input) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] hash = md.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder();
            for (byte b : hash) hex.append(String.format("%02x", b));
            return hex.toString();
        } catch (Exception e) {
            throw new RuntimeException("SHA-256 不可用", e);
        }
    }

    /** 将 List 序列化为 JSON 数组字符串，用于存入 JSONB 列。 */
    private static String toJsonString(List<String> items) {
        if (items == null || items.isEmpty()) return null;
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < items.size(); i++) {
            if (i > 0) sb.append(", ");
            sb.append("\"").append(items.get(i).replace("\"", "\\\"")).append("\"");
        }
        sb.append("]");
        return sb.toString();
    }

    // ---- 内部 DTO ----

    public record CreatedKey(ApiKey entity, String rawKey) {}

    public record ExchangeResult(String contextToken, String refreshToken, String scopeKbIds) {}

    public record ExtendResult(String keyId, String name, LocalDateTime newExpiresAt) {}
}
