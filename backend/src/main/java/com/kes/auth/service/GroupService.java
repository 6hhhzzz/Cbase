package com.kes.auth.service;

import com.kes.auth.model.GroupAdmin;
import com.kes.auth.model.User;
import com.kes.auth.model.UserGroup;
import com.kes.auth.model.UserGroupMember;
import com.kes.auth.repository.GroupAdminRepository;
import com.kes.auth.repository.UserGroupMemberRepository;
import com.kes.auth.repository.UserGroupRepository;
import com.kes.auth.repository.UserRepository;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;

/**
 * 用户组服务 — v4 ACE 权限模型。
 * 管理全局可嵌套用户组的 CRUD、成员管理和层级展开。
 */
@Service
public class GroupService {

    private static final Logger log = LoggerFactory.getLogger(GroupService.class);

    private final UserGroupRepository groupRepo;
    private final UserGroupMemberRepository memberRepo;
    private final UserRepository userRepo;
    private final GroupAdminRepository groupAdminRepo;

    public GroupService(UserGroupRepository groupRepo,
                        UserGroupMemberRepository memberRepo,
                        UserRepository userRepo,
                        GroupAdminRepository groupAdminRepo) {
        this.groupRepo = groupRepo;
        this.memberRepo = memberRepo;
        this.userRepo = userRepo;
        this.groupAdminRepo = groupAdminRepo;
    }

    // ============================================================
    // 用户组 CRUD
    // ============================================================

    /** 创建全局用户组 */
    @Transactional
    public UserGroup createGroup(String name, String description, String parentGroupId, String createdBy) {
        if (name == null || name.isBlank()) {
            throw new BusinessException(ErrorCode.GROUP_NAME_EMPTY);
        }
        if (parentGroupId != null) {
            groupRepo.findById(parentGroupId)
                .orElseThrow(() -> new BusinessException(ErrorCode.GROUP_NOT_FOUND, "父组不存在: " + parentGroupId));
        }
        UserGroup group = new UserGroup(UUID.randomUUID().toString(), name, parentGroupId, createdBy);
        group.setDescription(description != null ? description : "");
        group = groupRepo.save(group);
        // 创建者自动成为 group owner
        groupAdminRepo.save(new GroupAdmin(group.getId(), createdBy, "owner", null));
        log.info("用户组创建: id={}, name={}, owner={}, parent={}", group.getId(), name, createdBy, parentGroupId);
        return group;
    }

    /** 列出所有根组（无父组的顶层组） */
    public List<UserGroup> listRootGroups() {
        return groupRepo.findByParentGroupIdIsNull();
    }

    /** 列出指定父组下的子组 */
    public List<UserGroup> listChildGroups(String parentGroupId) {
        return groupRepo.findByParentGroupId(parentGroupId);
    }

    /** 列出所有组 */
    public List<UserGroup> listAllGroups() {
        return groupRepo.findAll();
    }

    /** 获取单个组 */
    public UserGroup getGroup(String groupId) {
        return groupRepo.findById(groupId)
            .orElseThrow(() -> new BusinessException(ErrorCode.GROUP_NOT_FOUND, "用户组不存在: " + groupId));
    }

    /** 修改用户组 */
    @Transactional
    public UserGroup updateGroup(String groupId, String name, String description,
                                  String parentGroupId, Boolean isSystemAdmin) {
        UserGroup group = getGroup(groupId);
        if (name != null && !name.isBlank()) {
            group.setName(name);
        }
        if (description != null) {
            group.setDescription(description);
        }
        if (isSystemAdmin != null) {
            group.setSystemAdmin(isSystemAdmin);
        }
        if (parentGroupId != null) {
            // 防止循环引用
            if (groupId.equals(parentGroupId)) {
                throw new BusinessException(ErrorCode.GROUP_CANNOT_PARENT_SELF);
            }
            if (!parentGroupId.isEmpty()) {
                groupRepo.findById(parentGroupId)
                    .orElseThrow(() -> new BusinessException(ErrorCode.GROUP_NOT_FOUND, "父组不存在: " + parentGroupId));
            }
            group.setParentGroupId(parentGroupId.isEmpty() ? null : parentGroupId);
        }
        group = groupRepo.save(group);
        log.info("用户组更新: id={}, name={}", groupId, group.getName());
        return group;
    }

    /** 删除用户组（有关联子组时阻止） */
    @Transactional
    public void deleteGroup(String groupId) {
        UserGroup group = getGroup(groupId);
        List<UserGroup> children = groupRepo.findByParentGroupId(groupId);
        if (!children.isEmpty()) {
            throw new BusinessException(ErrorCode.GROUP_HAS_CHILDREN, "该组下有 " + children.size() + " 个子组，请先删除子组");
        }
        groupRepo.delete(group);
        log.info("用户组删除: id={}, name={}", groupId, group.getName());
    }

    // ============================================================
    // Group 管理员管理
    // ============================================================

    /** 判断用户是否可以管理该组（全局管理员 或 该组的 admin/owner） */
    public boolean canManageGroup(String groupId, String userId) {
        // 全局管理员
        if (userRepo.findById(userId).map(u -> u.getIsGlobalAdmin() != null && u.getIsGlobalAdmin()).orElse(false))
            return true;
        // is_system_admin 组
        if (memberRepo.findGroupIdsByUserId(userId).stream()
                .anyMatch(gid -> groupRepo.findById(gid).map(UserGroup::isSystemAdmin).orElse(false)))
            return true;
        // 该组的 admin
        return groupAdminRepo.existsByGroupIdAndUserId(groupId, userId);
    }

    public List<GroupAdmin> getGroupAdmins(String groupId) {
        return groupAdminRepo.findByGroupId(groupId);
    }

    @Transactional
    public void addGroupAdmin(String operatorId, String groupId, String userId, String role) {
        if (!canManageGroup(groupId, operatorId))
            throw new BusinessException(ErrorCode.GROUP_ADMIN_REQUIRED);
        getGroup(groupId);
        if (groupAdminRepo.existsByGroupIdAndUserId(groupId, userId))
            throw new BusinessException(ErrorCode.GROUP_ADMIN_ALREADY_EXISTS);
        String r = ("admin".equals(role) || "owner".equals(role)) ? role : "admin";
        groupAdminRepo.save(new GroupAdmin(groupId, userId, r, operatorId));
        log.info("Group 管理员添加: group={}, user={}, role={}", groupId, userId, r);
    }

    @Transactional
    public void removeGroupAdmin(String operatorId, String groupId, String userId) {
        if (!canManageGroup(groupId, operatorId))
            throw new BusinessException(ErrorCode.GROUP_ADMIN_REQUIRED);
        GroupAdmin ga = groupAdminRepo.findByGroupIdAndUserId(groupId, userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.GROUP_ADMIN_NOT_FOUND));
        if ("owner".equals(ga.getRole()) && !operatorId.equals(userId))
            throw new BusinessException(ErrorCode.GROUP_CANNOT_REMOVE_OWNER);
        groupAdminRepo.deleteByGroupIdAndUserId(groupId, userId);
        log.info("Group 管理员移除: group={}, user={}", groupId, userId);
    }

    // ============================================================
    // 组成员管理
    // ============================================================

    /** 获取组成员 ID 列表（直接成员，不含嵌套） */
    public List<String> getDirectMemberUserIds(String groupId) {
        return memberRepo.findByGroupId(groupId).stream()
            .map(UserGroupMember::getUserId)
            .toList();
    }

    /** 获取组成员详情列表（含用户名和显示名） */
    public List<Map<String, String>> getDirectMembers(String groupId) {
        return memberRepo.findByGroupId(groupId).stream()
            .map(m -> {
                Map<String, String> info = new java.util.HashMap<>();
                info.put("user_id", m.getUserId());
                userRepo.findById(m.getUserId()).ifPresent(u -> {
                    info.put("username", u.getUsername());
                    info.put("display_name", u.getDisplayName());
                });
                return info;
            })
            .toList();
    }

    /** 获取组的所有成员（直接 + 嵌套子组成员展开） */
    public Set<String> getExpandedMemberUserIds(String groupId) {
        Set<String> userIds = new HashSet<>();
        Set<String> visitedGroups = new HashSet<>();
        collectMembersRecursive(groupId, userIds, visitedGroups);
        return userIds;
    }

    private void collectMembersRecursive(String groupId, Set<String> userIds, Set<String> visitedGroups) {
        if (!visitedGroups.add(groupId)) return;  // 防止循环引用
        // 收集当前组的直接成员
        memberRepo.findByGroupId(groupId).forEach(m -> userIds.add(m.getUserId()));
        // 递归收集子组成员
        groupRepo.findByParentGroupId(groupId).forEach(child ->
            collectMembersRecursive(child.getId(), userIds, visitedGroups));
    }

    /** 按名称查找组 */
    public Optional<UserGroup> findByName(String name) {
        return groupRepo.findByName(name);
    }

    /** 添加成员到组 */
    @Transactional
    public void addMember(String groupId, String userId) {
        getGroup(groupId);
        if (memberRepo.existsByGroupIdAndUserId(groupId, userId)) {
            throw new BusinessException(ErrorCode.GROUP_ALREADY_MEMBER);
        }
        memberRepo.save(new UserGroupMember(UUID.randomUUID().toString(), groupId, userId));
        log.info("组成员添加: group={}, user={}", groupId, userId);
    }

    /** 批量添加成员 — 跳过已存在的，返回成功添加数 */
    @Transactional
    public int addMembers(String groupId, java.util.List<String> userIds) {
        getGroup(groupId);
        int added = 0;
        for (String userId : userIds) {
            if (!memberRepo.existsByGroupIdAndUserId(groupId, userId)) {
                memberRepo.save(new UserGroupMember(UUID.randomUUID().toString(), groupId, userId));
                added++;
            }
        }
        log.info("批量组成员添加: group={}, requested={}, added={}", groupId, userIds.size(), added);
        return added;
    }

    /** 从组移除成员 */
    @Transactional
    public void removeMember(String groupId, String userId) {
        if (!memberRepo.existsByGroupIdAndUserId(groupId, userId)) {
            throw new BusinessException(ErrorCode.GROUP_MEMBER_NOT_FOUND);
        }
        memberRepo.deleteByGroupIdAndUserId(groupId, userId);
        log.info("组成员移除: group={}, user={}", groupId, userId);
    }

    /** 统计组成员数（仅直接成员） */
    public long countMembers(String groupId) {
        return memberRepo.countByGroupId(groupId);
    }

    // ============================================================
    // 层级展开 — 核心算法
    // ============================================================

    /**
     * 获取用户的有效组列表（含层级展开）。
     * 用户直接归属的组 + 递归上溯所有祖先组。
     *
     * 例：用户在"后端架构组"(parent=研发部, parent=公司全员)
     *     → effectiveGroups = [后端架构组, 研发部, 公司全员]
     */
    public Set<String> expandUserEffectiveGroups(String userId) {
        Set<String> result = new LinkedHashSet<>();
        Deque<String> queue = new ArrayDeque<>();

        // 起点：用户直接归属的组
        List<String> directGroups = memberRepo.findGroupIdsByUserId(userId);
        for (String gid : directGroups) {
            if (result.add(gid)) {
                queue.add(gid);
            }
        }

        // BFS 上溯所有祖先组
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
     * 用于权限缓存失效：parent_group_id 变更时需要找出所有受影响的子组。
     */
    public Set<String> expandAncestors(String groupId) {
        Set<String> ancestors = new LinkedHashSet<>();
        String current = groupId;
        while (true) {
            Optional<String> parent = groupRepo.findParentId(current);
            if (parent.isEmpty()) break;
            if (!ancestors.add(parent.get())) break;  // 防止循环
            current = parent.get();
        }
        return ancestors;
    }

    /**
     * 获取指定组的所有子孙组 ID（递归向下展开）。
     * 用于 parent_group_id 变更时的缓存失效。
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
}
