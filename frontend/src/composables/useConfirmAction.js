import { ElMessageBox } from 'element-plus'

/**
 * 操作确认对话框封装。
 * 替换所有视图中重复的 ElMessageBox.confirm() 样板代码。
 */

/**
 * 通用确认对话框。
 * @param {string} message - 确认提示文案
 * @param {string} title  - 对话框标题
 * @returns {Promise<boolean>} true=确认, false=取消
 */
export async function confirmAction(message = '确认执行此操作？', title = '提示') {
  try {
    await ElMessageBox.confirm(message, title, { type: 'warning' })
    return true
  } catch {
    return false
  }
}

/**
 * 删除确认对话框（预置文案）。
 * @param {string} name - 要删除的目标名称
 * @returns {Promise<boolean>} true=确认删除, false=取消
 */
export async function confirmDelete(name = '该项') {
  return confirmAction(`确认删除「${name}」？此操作不可撤销。`, '警告')
}
