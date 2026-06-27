package com.kes.auth.service;

import com.kes.auth.model.AccessControlEntry;
import com.kes.auth.model.KnowledgeBase;
import com.kes.auth.repository.AceRepository;
import com.kes.auth.repository.KnowledgeBaseRepository;
import com.kes.document.service.DocumentPermissionService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * 权限查询服务 — v4 ACE 模型的核心算法实现。
 *
 * <p>负责计算"用户在某个 Space 中有权访问哪些 KB/文档"。
 * 本服务是纯查询服务，不执行写操作，也不负责权限校验（权限校验由 {@link PermissionService} 负责）。
 *
 * <p>算法概要（KB 级别）：
 * <ol>
 *   <li>全局管理员 → 返回 Space 中所有未删除的 KB</li>
 *   <li>获取用户的有效组列表（含层级展开）</li>
 *   <li>Space 管理员 → 可以看到所有 KB</li>
 *   <li>space_wide KB 自动对 Space 成员可见</li>
 *   <li>查 ACE 表：allow → 加入，deny → 移除（deny 始终覆盖 allow）</li>
 *   <li>Redis 缓存（5min TTL）</li>
 * </ol>
 */
@Service
public class PermissionQueryService {

    private static final Logger log = LoggerFactory.getLogger(PermissionQueryService.class);

    private final KnowledgeBaseRepository kbRepo;
    private final AceRepository aceRepo;
    private final KbPermissionCache permissionCache;
    private final PermissionService permService;
    private final DocumentPermissionService docPermissionService;

    public PermissionQueryService(KnowledgeBaseRepository kbRepo,
                                  AceRepository aceRepo,
                                  KbPermissionCache permissionCache,
                                  PermissionService permService,
                                  DocumentPermissionService docPermissionService) {
        this.kbRepo = kbRepo;
        this.aceRepo = aceRepo;
        this.permissionCache = permissionCache;
        this.permService = permService;
        this.docPermissionService = docPermissionService;
    }

    // ================================================================
    // KB 权限解析
    // ================================================================

    /**
     * 计算用户在当前 Space 中有权访问的所有 KB ID — v4 ACE 模型。
     * 不检查具体权限，返回所有可见 KB（向后兼容）。
     */
    public List<String> resolveAccessibleKbIds(String spaceId, String userId) {
        return resolveAccessibleKbIds(spaceId, userId, null);
    }

    /**
     * 计算用户有指定权限的 KB ID 列表。
     * @param requiredPermission 如 "kb.read"、"kb.write"，为 null 则返回所有可见 KB
     */
    public List<String> resolveAccessibleKbIds(String spaceId, String userId,
                                                String requiredPermission) {
        // 1. 查缓存
        Set<String> cached = permissionCache.get(userId, spaceId);
        if (cached != null) {
            return new ArrayList<>(cached);
        }

        // 2. 全局管理员 → 全量访问
        if (permService.isGlobalAdmin(userId)) {
            List<KnowledgeBase> allKbs = kbRepo.findBySpaceIdAndDeletedAtIsNull(spaceId);
            Set<String> allIds = new LinkedHashSet<>();
            allKbs.forEach(kb -> allIds.add(kb.getId()));
            permissionCache.put(userId, spaceId, allIds);
            return new ArrayList<>(allIds);
        }

        // 3. 获取用户有效组 + Space 准入组交集
        Set<String> userSpaceGroups = permService.getUserSpaceGroups(spaceId, userId);
        boolean isSpaceAdmin = permService.isSpaceAdmin(spaceId, userId);

        // 4. 非 Space 成员 → 空列表
        if (!isSpaceAdmin && userSpaceGroups.isEmpty()) {
            return List.of();
        }

        // 5. 基础可见 KB
        Set<String> result = new LinkedHashSet<>();

        if (isSpaceAdmin) {
            kbRepo.findBySpaceIdAndDeletedAtIsNull(spaceId)
                .forEach(kb -> result.add(kb.getId()));
        }

        // space_wide KB 对所有 Space 成员自动可见
        List<String> spaceWideKbs = kbRepo.findSpaceWideKbIds(spaceId);
        result.addAll(spaceWideKbs);

        // 6. 查询 ACE 表
        if (!userSpaceGroups.isEmpty()) {
            List<AccessControlEntry> groupAces = aceRepo.findKbAcesByPrincipals(
                spaceId, "group", new ArrayList<>(userSpaceGroups));
            applyAceEntries(result, groupAces);

            List<AccessControlEntry> userAces = aceRepo.findKbAcesByPrincipals(
                spaceId, "user", List.of(userId));
            applyAceEntries(result, userAces);
        }

        // 7. 细粒度权限过滤（自定义角色）
        if (requiredPermission != null && !isSpaceAdmin) {
            result.removeIf(kbId ->
                !permService.hasPermission(userId, spaceId, kbId, requiredPermission));
        }

        // 8. 写缓存
        permissionCache.put(userId, spaceId, result);

        log.debug("权限解析 v4: user={}, space={}, required={}, kb_ids={}, isAdmin={}, groups={}",
            userId, spaceId, requiredPermission, result, isSpaceAdmin, userSpaceGroups);
        return new ArrayList<>(result);
    }

    // ================================================================
    // 文档级权限解析（Phase 3）
    // ================================================================

    /**
     * 解析用户对指定 KB 中每个文档的访问权限。
     *
     * @return null 表示无限制（所有文档可见）；否则返回应排除的 doc_id 列表
     */
    public List<String> resolveAccessibleDocIds(String spaceId, String userId, List<String> kbIds) {
        if (kbIds == null || kbIds.isEmpty()) return List.of();

        // 1. Space admin/全局管理员 → 全可见
        if (permService.isGlobalAdmin(userId) || permService.isSpaceAdmin(spaceId, userId)) {
            return null;
        }

        // 2. 通过 DocumentPermissionService 查询自定义权限文档（跨模块通过 Service 门面）
        List<String> customDocIds = docPermissionService.getCustomPermissionDocIds(kbIds);
        if (customDocIds.isEmpty()) {
            return null;
        }

        // 3. 对隔离文档查 document ACE
        Set<String> userSpaceGroups = permService.getUserSpaceGroups(spaceId, userId);
        List<String> groupIds = new ArrayList<>(userSpaceGroups);

        Set<String> deniedDocIds = new LinkedHashSet<>();
        Set<String> allowedDocIds = new LinkedHashSet<>();

        if (!groupIds.isEmpty()) {
            List<AccessControlEntry> groupAces = aceRepo.findDocAcesByPrincipals(spaceId, "group", groupIds);
            for (AccessControlEntry ace : groupAces) {
                if ("deny".equals(ace.getEffect())) {
                    deniedDocIds.add(ace.getResourceId());
                } else {
                    allowedDocIds.add(ace.getResourceId());
                }
            }
        }

        List<AccessControlEntry> userAces = aceRepo.findDocAcesByPrincipals(spaceId, "user", List.of(userId));
        for (AccessControlEntry ace : userAces) {
            if ("deny".equals(ace.getEffect())) {
                deniedDocIds.add(ace.getResourceId());
            } else {
                allowedDocIds.add(ace.getResourceId());
            }
        }

        // 4. 计算排除列表
        Set<String> excludedDocIds = new LinkedHashSet<>();
        for (String docId : customDocIds) {
            if (deniedDocIds.contains(docId)) {
                excludedDocIds.add(docId);
            } else if (!allowedDocIds.contains(docId)) {
                excludedDocIds.add(docId);
            }
        }

        return excludedDocIds.isEmpty() ? null : new ArrayList<>(excludedDocIds);
    }

    // ================================================================
    // KB 信息查询（供 Controller 使用）
    // ================================================================

    /**
     * 计算用户可访问的 KB 列表（含 name/description/visibility 信息）。
     * 替代 Controller 中直接调用 kbRepo.findById() 的模式。
     */
    public List<com.kes.common.dto.SpaceDtos.KbAccessInfo> resolveAccessibleKbInfoList(
            String spaceId, String userId) {
        List<String> kbIds = resolveAccessibleKbIds(spaceId, userId, "kb.read");
        return kbIds.stream()
            .map(kbRepo::findById).filter(Optional::isPresent).map(Optional::get)
            .filter(kb -> kb.getDeletedAt() == null)
            .map(kb -> new com.kes.common.dto.SpaceDtos.KbAccessInfo(
                kb.getId(), kb.getName(),
                kb.getDescription() != null ? kb.getDescription() : "", kb.getVisibility()))
            .toList();
    }

    // ================================================================
    // 内部方法
    // ================================================================

    /**
     * 应用 ACE 条目到结果集。
     * allow → 加入 result，deny → 从 result 中移除。
     * deny 始终覆盖 allow（无论处理顺序）。
     */
    private void applyAceEntries(Set<String> kbIds, List<AccessControlEntry> aces) {
        Set<String> denyKbIds = new LinkedHashSet<>();
        Set<String> allowKbIds = new LinkedHashSet<>();

        for (AccessControlEntry ace : aces) {
            if ("deny".equals(ace.getEffect())) {
                denyKbIds.add(ace.getResourceId());
            } else {
                allowKbIds.add(ace.getResourceId());
            }
        }

        kbIds.addAll(allowKbIds);
        kbIds.removeAll(denyKbIds);
    }
}
