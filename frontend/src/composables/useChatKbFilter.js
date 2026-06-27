import { ref } from 'vue'

/**
 * Chat KB 筛选 Composable。
 * 管理跨KB联合查询时的 KB 排除列表和筛选模式。
 */
export function useChatKbFilter() {
  const kbMode = ref('all')      // 'all' | 'custom'
  const excludedKbIds = ref([])  // 被排除的 KB ID 列表
  const expanded = ref(false)    // KB 列表是否展开

  function isExcluded(kbId) {
    return excludedKbIds.value.includes(kbId)
  }

  function toggleKb(kbId) {
    const idx = excludedKbIds.value.indexOf(kbId)
    if (idx >= 0) {
      excludedKbIds.value.splice(idx, 1)
    } else {
      excludedKbIds.value.push(kbId)
    }
    kbMode.value = excludedKbIds.value.length > 0 ? 'custom' : 'all'
  }

  function resetKbFilter() {
    excludedKbIds.value = []
    kbMode.value = 'all'
  }

  return { kbMode, excludedKbIds, expanded, isExcluded, toggleKb, resetKbFilter }
}
