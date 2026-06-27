package com.kes.auth.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.util.Set;
import java.util.concurrent.TimeUnit;

/**
 * kb_ids 权限缓存 — v4 ACE 权限模型。
 *
 * <p>缓存策略：
 * <ul>
 *   <li>kb_ids:  kes:user:{userId}:kb_ids:{spaceId} (Set, TTL 300s)</li>
 *   <li>groups:  kes:user:{userId}:effective_groups (Set, TTL 600s)</li>
 *   <li>索引:    kes:space:{spaceId}:user_ids (Set, TTL 300s)</li>
 * </ul>
 *
 * <p>失效触发：Space 准入组变更、ACE 变更、组成员变更、管理员变更。
 */
@Component
public class KbPermissionCache {

    private static final Logger log = LoggerFactory.getLogger(KbPermissionCache.class);
    private static final String KEY_PREFIX = "kes:user:";
    private static final String USER_SET_PREFIX = "kes:space:";
    private static final String USER_SET_SUFFIX = ":user_ids";
    private static final String GROUP_SUFFIX = ":effective_groups";
    private static final int KB_TTL_SECONDS = 300;    // 5 分钟
    private static final int GROUP_TTL_SECONDS = 600; // 10 分钟

    private final StringRedisTemplate redis;

    public KbPermissionCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // ---- kb_ids 缓存 ----

    /** 读取缓存的 kb_ids */
    public Set<String> get(String userId, String spaceId) {
        String key = kbIdsKey(userId, spaceId);
        Set<String> result = redis.opsForSet().members(key);
        if (result != null && !result.isEmpty()) {
            log.debug("kb_ids 缓存命中: {}", key);
            return result;
        }
        return null;
    }

    /** 写入 kb_ids 缓存 */
    public void put(String userId, String spaceId, Set<String> kbIds) {
        if (kbIds == null || kbIds.isEmpty()) return;
        String key = kbIdsKey(userId, spaceId);
        redis.opsForSet().add(key, kbIds.toArray(new String[0]));
        redis.expire(key, KB_TTL_SECONDS, TimeUnit.SECONDS);
        redis.opsForSet().add(userSetKey(spaceId), userId);
        redis.expire(userSetKey(spaceId), KB_TTL_SECONDS, TimeUnit.SECONDS);
        log.debug("kb_ids 缓存写入: {}, count={}", key, kbIds.size());
    }

    /** 按用户+Space 清除 kb_ids 缓存 */
    public void evict(String userId, String spaceId) {
        redis.delete(kbIdsKey(userId, spaceId));
        log.debug("kb_ids 缓存清除: user={}, space={}", userId, spaceId);
    }

    /** 按 Space 清除所有用户的 kb_ids 缓存 */
    public void evictBySpace(String spaceId) {
        Set<String> userIds = redis.opsForSet().members(userSetKey(spaceId));
        if (userIds != null) {
            for (String uid : userIds) {
                redis.delete(kbIdsKey(uid, spaceId));
            }
        }
        redis.delete(userSetKey(spaceId));
        log.debug("kb_ids 缓存按 Space 清除: space={}, users={}", spaceId,
            userIds != null ? userIds.size() : 0);
    }

    // ---- effective_groups 缓存 ----

    /** 读取用户的有效组缓存 */
    public Set<String> getEffectiveGroups(String userId) {
        String key = effectiveGroupsKey(userId);
        Set<String> result = redis.opsForSet().members(key);
        if (result != null && !result.isEmpty()) {
            log.debug("effective_groups 缓存命中: user={}", userId);
            return result;
        }
        return null;
    }

    /** 写入用户的有效组缓存 */
    public void putEffectiveGroups(String userId, Set<String> groupIds) {
        if (groupIds == null || groupIds.isEmpty()) return;
        String key = effectiveGroupsKey(userId);
        redis.opsForSet().add(key, groupIds.toArray(new String[0]));
        redis.expire(key, GROUP_TTL_SECONDS, TimeUnit.SECONDS);
    }

    /** 清除用户的有效组缓存 */
    public void evictEffectiveGroups(String userId) {
        redis.delete(effectiveGroupsKey(userId));
    }

    // ---- Key 生成 ----

    private static String kbIdsKey(String userId, String spaceId) {
        return KEY_PREFIX + userId + ":kb_ids:" + spaceId;
    }

    private static String effectiveGroupsKey(String userId) {
        return KEY_PREFIX + userId + GROUP_SUFFIX;
    }

    private static String userSetKey(String spaceId) {
        return USER_SET_PREFIX + spaceId + USER_SET_SUFFIX;
    }
}
