package com.kes.auth.service;

import com.kes.AbstractIntegrationTest;
import com.kes.auth.model.*;
import com.kes.auth.repository.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

/**
 * PermissionService 集成测试 — ACE 权限模型核心算法。
 * 使用真实数据库验证权限解析结果。
 */
class PermissionServiceIT extends AbstractIntegrationTest {

    @Autowired private PermissionService permService;
    @Autowired private PermissionQueryService permQueryService;
    @Autowired private UserRepository userRepo;
    @Autowired private SpaceRepository spaceRepo;
    @Autowired private SpaceAdminRepository spaceAdminRepo;
    @Autowired private SpaceGroupRepository spaceGroupRepo;
    @Autowired private KnowledgeBaseRepository kbRepo;
    @Autowired private AceRepository aceRepo;
    @Autowired private UserGroupRepository groupRepo;
    @Autowired private UserGroupMemberRepository groupMemberRepo;
    @Autowired private GroupService groupService;
    @Autowired private KbPermissionCache permissionCache;

    private String spaceId, kbSpaceWideId, kbRestrictedId;
    private User admin, member, outsider;
    private UserGroup group;

    @BeforeEach
    @Transactional
    void setUpData() {
        spaceId = UUID.randomUUID().toString();

        // 创建用户
        admin = createUser("admin-user");
        member = createUser("member-user");
        outsider = createUser("outsider");

        // 创建 Space
        Space space = spaceRepo.save(new Space(spaceId, "测试空间", "general", "测试", admin.getId()));
        spaceAdminRepo.save(new SpaceAdmin(spaceId, admin.getId(), "owner", null));

        // 创建 KB
        kbSpaceWideId = UUID.randomUUID().toString();
        kbRepo.save(new KnowledgeBase(kbSpaceWideId, spaceId, "公开KB", "", "space_wide", admin.getId()));

        kbRestrictedId = UUID.randomUUID().toString();
        kbRepo.save(new KnowledgeBase(kbRestrictedId, spaceId, "受限KB", "", "restricted", admin.getId()));

        // 创建用户组 + 加入成员
        group = new UserGroup();
        group.setId(UUID.randomUUID().toString());
        group.setName("测试组");
        group.setCreatedBy(admin.getId());
        groupRepo.save(group);
        groupMemberRepo.save(new UserGroupMember(UUID.randomUUID().toString(), group.getId(), member.getId()));
    }

    @Test
    @Transactional
    void spaceAdmin_canAccessAllKbs() {
        List<String> kbIds = permQueryService.resolveAccessibleKbIds(spaceId, admin.getId());
        assertTrue(kbIds.contains(kbSpaceWideId), "Space admin 应能访问 space_wide KB");
        assertTrue(kbIds.contains(kbRestrictedId), "Space admin 应能访问 restricted KB");
    }

    @Test
    @Transactional
    void regularMember_canAccessSpaceWideKb() {
        // member 通过用户组加入 Space
        spaceGroupRepo.save(new SpaceGroup(UUID.randomUUID().toString(), spaceId, group.getId()));

        List<String> kbIds = permQueryService.resolveAccessibleKbIds(spaceId, member.getId());
        assertTrue(kbIds.contains(kbSpaceWideId), "普通成员应能访问 space_wide KB");
        assertFalse(kbIds.contains(kbRestrictedId), "普通成员不应能访问 restricted KB（无 ACE）");
    }

    @Test
    @Transactional
    void aceDeny_overridesAllow() {
        // member 通过用户组加入 Space
        spaceGroupRepo.save(new SpaceGroup(UUID.randomUUID().toString(), spaceId, group.getId()));

        // ACE: allow member 组访问 restricted KB
        aceRepo.save(new AccessControlEntry(
            UUID.randomUUID().toString(), spaceId, "kb", kbRestrictedId,
            "group", group.getId(), "admin", "allow", 0));

        // 验证允许
        List<String> kbIds = permQueryService.resolveAccessibleKbIds(spaceId, member.getId());
        assertTrue(kbIds.contains(kbRestrictedId), "ACE allow 后应能访问");

        // ACE: deny member 用户访问 restricted KB（deny 覆盖 allow）
        aceRepo.save(new AccessControlEntry(
            UUID.randomUUID().toString(), spaceId, "kb", kbRestrictedId,
            "user", member.getId(), "admin", "deny", 10));

        // 直接写 repo 绕过了 AceService 的缓存失效，手动 evict 模拟生产的 ACE 变更失效
        permissionCache.evict(member.getId(), spaceId);

        kbIds = permQueryService.resolveAccessibleKbIds(spaceId, member.getId());
        assertFalse(kbIds.contains(kbRestrictedId), "deny 应覆盖 allow，最终拒绝访问");
    }

    @Test
    @Transactional
    void outsider_hasNoAccess() {
        List<String> kbIds = permQueryService.resolveAccessibleKbIds(spaceId, outsider.getId());
        assertTrue(kbIds.isEmpty(), "非 Space 成员应无任何 KB 访问权限");
    }

    // ---- helpers ----

    private User createUser(String username) {
        User u = new User(UUID.randomUUID().toString(), username, "pw", username);
        return userRepo.save(u);
    }
}
