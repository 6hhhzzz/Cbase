package com.kes.auth.service;

import com.kes.auth.model.GroupAdmin;
import com.kes.auth.model.UserGroup;
import com.kes.auth.model.UserGroupMember;
import com.kes.auth.repository.GroupAdminRepository;
import com.kes.auth.repository.UserGroupMemberRepository;
import com.kes.auth.repository.UserGroupRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;

/**
 * 用户组层级服务 — BFS/DFS 遍历 + 嵌套路径创建。
 *
 * 从 GroupService 提取，专注于：
 *   - 用户有效组展开（含祖先上溯）
 *   - 组成员递归展开（含子组）
 *   - 祖先/子孙遍历
 *   - 按路径逐级创建嵌套组（★ v9 企业同步核心方法）
 */
@Service
public class GroupHierarchyService {

    private static final Logger log = LoggerFactory.getLogger(GroupHierarchyService.class);

    private final UserGroupRepository groupRepo;
    private final UserGroupMemberRepository memberRepo;
    private final GroupAdminRepository groupAdminRepo;

    public GroupHierarchyService(UserGroupRepository groupRepo,
                                  UserGroupMemberRepository memberRepo,
                                  GroupAdminRepository groupAdminRepo) {
        this.groupRepo = groupRepo;
        this.memberRepo = memberRepo;
        this.groupAdminRepo = groupAdminRepo;
    }

    // ============================================================
    // 成员展开（含嵌套子组）
    // ============================================================

    /** 获取组的所有成员（直接 + 嵌套子组成员展开） */
    public Set<String> getExpandedMemberUserIds(String groupId) {
        Set<String> userIds = new HashSet<>();
        Set<String> visitedGroups = new HashSet<>();
        collectMembersRecursive(groupId, userIds, visitedGroups);
        return userIds;
    }

    private void collectMembersRecursive(String groupId, Set<String> userIds, Set<String> visitedGroups) {
        if (!visitedGroups.add(groupId)) return;
        memberRepo.findByGroupId(groupId).forEach(m -> userIds.add(m.getUserId()));
        groupRepo.findByParentGroupId(groupId).forEach(child ->
            collectMembersRecursive(child.getId(), userIds, visitedGroups));
    }

    // ============================================================
    // 用户有效组展开（含祖先上溯）
    // ============================================================

    /**
     * 展开用户的有效组（直接归属 + 递归上溯所有祖先）。
     *
     * 例：用户在"后端架构组"(parent=研发部, parent=公司全员)
     *     → effectiveGroups = [后端架构组, 研发部, 公司全员]
     */
    public Set<String> expandUserEffectiveGroups(String userId) {
        Set<String> result = new LinkedHashSet<>();
        Deque<String> queue = new ArrayDeque<>();

        List<String> directGroups = memberRepo.findGroupIdsByUserId(userId);
        for (String gid : directGroups) {
            if (result.add(gid)) {
                queue.add(gid);
            }
        }

        while (!queue.isEmpty()) {
            String gid = queue.poll();
            groupRepo.findParentId(gid).ifPresent(parentId -> {
                if (result.add(parentId)) {
                    queue.add(parentId);
                }
            });
        }

        return result;
    }

    /**
     * 展开指定组的所有祖先（不含自身）。
     */
    public Set<String> expandAncestors(String groupId) {
        Set<String> ancestors = new LinkedHashSet<>();
        String current = groupId;
        while (true) {
            Optional<String> parent = groupRepo.findParentId(current);
            if (parent.isEmpty()) break;
            if (!ancestors.add(parent.get())) break;
            current = parent.get();
        }
        return ancestors;
    }

    /**
     * 获取指定组的所有子孙组 ID（递归向下展开）。
     */
    public Set<String> expandDescendants(String groupId) {
        Set<String> result = new LinkedHashSet<>();
        Deque<String> queue = new ArrayDeque<>();
        queue.add(groupId);
        while (!queue.isEmpty()) {
            String gid = queue.poll();
            List<UserGroup> children = groupRepo.findByParentGroupId(gid);
            for (UserGroup child : children) {
                if (result.add(child.getId())) {
                    queue.add(child.getId());
                }
            }
        }
        return result;
    }

    // ============================================================
    // 嵌套建组 — ★ v9 企业同步核心方法
    // ============================================================

    /**
     * 按路径逐级查找或创建嵌套用户组。
     *
     * <p>输入斜杠分隔的组路径，逐级查找已有组；不存在的自动创建并链入父组。
     * CSV 导入、LDAP/AD 同步、Keycloak/OIDC 组映射均复用此方法。
     *
     * @param path      组路径，斜杠分隔，如 "公司/技术中心/后端组"
     * @param createdBy 操作人 userId
     * @return 叶子组 ID（路径最后一级的组）
     */
    @Transactional
    public String findOrCreateGroupPath(String path, String createdBy) {
        if (path == null || path.isBlank()) {
            throw new BusinessException(ErrorCode.PARAM_INVALID, "组路径不能为空");
        }

        String[] segments = path.split("/");
        String parentId = null;
        String currentId = null;

        for (String rawName : segments) {
            final String name = rawName.trim();
            if (name.isEmpty()) continue;

            final String finalParentId = parentId;
            Optional<UserGroup> existing = groupRepo.findAll().stream()
                .filter(g -> name.equals(g.getName())
                    && java.util.Objects.equals(finalParentId, g.getParentGroupId()))
                .findFirst();

            if (existing.isPresent()) {
                currentId = existing.get().getId();
            } else {
                UserGroup group = new UserGroup(
                    UUID.randomUUID().toString(), name, parentId, createdBy);
                group.setSource("sync");
                group = groupRepo.save(group);
                groupAdminRepo.save(new GroupAdmin(
                    group.getId(), createdBy, "owner", null));
                currentId = group.getId();
                log.info("嵌套建组: name={}, parent={}, id={}", name, parentId, currentId);
            }
            parentId = currentId;
        }

        if (currentId == null) {
            throw new BusinessException(ErrorCode.PARAM_INVALID, "组路径中无有效组名");
        }
        return currentId;
    }
}
