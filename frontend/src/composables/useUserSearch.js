import { ref } from 'vue'
import { userApi } from '../api'

/**
 * 远程用户搜索 Composable。
 * 封装 userApi.search() 调用和 userOptions 状态。
 * 被 SpaceSettings（添加管理员）和 GroupManagement（添加成员/管理员）共享。
 */
export function useUserSearch() {
  const userOptions = ref([])
  const searching = ref(false)

  async function searchUsers(query) {
    if (!query || query.trim().length < 1) {
      userOptions.value = []
      return
    }
    try {
      searching.value = true
      const res = await userApi.search(query.trim())
      userOptions.value = (res.data.data || []).map(u => ({
        user_id: u.user_id,
        username: u.username,
        display_name: u.display_name || '',
      }))
    } catch {
      userOptions.value = []
    } finally {
      searching.value = false
    }
  }

  return { userOptions, searching, searchUsers }
}
