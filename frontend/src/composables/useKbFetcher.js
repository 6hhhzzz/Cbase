import { ref } from 'vue'
import { authApi } from '../api'

/**
 * KB 列表获取与缓存 Composable。
 * 封装 authApi.getAccessibleKBs() 调用，替换 Chat / Documents / Approvals 中的重复实现。
 *
 * @param {object} options
 * @param {boolean} options.autoSelectFirst - 是否自动选中第一个 KB（Documents 视图使用）
 */
export function useKbFetcher({ autoSelectFirst = false } = {}) {
  const kbs = ref([])
  const loading = ref(false)
  /** 自动选中的第一个 KB ID，仅 autoSelectFirst 模式有效 */
  const firstKbId = ref('')

  async function loadKBs() {
    try {
      loading.value = true
      const res = await authApi.getAccessibleKBs()
      kbs.value = res.data.data || []
      if (autoSelectFirst && kbs.value.length > 0) {
        firstKbId.value = kbs.value[0].kb_id
      }
    } catch {
      /* 非致命 — 拦截器已提示 */
    } finally {
      loading.value = false
    }
  }

  /** 根据 kb_id 查找 KB 名称 */
  function kbName(kbId) {
    const kb = kbs.value.find(k => k.kb_id === kbId)
    return kb ? kb.name : '未知知识库'
  }

  return { kbs, loading, firstKbId, loadKBs, kbName }
}
