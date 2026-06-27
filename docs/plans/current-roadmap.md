# 项目计划文档 — 2026-06-25

---

## 当前优先事项

```
P0 (进行中):  MCP 读能力完善 — read_document + ask_expert + Resources
P1 (下一项):  LDAP/AD 账号同步 — 解决企业接入的最大阻塞
P2 (之后):    OIDC Federation — 现代企业标准 SSO
```

---

## 已完成的 Agent 写能力设计（延后到 v10）

> 让外部 Agent 管理/上传知识库文档的能力，含五层防垃圾机制。设计已完成，待项目有稳定用户后实施。

### 能力分级

| 级别 | 能力 | 风险 | 适用 Agent |
|------|------|------|-----------|
| **L0 只读** | search + read + ask | 无 | 通用问答 Agent |
| **L1 提议** | 提交文档草稿，需人工审批 | 低 | 会议纪要 Agent |
| **L2 受信写入** | 直接上传到指定 KB，自动入库 | 中 | CI 文档生成 |
| **L3 管理** | 更新/删除已有文档 | 高 | 暂不开放 |

### 五层防护

1. **权限** — API Key `permission` 字段: `read` / `read_write`
2. **范围** — 只能写到有 Editor 权限的 KB（交集）
3. **内容校验** — 文件类型白名单/大小限制/最小文本量/自然语言检测/重复检测
4. **审批门** — L1 模式提交后走 DocumentApproval 审批流
5. **审计** — 所有 Agent 写操作完整记录到 admin_action_logs

### 新增 MCP Tools（未来）

- `propose_document` — L1 提议上传（审批门）
- `upload_document` — L2 直接上传（需 read_write Key + 质量校验）

---

## 其他已完成规划（按需启动）

| 规划 | 状态 | 启动条件 |
|------|------|---------|
| Agent 写能力 (v10) | 📋 设计完成 | 有稳定用户反馈需求 |
| OIDC Federation | 📋 设计完成 | 第一个 Okta/Azure AD 客户 |
| LDAP/AD 同步 | 📋 设计完成 | P0 完成后立即启动 |
| PermissionResolver 接口 | 📋 设计完成 | 有租户/自定义权限需求 |
| SemanticChunker | 📋 存根就绪 | Phase 2 |
| 多租户 | 📋 远期 | SaaS 化部署 |
