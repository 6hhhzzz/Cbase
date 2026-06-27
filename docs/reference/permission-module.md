# 权限管理模块详解

> 版本: v4 ACE + v8 MCP A+C 混合
> 最后更新: 2026-06-26

---

## 1. 模块架构概览

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         请求入口 (HTTP / MCP)                             │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
    ┌──────────────────┐          ┌──────────────────┐
    │   JwtFilter      │          │  MCP Auth        │
    │   验证 JWT 签名   │          │  API Key → JWT   │
    │   注入 SecurityCtx│          │  交换端点         │
    └────────┬─────────┘          └────────┬─────────┘
             │                             │
             └──────────┬──────────────────┘
                        ▼
    ┌──────────────────────────────────────────────┐
    │              SecurityContext                  │
    │   Principal: userId                          │
    │   Credentials: JWT token string              │
    └────────────────────┬─────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
┌──────────────────┐          ┌──────────────────────────┐
│  注解 + AOP       │          │  手动权限校验              │
│  @RequireSpaceAdm │          │  PermissionService        │
│  @RequireGlobalAd │          │  .requireSpaceAdmin()     │
│  → AdminGuard     │          │  .isSpaceAdmin()          │
└────────┬─────────┘          │  .requireSpaceMember()    │
         │                    └────────────┬─────────────┘
         │                                 │
         └──────────────┬──────────────────┘
                        ▼
    ┌──────────────────────────────────────────────┐
    │           PermissionService                  │
    │          唯一权威的权限决策点                  │
    │                                              │
    │  isGlobalAdmin()     全局管理员判定           │
    │  isSpaceAdmin()      Space 管理员判定         │
    │  isSpaceMember()     Space 成员判定           │
    │  isSpaceOwner()      Space Owner 判定         │
    │  getUserSpaceRole()  用户角色查询             │
    │  getUserSpaceGroups() 有效组展开              │
    └────────────────────┬─────────────────────────┘
                         │
                         ▼
    ┌──────────────────────────────────────────────┐
    │         PermissionQueryService               │
    │         KB/文档级权限解析                     │
    │                                              │
    │  resolveAccessibleKbIds()   KB 权限列表      │
    │  resolveAccessibleDocIds()  文档权限列表     │
    └────────────────────┬─────────────────────────┘
                         │
                         ▼
    ┌──────────────────────────────────────────────┐
    │         KbPermissionCache (Redis)             │
    │         5 分钟 TTL 缓存加速                    │
    └──────────────────────────────────────────────┘
```

---

## 2. 三层身份模型

系统定义了三层身份，从高到低依次为：

| 层级 | 身份 | 判定方式 | 权限范围 |
|------|------|---------|---------|
| L1 | 全局超级管理员 | `users.is_global_admin = TRUE` 或所属 `user_groups.is_system_admin = TRUE` | 所有 Space 的所有 KB |
| L2 | Space 管理员 | `space_admins` 表直接关联 User（owner / admin） | 当前 Space 内所有 KB |
| L3 | Space 普通成员 | 通过 `space_groups` 关联的全局用户组（含嵌套展开） | KB 访问由 ACE 矩阵决定 |

### 实现位置

**`PermissionService.java`** — `backend/src/main/java/com/kes/auth/service/PermissionService.java`

```java
// L1: 全局管理员判定 (第 80-93 行)
public boolean isGlobalAdmin(String userId) {
    // 来源 1: users.is_global_admin
    boolean userFlag = userRepo.findById(userId)
        .map(u -> u.getIsGlobalAdmin() != null && u.getIsGlobalAdmin())
        .orElse(false);
    if (userFlag) return true;

    // 来源 2: 用户属于 is_system_admin 的全局组
    List<String> userGroupIds = groupMemberRepo.findGroupIdsByUserId(userId);
    if (userGroupIds.isEmpty()) return false;
    return groupRepo.findAllById(userGroupIds).stream()
        .anyMatch(UserGroup::isSystemAdmin);
}

// L2: Space 管理员判定 (第 114-116 行)
public boolean isSpaceAdmin(String spaceId, String userId) {
    return spaceAdminRepo.existsBySpaceIdAndUserId(spaceId, userId);
}

// L3: Space 成员判定 (第 159-165 行)
public boolean isSpaceMember(String spaceId, String userId) {
    // 管理员也算成员
    if (spaceAdminRepo.existsBySpaceIdAndUserId(spaceId, userId)) return true;
    // 获取用户在 Space 中的有效组 (含嵌套展开)
    return !getUserSpaceGroups(spaceId, userId).isEmpty();
}
```

**级联关系**: L1 > L2 > L3。全局管理员自动通过所有 Space Admin 和 Space Member 检查；Space Admin 自动通过 Space Member 检查。

```java
// requireSpaceAdmin 中的级联 (第 107-112 行)
public void requireSpaceAdmin(String spaceId, String userId) {
    if (isGlobalAdmin(userId)) return;   // L1 自动通过
    if (!isSpaceAdmin(spaceId, userId)) {
        throw new BusinessException(403, "需要 Space 管理员权限");
    }
}

// requireSpaceMember 中的级联 (第 147-153 行)
public void requireSpaceMember(String spaceId, String userId) {
    if (isGlobalAdmin(userId)) return;   // L1 自动通过
    if (isSpaceAdmin(spaceId, userId)) return;  // L2 自动通过
    if (!isSpaceMember(spaceId, userId)) {
        throw new BusinessException(403, "你无权访问该 Space");
    }
}
```

---

## 3. JWT 双 Token 方案

### Token 类型

| Token | 有效期 | 载荷 | 用途 |
|-------|--------|------|------|
| `refresh_token` | 7 天 | `{sub: userId, type: "refresh"}` | 登录、刷新、列出 Space、切换 Space |
| `context_token` | 30 分钟 | `{sub: userId, space_id, role}` | 所有业务 API 调用 |

### Token 生成

**`JwtUtil.java`** — `backend/src/main/java/com/kes/common/util/JwtUtil.java`

```java
// 签发 Context Token (第 75-82 行)
public String generateContextToken(String userId, String username,
                                    String spaceId, String role) {
    return Jwts.builder()
        .subject(userId)
        .claim("username", username)
        .claim("space_id", spaceId)    // Space 上下文绑定
        .claim("role", role)           // 用户在 Space 中的角色
        .issuedAt(new Date())
        .expiration(new Date(System.currentTimeMillis() + contextExpiration))
        .signWith(getSigningKey())
        .compact();
}
```

### Token 验证链

**`JwtFilter.java`** — `backend/src/main/java/com/kes/auth/config/JwtFilter.java`

```
请求 → 提取 Bearer Token → 验证签名 → 提取 userId + spaceId + role
    → 构建 Authentication → 注入 SecurityContext
```

```java
// JwtFilter 核心逻辑 (第 47-63 行)
String userId = jwtUtil.extractUserId(token);
List<SimpleGrantedAuthority> authorities = new ArrayList<>();
if (jwtUtil.isContextToken(token)) {
    String role = jwtUtil.extractContextRole(token);
    if (role != null) {
        authorities.add(new SimpleGrantedAuthority("ROLE_" + role.toUpperCase()));
    }
}
UsernamePasswordAuthenticationToken auth =
    new UsernamePasswordAuthenticationToken(userId, token, authorities);
SecurityContextHolder.getContext().setAuthentication(auth);
```

### 切换 Space 流程

**`AuthService.java`** — `backend/src/main/java/com/kes/auth/service/AuthService.java:177-191`

```
1. 前端用 refresh_token 调用 POST /api/auth/switch-space { space_id }
2. AuthService 调用 PermissionService.getUserSpaceRole(spaceId, userId)
3. 如果 role == null → 403 (用户不是该 Space 成员)
4. 如果 role 有效 → 签发 30 分钟 context_token (嵌入 space_id + role)
5. 前端后续所有业务请求用 context_token
```

---

## 4. 权限校验的三种模式

### 模式 1: 注解声明式（Controller 入口守卫）

**注解定义:**

- `@RequireGlobalAdmin` — `backend/src/main/java/com/kes/common/annotation/RequireGlobalAdmin.java`
- `@RequireSpaceAdmin` — `backend/src/main/java/com/kes/common/annotation/RequireSpaceAdmin.java`

**AOP 切面实现:**

`backend/src/main/java/com/kes/common/aop/AdminGuard.java`

```java
@Aspect
@Component
public class AdminGuard {

    @Around("@annotation(com.kes.common.annotation.RequireGlobalAdmin)")
    public Object checkGlobalAdmin(ProceedingJoinPoint jp) throws Throwable {
        permissionService.requireGlobalAdmin();  // 从 SecurityContext 提取当前用户
        return jp.proceed();
    }

    @Around("@annotation(com.kes.common.annotation.RequireSpaceAdmin)")
    public Object checkSpaceAdmin(ProceedingJoinPoint jp) throws Throwable {
        String spaceId = permissionService.getCurrentSpaceId();  // 从 JWT 提取
        String userId = permissionService.getCurrentUserId();
        permissionService.requireSpaceAdmin(spaceId, userId);
        return jp.proceed();
    }
}
```

**使用示例:**

```java
// SpaceController.java
@PostMapping("/{spaceId}/kbs")
@RequireSpaceAdmin  // AOP 自动拦截，非管理员直接返回 403
public ApiResponse<Map<String, String>> createKb(...) { ... }

// AdminController.java
@GetMapping("/spaces")
@RequireGlobalAdmin  // AOP 自动拦截，非全局管理员直接返回 403
public ApiResponse<List<Space>> getAllSpaces() { ... }
```

### 模式 2: Service 手动调用（业务逻辑内的权限决策）

当需要在方法内部根据权限做分支判断时（而非简单地拒绝），使用手动调用：

```java
// DocumentController.java:delete() — 根据权限做不同操作
@DeleteMapping("/{docId}")
public ApiResponse<Map<String, Object>> delete(@PathVariable String docId,
        Authentication auth) {
    String userId = auth.getName();
    String spaceId = documentService.getById(docId).getSpaceId();

    if (permissionService.isSpaceAdmin(spaceId, userId)) {
        documentService.softDelete(docId);              // 管理员：直接删除
        return ApiResponse.success(Map.of("action", "deleted"));
    } else {
        documentService.requestDelete(docId, userId);    // 成员：创建审批
        return ApiResponse.success(Map.of("action", "pending_approval"));
    }
}
```

`isSpaceAdmin()` 返回 `boolean`，不抛异常，适合做 if-else 分支。

`requireSpaceAdmin()` 失败时抛 `BusinessException(403, ...)`，适合做强制拦截。

### 模式 3: PermissionQueryService 纯数据查询（KB 级别权限解析）

```java
// ChatController.java — 计算用户可访问的 KB 列表
String spaceId = jwtUtil.extractSpaceId(token);
List<String> kbIds = permissionQueryService.resolveAccessibleKbIds(spaceId, userId);
// kbIds = 用户在该 Space 中有权访问的所有 KB ID
```

---

## 5. PermissionService 完整 API

**文件:** `backend/src/main/java/com/kes/auth/service/PermissionService.java` (244 行)

### 全局管理员

| 方法 | 签名 | 说明 |
|------|------|------|
| `requireGlobalAdmin` | `(String userId)` | 校验指定用户是全局管理员，否则抛 403 |
| `requireGlobalAdmin` | `()` | 从 SecurityContext 提取当前用户 |
| `isGlobalAdmin` | `(String userId) → boolean` | 纯查询，不抛异常 |

### Space 管理员

| 方法 | 签名 | 说明 |
|------|------|------|
| `requireSpaceAdmin` | `(String spaceId, String userId)` | 校验指定用户是该 Space 管理员 |
| `requireSpaceAdmin` | `()` | 从 SecurityContext 提取 spaceId + userId |
| `isSpaceAdmin` | `(String spaceId, String userId) → boolean` | 纯查询 |

### Space Owner

| 方法 | 签名 | 说明 |
|------|------|------|
| `requireSpaceOwner` | `(String spaceId, String userId)` | 仅 Owner 可执行 |
| `isSpaceOwner` | `(String spaceId, String userId) → boolean` | 纯查询 |

### Space 成员

| 方法 | 签名 | 说明 |
|------|------|------|
| `requireSpaceMember` | `(String spaceId, String userId)` | 校验用户是 Space 成员（含管理员） |
| `requireSpaceMember` | `()` | 从 SecurityContext 提取 |
| `isSpaceMember` | `(String spaceId, String userId) → boolean` | 纯查询 |
| `getUserSpaceGroups` | `(String spaceId, String userId) → Set<String>` | 获取用户在 Space 中的有效组 ID |

### 角色查询

| 方法 | 签名 | 说明 |
|------|------|------|
| `getUserSpaceRole` | `(String spaceId, String userId) → String` | 返回 "owner" / "admin" / "member" / null |

### SecurityContext 工具

| 方法 | 签名 | 说明 |
|------|------|------|
| `getCurrentUserId` | `() → String` | 从 SecurityContext 提取当前 userId |
| `getCurrentSpaceId` | `() → String` | 从 JWT context_token 提取 spaceId |
| `getCurrentRole` | `() → String` | 从 JWT context_token 提取 role |

---

## 6. PermissionQueryService — KB 权限解析

**文件:** `backend/src/main/java/com/kes/auth/service/PermissionQueryService.java` (205 行)

### 核心算法: `resolveAccessibleKbIds(spaceId, userId)`

```
输入: spaceId, userId
输出: List<String> kbIds (用户有权访问的 KB ID 列表)

算法:
  1. 查 Redis 缓存: kes:user:{userId}:kb_ids:{spaceId}
     → 命中则直接返回

  2. 全局管理员判定:
     → isGlobalAdmin(userId) → 返回 Space 中所有未删除的 KB

  3. 计算用户有效组:
     → expandUserEffectiveGroups(userId) → 含嵌套上溯 BFS

  4. 判断 Space 身份:
     → space_admins 中有记录 → Space 管理员 → 所有 KB 可见
     → space_groups 中有匹配 → Space 普通成员 → 继续 ACE 解析
     → 都不匹配 → 返回空列表

  5. space_wide KB:
     → kbRepo.findSpaceWideKbIds(spaceId) → 自动加入结果

  6. ACE 矩阵:
     → 查询 access_control_entries WHERE space_id = :spaceId
       AND principal_type IN ('user', 'group')
       AND principal_id IN (:userGroups + userId)
     → allow → 加入结果
     → deny  → 从结果移除 (deny 始终覆盖 allow)

  7. 写入 Redis 缓存 (TTL 5 分钟)
```

### 代码实现

```java
// 第 61-115 行
public List<String> resolveAccessibleKbIds(String spaceId, String userId) {
    // 1. 缓存检查
    List<String> cached = cache.get(userId, spaceId);
    if (cached != null) return cached;

    // 2. 全局管理员
    if (permService.isGlobalAdmin(userId)) {
        List<String> allKbIds = kbRepo.findBySpaceIdAndDeletedAtIsNull(spaceId)
            .stream().map(KnowledgeBase::getId).toList();
        cache.put(userId, spaceId, allKbIds);
        return allKbIds;
    }

    // 3. 有效组展开
    Set<String> effectiveGroups = groupService.expandUserEffectiveGroups(userId);

    // 4. Space 管理员
    if (permService.isSpaceAdmin(spaceId, userId)) {
        List<String> allKbIds = kbRepo.findBySpaceIdAndDeletedAtIsNull(spaceId)
            .stream().map(KnowledgeBase::getId).toList();
        cache.put(userId, spaceId, allKbIds);
        return allKbIds;
    }

    // 5. 成员组匹配
    List<String> spaceGroupIds = spaceGroupRepo.findGroupIdsBySpaceId(spaceId);
    Set<String> matched = new HashSet<>(effectiveGroups);
    matched.retainAll(spaceGroupIds);
    if (matched.isEmpty()) {
        cache.put(userId, spaceId, List.of());
        return List.of();
    }

    // 6. ACE 解析
    Set<String> result = new LinkedHashSet<>();
    // 6a. space_wide KBs
    result.addAll(kbRepo.findSpaceWideKbIds(spaceId));

    // 6b. ACE 条目
    List<String> principals = new ArrayList<>();
    principals.add(userId);
    principals.addAll(new ArrayList<>(effectiveGroups));
    // ... deny/allow 处理 ...

    // 7. 写入缓存
    cache.put(userId, spaceId, new ArrayList<>(result));
    return new ArrayList<>(result);
}
```

---

## 7. ACE 权限矩阵

### 数据模型

`access_control_entries` 表结构：

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | UUID PK | |
| `space_id` | UUID FK → spaces | 所属 Space |
| `resource_type` | VARCHAR | 资源类型 (当前为 "kb") |
| `resource_id` | UUID | 资源 ID (KB ID) |
| `principal_type` | VARCHAR | 主体类型: "user" 或 "group" |
| `principal_id` | UUID | 主体 ID: userId 或 groupId |
| `role_id` | UUID FK → roles | 授予的角色 |
| `effect` | VARCHAR | "allow" 或 "deny" |
| `priority` | INT | 优先级 (数字越大越优先) |

### 核心原则

```
1. allow 条目 → 授予对指定 KB 的访问
2. deny 条目 → 撤销对指定 KB 的访问
3. deny 始终覆盖 allow（无论优先级）
4. 未匹配到任何 ACE 条目的 KB 默认不可访问
5. space_wide KB 对所有 Space 成员自动可见（无需 ACE 条目）
```

### ACE 管理 API

**`AceService.java`** — `backend/src/main/java/com/kes/auth/service/AceService.java`

| 操作 | 端点 | 权限要求 |
|------|------|---------|
| 查看 ACE 矩阵 | `GET /spaces/{id}/aces` | Space Admin |
| 创建 ACE 条目 | `POST /spaces/{id}/aces` | Space Admin |
| 修改 ACE 条目 | `PUT /spaces/{id}/aces/{aceId}` | Space Admin |
| 删除 ACE 条目 | `DELETE /spaces/{id}/aces/{aceId}` | Space Admin |

---

## 8. 角色系统

### 预置系统角色

| 角色 | permissions JSONB | 说明 |
|------|-------------------|------|
| Admin | `["kb.read","kb.write","kb.delete","ace.manage"]` | 完整 KB 管理 |
| Editor | `["kb.read","kb.write"]` | 读写 KB |
| Viewer | `["kb.read"]` | 只读 KB |
| Deny | `["kb.deny"]` | 明确拒绝（用于 deny 条目） |

系统角色受保护，不可删除，仅可改名。

**`RoleService.java`** — `backend/src/main/java/com/kes/auth/service/RoleService.java`

管理员可创建自定义角色，自定义 `permissions` JSONB 数组。

---

## 9. Redis 权限缓存

**文件:** `backend/src/main/java/com/kes/auth/service/KbPermissionCache.java` (122 行)

### 缓存键设计

```
Key:  kes:user:{userId}:kb_ids:{spaceId}       (Set, TTL 300s)
Aux:  kes:space:{spaceId}:user_ids             (Set, TTL 300s)
```

### 缓存失效时机

```java
// KbPermissionCache.java
public void evict(String userId, String spaceId) {
    // 1. 删除用户缓存
    redis.delete("kes:user:" + userId + ":kb_ids:" + spaceId);
    // 2. 更新辅助索引
    redis.sRem("kes:space:" + spaceId + ":user_ids", userId);
}
```

失效触发点（通过 Spring Events 或直接调用）：

| 事件 | 触发 |
|------|------|
| KB 创建/删除/恢复 | `KbService` → `cache.evictAll(spaceId)` |
| ACE 条目增删改 | `AceService` → `cache.evictAll(spaceId)` |
| 用户组变更 | `GroupService` → `cache.evictAllForUser(userId)` |
| Space 成员增减 | `SpaceService` → `cache.evictAll(spaceId)` |
| 用户禁用/启用 | `AdminService` → `cache.evict(userId, null)` |

---

## 10. 用户组层级展开

**文件:** `backend/src/main/java/com/kes/auth/service/GroupService.java`

### BFS 上溯展开

```java
// expandUserEffectiveGroups (第 267-280 行)
// 从用户直接所属的组出发，BFS 向上追溯所有祖先组
// 子组成员自动继承父组权限

输入: userId
输出: Set<String> effectiveGroupIds (含直接组 + 所有祖先组)

示例:
  userId = "user-1"
  直接组: ["group-A"]
  group-A.parent = "group-B"
  group-B.parent = "group-C"

  输出: {"group-A", "group-B", "group-C"}
```

此展开用于：
1. `PermissionService.getUserSpaceGroups()` — Space 成员判定
2. `PermissionQueryService.resolveAccessibleKbIds()` — ACE 主体匹配
3. `PermissionService.isGlobalAdmin()` — 系统管理组判定

---

## 11. Controller 层校验统一规范

经过最近一次重构（2026-06-26），所有 Controller 的权限校验统一为以下模式：

### 规则

```
1. 写操作 (POST/PUT/DELETE) → @RequireSpaceAdmin 或 @RequireGlobalAdmin 注解
2. 读操作 (GET) → 如需校验，在方法体开头调用 permissionService.requireXxx()
3. 分支判断 → 使用 permissionService.isXxx() (boolean 返回值)
4. 禁止 → 直接从 JWT 取 role 字符串比较 (如 "admin".equals(role))
5. 禁止 → Controller 直接注入 Repository
```

### 各 Controller 权限校验状态

| Controller | 校验方式 | 状态 |
|------------|---------|------|
| `AdminController` | `@RequireGlobalAdmin` 注解 | ✅ |
| `SpaceController` | `@RequireSpaceAdmin` 注解 (全部端点) | ✅ |
| `ApiKeyController` | 手动 `extractUserId` + ownership 检查 | ✅ (Key 操作需要拥有者校验) |
| `AuthController` | 手动 JWT 验证 (登录/注册不需要管理员) | ✅ |
| `DocumentController` | `@RequireSpaceAdmin` + `isSpaceAdmin()` 分支 | ✅ |
| `ChatController` | `requireSpaceMember()` | ✅ |
| `ConversationController` | `requireSpaceMember()` | ✅ |
| `GroupController` | 手动 `extractUserId` | ⚠️ 创建组无校验 |
| `RoleController` | 无注解 | ⚠️ |

---

## 12. MCP API Key 权限模型 (v8 A+C)

### A+C 混合公式

```
effective_kb_ids = tool_kb_ids      ← Agent 调用时传参 (可选)
                 ∩ ace_kb_ids       ← 用户 ACE 权限 (Java 实时解析)
                 ∩ scope_kb_ids     ← API Key 白名单 (创建时设定)
```

### 实现链路

```
MCP Client                    Java Backend                  Python MCP
    │                              │                            │
    │  POST /api/auth/mcp/exchange │                            │
    │  {api_key, space_id} ──────→ │                            │
    │                              │ ApiKeyService.exchange()   │
    │                              │  - 验证 key_hash           │
    │                              │  - 返回 context_token       │
    │                              │  - 返回 scope_kb_ids       │
    │  ←── {context_token,         │                            │
    │       scope_kb_ids}          │                            │
    │                                                          │
    │  MCP Tool 调用 ───────────────────────────────────────→ │
    │                              │                            │ MCPAuth.ensure_token()
    │                              │  GET /accessible-kbs ────→ │ resolve_kb_ids()
    │                              │  ←── ace_kb_ids ────────── │
    │                              │                            │ intersect_kb_ids(
    │                              │                            │   tool_kb_ids,
    │                              │                            │   ace_kb_ids,
    │                              │                            │   scope_kb_ids)
    │  ←── 检索结果 ────────────────────────────────────────── │
```

### scope_kb_ids 管理

| 操作 | API | 校验 |
|------|-----|------|
| 创建时设定 | `POST /mcp/keys` body: `{scope_kb_ids: [...]}` | scope ⊆ 创建者当前 ACE 权限 |
| 查看 scope | `GET /mcp/keys` response: `{scope_kb_ids: "[...]"}` | 仅显示自己的 Key |
| 修改 scope | `PUT /mcp/keys/{id}/scope` | scope ⊆ 创建者当前 ACE 权限 |

```java
// ApiKeyService.java — validateScope (第 172-183 行)
private void validateScope(String userId, String spaceId, List<String> scopeKbIds) {
    if (scopeKbIds == null || scopeKbIds.isEmpty()) return;
    List<String> aceKbIds = permissionQueryService.resolveAccessibleKbIds(spaceId, userId);
    Set<String> aceSet = new HashSet<>(aceKbIds);
    List<String> invalid = scopeKbIds.stream()
        .filter(kb -> !aceSet.contains(kb))
        .toList();
    if (!invalid.isEmpty()) {
        throw new BusinessException(409,
            "以下知识库不在你的权限范围内: " + String.join(", ", invalid));
    }
}
```

---

## 13. 权限校验调用关系总图

```
┌───────────────────────────────────────────────────────────────┐
│                        Controller 层                          │
│                                                               │
│  @RequireSpaceAdmin ──→ AdminGuard ──→ PermissionService      │
│  @RequireGlobalAdmin ──→ AdminGuard ──→ PermissionService     │
│  permissionService.isXxx()     ──→ PermissionService (分支)   │
│  permissionService.requireXxx()──→ PermissionService (强校验)  │
│  permissionQueryService.resolve*() → PermissionQueryService    │
└───────────────────────────────────┬───────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
          ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
          │PermissionSvc │ │PermissionQry │ │KbPermission  │
          │ 身份判定      │ │ KB 权限解析   │ │  Cache(Redis) │
          │              │ │              │ │              │
          │ isGlobalAdmin│ │ resolveKbIds │ │ get/put/evict│
          │ isSpaceAdmin │ │ resolveDocIds│ │              │
          │ isSpaceMember│ │              │ │              │
          │ isSpaceOwner │ │              │ │              │
          │ getUserRole  │ │              │ │              │
          └──────┬───────┘ └──────┬───────┘ └──────────────┘
                 │                │
                 ▼                ▼
          ┌──────────────────────────────────────────┐
          │              Repository 层                │
          │                                          │
          │  SpaceAdminRepo    SpaceGroupRepo        │
          │  GroupMemberRepo   GroupRepo             │
          │  UserRepo          AceRepo               │
          │  KnowledgeBaseRepo DocumentMetaRepo      │
          └──────────────────────────────────────────┘
```

---

## 14. 关键文件索引

| 文件 | 路径 | 职责 |
|------|------|------|
| `PermissionService.java` | `backend/.../auth/service/PermissionService.java` | 权限校验唯一入口 (244 行) |
| `PermissionQueryService.java` | `backend/.../auth/service/PermissionQueryService.java` | KB/文档权限解析 (205 行) |
| `KbPermissionCache.java` | `backend/.../auth/service/KbPermissionCache.java` | Redis 权限缓存 (122 行) |
| `AdminGuard.java` | `backend/.../common/aop/AdminGuard.java` | AOP 权限切面 (43 行) |
| `RequireSpaceAdmin.java` | `backend/.../common/annotation/RequireSpaceAdmin.java` | Space Admin 注解 |
| `RequireGlobalAdmin.java` | `backend/.../common/annotation/RequireGlobalAdmin.java` | 全局 Admin 注解 |
| `SecurityConfig.java` | `backend/.../auth/config/SecurityConfig.java` | Spring Security 配置 |
| `JwtFilter.java` | `backend/.../auth/config/JwtFilter.java` | JWT 过滤器 (75 行) |
| `JwtUtil.java` | `backend/.../common/util/JwtUtil.java` | JWT 签发/解析/校验 (139 行) |
| `ControllerAuthHelper.java` | `backend/.../common/util/ControllerAuthHelper.java` | Controller 鉴权工具 (47 行) |
| `ApiKeyService.java` | `backend/.../auth/service/ApiKeyService.java` | API Key 管理 + scope 校验 |
| `AceService.java` | `backend/.../auth/service/AceService.java` | ACE 矩阵 CRUD |
| `RoleService.java` | `backend/.../auth/service/RoleService.java` | 角色管理 |
| `GroupService.java` | `backend/.../auth/service/GroupService.java` | 用户组 + 层级展开 |
| `MCPAuth.java` | `ai-service/kes_mcp/auth.py` | MCP API Key → JWT 交换 |
| `tools.py` | `ai-service/kes_mcp/tools.py` | MCP Tool 权限交集实现 |
