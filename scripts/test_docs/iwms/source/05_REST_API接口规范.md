format: html
output: 05_REST_API接口规范.html

# IWMS REST API 接口规范

## 文档信息

- **版本**: v1.0
- **作者**: 陈强（后端组长）
- **日期**: 2026 年 4 月 28 日
- **Base URL**: `https://iwms-api.acme.com/api/v1`

## 一、通用规范

### 1.1 请求格式

- Content-Type: `application/json; charset=utf-8`
- 认证头: `Authorization: Bearer <access_token>`

### 1.2 响应格式

成功响应：
```json
{"code": 0, "message": "ok", "data": {...}}
```

分页响应：
```json
{"code": 0, "data": {"items": [...], "total": 350, "page": 1, "size": 20}}
```

错误响应：
```json
{"code": 401, "message": "未登录或 Token 已过期"}
```

### 1.3 HTTP 状态码

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 400 | 参数校验失败 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 数据冲突（如重复入库单号） |
| 422 | 业务逻辑错误（如库存不足） |
| 500 | 服务器内部错误 |

## 二、入库管理 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /inbound/orders | 创建入库单 | inbound:write |
| GET | /inbound/orders | 入库单列表（分页） | inbound:read |
| GET | /inbound/orders/{id} | 入库单详情 | inbound:read |
| PUT | /inbound/orders/{id}/status | 更新入库单状态 | inbound:write |
| POST | /inbound/orders/{id}/items | 添加入库明细 | inbound:write |
| POST | /inbound/orders/{id}/quality | 质检确认 | inbound:write |
| GET | /inbound/items?batch_no={batch} | 按批次查询入库明细 | inbound:read |
| POST | /inbound/transfer | 创建调拨入库单 | inbound:write |

### POST /inbound/orders 请求示例

```json
{
  "type": "purchase",
  "erp_order_id": "PO-2026-0892",
  "supplier_id": "c7e3d...",
  "warehouse_id": "a1b2c...",
  "items": [
    {"sku_id": "SKU-001", "expected_qty": 100},
    {"sku_id": "SKU-002", "expected_qty": 50}
  ]
}
```

## 三、出库管理 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /outbound/orders | 创建出库单 | outbound:write |
| GET | /outbound/orders | 出库单列表 | outbound:read |
| GET | /outbound/orders/{id} | 出库单详情 | outbound:read |
| POST | /outbound/orders/{id}/approve | 出库审批 | outbound:approve |
| POST | /outbound/waves | 创建波次拣货任务 | outbound:write |
| GET | /outbound/waves/{id}/pick-path | 获取拣货路径 | outbound:read |
| POST | /outbound/packages | 复核打包确认 | outbound:write |
| PUT | /outbound/orders/{id}/express | 回填快递单号 | outbound:write |

### 出库审批流程

```
POST /outbound/orders/{id}/approve
Body: {"action": "approve", "comment": "金额在权限范围内"}
```

审批规则见《需求规格说明书》2.2.2 节。不同金额对应不同审批层级：
- ≤5000 元：系统自动通过
- 5000-50000 元：仓库主管审批
- 50000-200000 元：仓库主管 + 财务审批
- >200000 元：仓库主管 + 财务 + 总经理

## 四、库存管理 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /inventory?sku_id={sku} | 查询实时库存 | inventory:read |
| GET | /inventory/batch/{batch_no} | 批次溯源查询 | inventory:read |
| POST | /inventory/count | 创建盘点任务 | inventory:write |
| PUT | /inventory/count/{id} | 提交盘点结果 | inventory:write |
| GET | /inventory/alerts | 获取库存预警列表 | inventory:read |
| GET | /inventory/logs | 库存变更日志 | inventory:read |

## 五、权限管理 API

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /auth/login | 用户登录 | 无 |
| POST | /auth/refresh | 刷新 Token | 无 |
| GET | /auth/users | 用户列表 | auth:read |
| POST | /auth/users | 创建用户 | auth:write |
| PUT | /auth/users/{id} | 编辑用户 | auth:write |
| DELETE | /auth/users/{id} | 禁用用户 | auth:write |
| GET | /auth/roles | 角色列表 | auth:read |
| POST | /auth/roles | 创建角色 | auth:write |
| PUT | /auth/roles/{id}/permissions | 分配权限 | auth:write |
| GET | /auth/audit-logs | 查询审计日志 | auth:read |

权限模型详情见《权限模块设计文档》。

## 六、报表 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /reports/inventory-turnover | 库存周转率报表 |
| GET | /reports/inbound-outbound-stats | 出入库统计 |
| GET | /reports/picking-efficiency | 拣货效率报表 |
| GET | /reports/slow-moving | 呆滞库存分析 |
| GET | /reports/export/{type} | 导出报表 Excel/PDF |

## 七、认证流程

1. **POST /auth/login** → 返回 `{access_token, refresh_token}`
2. 后续请求携带 `Authorization: Bearer <access_token>`
3. Access Token 过期（30min）→ **POST /auth/refresh** 换发新 Token
4. Refresh Token 过期（7d）→ 需重新登录

### JWT Token 结构

```json
{
  "sub": "user-uuid",
  "username": "zhangwei",
  "role": "warehouse_manager",
  "permissions": ["inbound:read", "inbound:write", "outbound:read"],
  "iat": 1715900000,
  "exp": 1715901800
}
```
