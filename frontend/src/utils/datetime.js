/**
 * 统一日期时间格式化工具。
 * 所有视图中的 fmtTime 内联实现统一使用此函数。
 */
export function fmtTime(ts) {
  if (!ts) return ''
  return new Date(ts).toLocaleString('zh-CN')
}
