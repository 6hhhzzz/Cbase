# ADR-002: v4 ACE 企业级权限模型

**状态**: 已接受
**日期**: 2026-06-18
**决策者**: 项目 Owner

## 背景

v3 RBAC 模型（Space → KB → Document）使用 `space_members`（用户→Space 直接关联）和 `kb_members`（用户→KB 直接关联）管理权限。随着系统向企业级演进，v3 模型暴露出以下局限：

1. **无法表达组织架构**：权限是「用户→KB」的直接映射，每增加一个用户就要逐个 KB 配置
2. **无法批量授权**：当整个部门需要访问某个 KB 时，必须逐一添加成员
3. **无法表达显式拒绝**：没有 deny 语义，只能通过「不授权」来实现限制
4. **Space 管理员单点故障**：管理员只通过 space_members.role='admin' 管理，缺乏 owner/admin 分级

## 决策

采用 **ACE（Access Control Entry）企业级权限模型**，核心理念：

> "成员归属于用户组，文档归属于KB，管理员配置用户组与KB之间的关系（带上角色）"

### 核心实体

| 实体 | 表 | 说明 |
|------|-----|------|
| 用户组 | `user_groups` | 全局可嵌套，`is_system_admin` 标记超级管理员组 |
| 组成员 | `user_group_members` | 用户→组 归属关系 |
| 角色 | `roles` | 可自定义的 KB 级别权限套餐（permissions JSONB） |
| Space 管理员 | `space_admins` | 直接关联 User（非组），分 owner/admin 两级 |
| Space 准入组 | `space_groups` | 将全局用户组分配到 Space |
| ACE | `access_control_entries` | 核心权限：principal → resource → role + effect |

### 关键设计原则

1. **普通成员靠组**：通过 `space_groups` 批量管理，管理员不需要逐个添加用户
2. **管理员靠人**：`space_admins` 直接关联 User，防止责任模糊和单点故障
3. **Owner/Admin 分级**：Owner 可删 Space、转让所有权；Admin 可管 KB 和准入组
4. **Deny 覆盖 Allow**：无论优先级，deny 始终胜出
5. **组嵌套继承**：子组成员自动成为父组成员（向上展开），继承父组的 ACE 权限
6. **KB visibility 保留**：`space_wide` 作为便捷的全员可见快捷方式
7. **安全边界不变**：Java 计算 kb_ids，Python 机械执行 `WHERE kb_id = ANY($1)`

### 与 v3 的关键差异

| 维度 | v3 | v4 |
|------|-----|-----|
| Space 成员 | space_members (user→space) | space_admins + space_groups |
| KB 权限 | kb_members (user→kb) | ACE 矩阵 (group/user → kb → role) |
| 管理员模型 | 单一 admin 角色 | owner + admin 分级 |
| 显式拒绝 | 不支持 | deny effect |
| 组管理 | 无 | 全局可嵌套用户组 |
| 角色自定义 | KB 成员固定角色 | 管理员可自定义权限套餐 |

## 后果

### 正面影响
- 管理员只需维护「组↔KB↔角色」矩阵，大幅降低运维成本
- 支持企业级组织架构（部门→小组→个人）
- Owner/Admin 分级防止权限滥用和单点故障
- Deny 语义使安全策略更精准

### 负面影响
- 初始配置复杂度增加（需先建组、分配准入组、配置 ACE）
- Phase 1 仅完成后端，前端管理界面需 Phase 2 才能使用
- 旧数据不兼容，需手动迁移

### 迁移策略
- 旧表 `space_members`、`kb_members` 直接删除
- 通过 `migration-v4-ace-permission.sql` 创建新表
- 用户手动重新填入组、Space 配置和 ACE 规则

## 参考

- [ADR-001: Space/KB Permission Model](./001-space-kb-permission-model.md)
- `scripts/migration-v4-ace-permission.sql` — 数据库迁移脚本
- `backend/.../auth/service/PermissionService.java` — 权限校验入口
- `backend/.../auth/service/AuthService.java` — `resolveAccessibleKbIds()` 核心算法
