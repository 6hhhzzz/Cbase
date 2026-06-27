package com.kes.auth.service;

import com.kes.auth.model.KnowledgeBase;
import com.kes.auth.model.Space;
import com.kes.auth.model.SpaceAdmin;
import com.kes.auth.model.SpaceGroup;
import com.kes.auth.model.User;
import com.kes.auth.model.UserGroup;
import com.kes.auth.repository.AceRepository;
import com.kes.auth.repository.KnowledgeBaseRepository;
import com.kes.auth.repository.SpaceAdminRepository;
import com.kes.auth.repository.SpaceGroupRepository;
import com.kes.auth.repository.SpaceRepository;
import com.kes.auth.repository.UserRepository;
import com.kes.common.dto.SpaceDtos.AdminInfo;
import com.kes.common.dto.SpaceDtos.GroupInfo;
import com.kes.common.exception.BusinessException;
import com.kes.common.exception.ErrorCode;
import com.kes.common.service.AuditLogger;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

/**
 * Space 管理服务 — v4 ACE 权限模型。
 *
 * <p>管理 Space 生命周期（创建/归档）、管理员（space_admins）和准入组（space_groups）。
 * 仅限 Space admin 及以上权限调用写操作。
 */
@Service
public class SpaceService {

    private static final Logger log = LoggerFactory.getLogger(SpaceService.class);

    private final SpaceRepository spaceRepo;
    private final SpaceAdminRepository spaceAdminRepo;
    private final SpaceGroupRepository spaceGroupRepo;
    private final KnowledgeBaseRepository kbRepo;
    private final UserRepository userRepo;
    private final KbPermissionCache permissionCache;
    private final PermissionService permService;
    private final GroupService groupService;
    private final AceRepository aceRepo;
    private final AuditLogger auditLogger;

    public SpaceService(SpaceRepository spaceRepo,
                        SpaceAdminRepository spaceAdminRepo,
                        SpaceGroupRepository spaceGroupRepo,
                        KnowledgeBaseRepository kbRepo,
                        UserRepository userRepo,
                        KbPermissionCache permissionCache,
                        PermissionService permService,
                        GroupService groupService,
                        AceRepository aceRepo,
                        AuditLogger auditLogger) {
        this.spaceRepo = spaceRepo;
        this.spaceAdminRepo = spaceAdminRepo;
        this.spaceGroupRepo = spaceGroupRepo;
        this.kbRepo = kbRepo;
        this.userRepo = userRepo;
        this.permissionCache = permissionCache;
        this.permService = permService;
        this.groupService = groupService;
        this.aceRepo = aceRepo;
        this.auditLogger = auditLogger;
    }

    // ================================================================
    // Space 生命周期
    // ================================================================

    /** 创建新 Space — 创建者自动成为 owner，并自动创建默认 KB */
    @Transactional
    public Space createSpace(String userId, String name, String typeLabel, String description) {
        String spaceId = UUID.randomUUID().toString();
        Space space = new Space(spaceId, name,
            typeLabel != null ? typeLabel : "general",
            description != null ? description : "", userId);
        space = spaceRepo.save(space);

        // 创建者成为 owner
        spaceAdminRepo.save(new SpaceAdmin(spaceId, userId, "owner", null));

        // 自动创建默认 KB
        KnowledgeBase defaultKb = new KnowledgeBase(
            UUID.randomUUID().toString(), spaceId, "默认知识库",
            "系统自动创建的默认知识库", "space_wide", userId);
        kbRepo.save(defaultKb);

        auditLogger.log(userId, spaceId, "space.create", "space", spaceId, name,
            "{\"type_label\":\"" + (typeLabel != null ? typeLabel : "general") + "\"}");

        log.info("Space 创建: id={}, name={}, owner={}", spaceId, name, userId);
        return space;
    }

    /** 归档 Space — Space admin */
    @Transactional
    public void archiveSpace(String operatorId, String spaceId) {
        permService.requireSpaceAdmin(spaceId, operatorId);
        Space space = spaceRepo.findById(spaceId)
            .orElseThrow(() -> new BusinessException(ErrorCode.SPACE_NOT_FOUND));
        space.setStatus("archived");
        spaceRepo.save(space);

        auditLogger.log(operatorId, spaceId, "space.archive", "space", spaceId, space.getName(), "{}");
        log.info("Space 归档: id={}, name={}", spaceId, space.getName());
    }

    // ================================================================
    // Space 管理员管理
    // ================================================================

    /** 查看 Space 管理员列表（原始实体，内部使用） */
    public List<SpaceAdmin> getSpaceAdmins(String spaceId) {
        return spaceAdminRepo.findBySpaceId(spaceId);
    }

    /** 查看 Space 管理员列表（含用户名和显示名，供 Controller 使用） */
    public List<AdminInfo> getAdminsWithUserInfo(String spaceId) {
        List<SpaceAdmin> admins = spaceAdminRepo.findBySpaceId(spaceId);
        return admins.stream().map(a -> {
            User u = userRepo.findById(a.getUserId()).orElse(null);
            return new AdminInfo(a.getUserId(),
                u != null ? u.getUsername() : "", u != null ? u.getDisplayName() : "",
                a.getRole(), a.getGrantedBy(), a.getCreatedAt());
        }).toList();
    }

    /** 添加 Space 管理员 — 仅 owner 可操作 */
    @Transactional
    public void addSpaceAdmin(String operatorId, String spaceId, String userId, String role) {
        permService.requireSpaceOwner(spaceId, operatorId);

        userRepo.findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND, "用户不存在: " + userId));

        if (spaceAdminRepo.existsBySpaceIdAndUserId(spaceId, userId)) {
            throw new BusinessException(ErrorCode.SPACE_ADMIN_ALREADY_EXISTS);
        }

        String adminRole = ("admin".equals(role) || "owner".equals(role)) ? role : "admin";
        spaceAdminRepo.save(new SpaceAdmin(spaceId, userId, adminRole, operatorId));

        permissionCache.evict(userId, spaceId);

        auditLogger.log(operatorId, spaceId, "admin.add", "user", userId,
            null, "{\"role\":\"" + adminRole + "\"}");
        log.info("Space 管理员添加: space={}, user={}, role={}", spaceId, userId, adminRole);
    }

    /** 移除 Space 管理员 — 仅 owner 可操作，不允许移除自己 */
    @Transactional
    public void removeSpaceAdmin(String operatorId, String spaceId, String userId) {
        permService.requireSpaceOwner(spaceId, operatorId);

        if (operatorId.equals(userId)) {
            throw new BusinessException(ErrorCode.SPACE_CANNOT_REMOVE_SELF);
        }

        SpaceAdmin admin = spaceAdminRepo.findBySpaceIdAndUserId(spaceId, userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.SPACE_ADMIN_NOT_FOUND));

        if ("owner".equals(admin.getRole())) {
            throw new BusinessException(ErrorCode.SPACE_CANNOT_REMOVE_OTHER_OWNER, "不能移除其他 Owner，仅 Owner 本人可转让");
        }

        spaceAdminRepo.deleteBySpaceIdAndUserId(spaceId, userId);
        permissionCache.evict(userId, spaceId);

        auditLogger.log(operatorId, spaceId, "admin.remove", "user", userId,
            null, "{\"previous_role\":\"" + admin.getRole() + "\"}");
        log.info("Space 管理员移除: space={}, user={}", spaceId, userId);
    }

    /** 转让 Owner — 仅当前 owner 可操作 */
    @Transactional
    public void transferOwnership(String operatorId, String spaceId, String newOwnerUserId) {
        permService.requireSpaceOwner(spaceId, operatorId);

        userRepo.findById(newOwnerUserId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND, "目标用户不存在: " + newOwnerUserId));

        SpaceAdmin newOwner = spaceAdminRepo.findBySpaceIdAndUserId(spaceId, newOwnerUserId)
            .orElseThrow(() -> new BusinessException(ErrorCode.SPACE_NOT_ADMIN_CANNOT_OWNER));

        // 原 owner 降级为 admin
        SpaceAdmin oldOwner = spaceAdminRepo.findBySpaceIdAndUserId(spaceId, operatorId).get();
        oldOwner.setRole("admin");
        spaceAdminRepo.save(oldOwner);

        // 新 owner 升级
        newOwner.setRole("owner");
        spaceAdminRepo.save(newOwner);

        auditLogger.log(operatorId, spaceId, "owner.transfer", "user", newOwnerUserId, null, "{}");
        log.info("Owner 转让: space={}, from={}, to={}", spaceId, operatorId, newOwnerUserId);
    }

    // ================================================================
    // Space 准入组管理
    // ================================================================

    /** 查看 Space 的准入组列表（原始实体，内部使用） */
    public List<SpaceGroup> getSpaceGroups(String spaceId) {
        return spaceGroupRepo.findBySpaceId(spaceId);
    }

    /** 查看 Space 的准入组列表（含组名，供 Controller 使用） */
    public List<GroupInfo> getGroupsWithName(String spaceId) {
        List<SpaceGroup> groups = spaceGroupRepo.findBySpaceId(spaceId);
        return groups.stream().map(g ->
            new GroupInfo(g.getId(), g.getGroupId(),
                groupService.getGroup(g.getGroupId()).getName(),
                g.getJoinedAt())
        ).toList();
    }

    /** 将全局用户组分配到 Space — Space admin */
    @Transactional
    public void addSpaceGroup(String operatorId, String spaceId, String groupId) {
        permService.requireSpaceAdmin(spaceId, operatorId);

        groupService.getGroup(groupId);

        if (spaceGroupRepo.existsBySpaceIdAndGroupId(spaceId, groupId)) {
            throw new BusinessException(ErrorCode.SPACE_GROUP_ALREADY_ADDED);
        }

        spaceGroupRepo.save(new SpaceGroup(UUID.randomUUID().toString(), spaceId, groupId));
        permissionCache.evictBySpace(spaceId);

        auditLogger.log(operatorId, spaceId, "space_group.add", "group", groupId, null, "{}");
        log.info("Space 准入组添加: space={}, group={}", spaceId, groupId);
    }

    /** 从 Space 移除准入组 — Space admin */
    @Transactional
    public void removeSpaceGroup(String operatorId, String spaceId, String groupId) {
        permService.requireSpaceAdmin(spaceId, operatorId);

        if (!spaceGroupRepo.existsBySpaceIdAndGroupId(spaceId, groupId)) {
            throw new BusinessException(ErrorCode.SPACE_GROUP_NOT_FOUND);
        }

        spaceGroupRepo.deleteBySpaceIdAndGroupId(spaceId, groupId);

        // 级联清理该组在 Space 中的所有 ACE 条目
        aceRepo.deleteBySpaceIdAndPrincipal(spaceId, "group", groupId);

        permissionCache.evictBySpace(spaceId);

        auditLogger.log(operatorId, spaceId, "space_group.remove", "group", groupId, null, "{}");
        log.info("Space 准入组移除: space={}, group={}, ACE已级联清理", spaceId, groupId);
    }
}
