/**
 * 全局常量映射表。
 * 所有视图中内联的角色标签、状态映射统一从这里引用，
 * 避免硬编码重复和后端变更时多处修改。
 */

/** Space / KB 角色中文标签 */
export const ROLE_LABEL_MAP = {
  owner: '拥有者',
  admin: '管理员',
  member: '成员',
}

/** 文档入库状态 → 中文文案 */
export const INGEST_STATUS_TEXT_MAP = {
  pending: '待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
}

/** 文档入库状态 → Element Plus tag type */
export const INGEST_STATUS_TYPE_MAP = {
  pending: 'info',
  processing: 'warning',
  completed: 'success',
  failed: 'danger',
}

/** 审批状态 → 中文文案 */
export const APPROVAL_STATUS_TEXT_MAP = {
  pending: '待审批',
  approved: '已通过',
  rejected: '已打回',
}

/** 审批操作类型 → 中文文案 */
export const APPROVAL_ACTION_TEXT_MAP = {
  upload: '上传',
  update: '更新',
  delete: '删除',
}

/** 审批操作类型 → Element Plus tag type */
export const APPROVAL_ACTION_TAG_MAP = {
  upload: 'primary',
  update: 'warning',
  delete: 'danger',
}

