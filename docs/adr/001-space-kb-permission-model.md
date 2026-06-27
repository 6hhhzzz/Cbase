# ADR-001: Space/KB 权限模型与扩展架构

> 状态: **已接受** | 日期: 2026-06-16 | 决策者: 项目作者

## 背景

系统最初设计了 Space → KB → Document 三层 RBAC，内置 admin/member/editor/viewer 四种角色。在实际使用和测试中发现：(1) 角色过多但大部分未生效；(2) KB 级角色分层增加了复杂度但未带来实际价值；(3) 扩展点（如 `kb_members.permissions` JSONB）建了但从未使用。

需要重新审视权限模型，同时为未来的自定义能力（自定义角色、自定义字段、可插拔检索策略、MCP 服务）确定扩展架构方向。

## 决策

### 1. 组织映射：Space 扁平化

Space 之间不设层级关系。类型区分通过 `type_label`（如"部门""项目""客户"）和 `metadata` JSONB 扩展字段实现。后续如需层级，可通过 metadata 中的 `parent_space_id` 做应用层软层级，不破坏核心模型。

### 2. 权限模型：Space 管操作、KB 管可见性

```
Space 层（管操作权限）
  ├ admin       — 管理成员、创建/删除 KB、审批文档
  ├ member      — 上传文档、查看文档、聊天
  └ 自定义角色   — 企业按需定义，如 "external_auditor"（只读）

KB 层（管可见性）
  └ visibility + kb_members 名单
       ├ space_wide  — Space 全员可见
       └ restricted  — 仅指定成员可见（kb_members 无角色分层，纯名单）
```

**文档层（管单文档可见性）：同一套模式往下递推**

```
document_meta.visibility:
  "inherit"    → 跟着 KB 走（默认，不改任何行为）
  "restricted" → 仅 doc_members 中的用户可看

doc_members: doc_id + user_id（纯名单，无角色）
```

规则：`文档可见 = (KB 有权限) AND (文档 visibility = inherit OR 用户在 doc_members 中)`。文档只能收窄不能放宽。

检索时 Python SQL 加过滤：排除当前用户不可见的文档。Java 在 FilterParams 中传入 userId，Python 机械执行。

**不再设 KB 内部角色分层。** KB 成员名单只管"能不能看"，操作权限由 Space 角色统一决定。

**权限模型：`resource:action`（如 `document:read`、`kb:manage`）。** 自定义角色通过 `role_definitions` 表定义，无需改代码。

### 3. 文档生命周期

- **审批**：硬需求。上传、更新、删除均触发审批流程，记录审计日志
- **生效/失效日期**：过期文档检索自动排除（`expiry_date IS NULL OR expiry_date > NOW()`），用户可手动查看过期文档
- **版本化**：每次修改 = 新版本，完整文件存储（非 diff），旧版本 chunks 标记 inactive 但保留在 DB 可回溯

### 4. 检索策略：KB 级别可配置

入库参数（chunk_size、overlap、LLM 增强开关）和查询默认值（top_k、Reranker 开关）在 KB 级别配置。查询时用户可临时调 top_k 和排除 KB。

代码层面每个处理阶段（解析、切片、embedding、检索、生成）使用接口隔离，为未来 Pipeline 编排留扩展点。

### 5. 信息分类：KB + metadata

KB = 粗分类 + 权限边界。细粒度标签通过 metadata JSONB 实现，不建独立的跨 KB 标签系统。

### 6. 产品边界：L1 问答 + MCP 服务

产品核心 = 文档检索基础设施。L1 问答是自带的人机交互界面。MCP 服务是给外部 AI Agent 的编程接口。L2-L5（摘要、嵌入流程、主动推送等）由外部 Agent 通过 MCP 消费，不在产品范围内。

## 影响

- 删除 KB 内部角色分层（admin/editor/viewer），简化 kb_members 为纯成员名单
- `document_meta` 新增 `visibility` 列（默认 `inherit`）+ 新增 `doc_members` 表（纯名单）
- Python 检索 SQL 需增加文档级可见性过滤（传入 userId）
- 新增 `role_definitions` 表支持自定义角色
- 原有 `kb_members.permissions` JSONB 列改为由 role 决定
- 检索管道需重构为 stage 接口（留扩展点，非立即实现完整 Pipeline）

## 取代

本 ADR 取代 PROJECT_GOALS.md 中关于 "KB 级别 admin/editor/viewer" 的旧描述。
