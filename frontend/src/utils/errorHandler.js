/**
 * 统一 API 错误处理工具。
 *
 * 使用方式：
 *   import { handleError, withError Toast } from '../utils/errorHandler'
 *   try { await someApi() } catch (e) { handleError(e) }
 *
 * 策略：
 *   1. HTTP 4xx/5xx → 由 axios 拦截器已处理（ElMessage.error）
 *   2. 网络错误 → 显示通用网络错误消息
 *   3. 取消操作（ElMessageBox cancel）→ 静默忽略
 */

import { ElMessage } from 'element-plus'

/**
 * 处理来自 API 调用的错误。
 * 网络错误显示提示，用户取消静默忽略，其他由拦截器已处理。
 */
export function handleError(error, fallbackMsg = '操作失败') {
  // 用户取消确认对话框 — 静默忽略
  if (error === 'cancel' || error === 'close') return
  if (error?.message?.includes('cancel')) return

  // 网络错误 — 拦截器未覆盖
  if (error?.code === 'ERR_NETWORK' || error?.message?.includes('Network Error')) {
    ElMessage.error('网络连接失败，请检查网络')
    return
  }

  // 请求超时
  if (error?.code === 'ECONNABORTED') {
    ElMessage.error('请求超时，请稍后重试')
    return
  }

  // 其他错误由拦截器已处理，静默
}

