import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '../api'

/**
 * 认证状态管理 — v4 ACE 企业级权限模型。
 * Space 角色: owner | admin | member
 */
export const useAuthStore = defineStore('auth', () => {
  function safeJsonParse(raw, fallback) {
    try { return JSON.parse(raw || fallback) } catch { return typeof fallback === 'string' ? fallback : fallback }
  }
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const contextToken = ref(localStorage.getItem('context_token') || '')
  const user = ref(safeJsonParse(localStorage.getItem('user'), null))
  const spaces = ref(safeJsonParse(localStorage.getItem('spaces'), []))
  const activeSpace = ref(safeJsonParse(localStorage.getItem('active_space'), null))

  const isLoggedIn = computed(() => !!refreshToken.value)

  const hasActiveSpace = computed(() => !!contextToken.value && !!activeSpace.value)

  // v4: owner | admin | member | guest
  const currentRole = computed(() => activeSpace.value?.role || 'guest')

  // 全局管理员（来自 login 时返回的 user 对象）
  const isGlobalAdmin = computed(() => user.value?.is_global_admin === true)

  // v4 权限快捷判断
  const isOwner = computed(() => currentRole.value === 'owner')
  const isSpaceAdmin = computed(() => currentRole.value === 'owner' || currentRole.value === 'admin')
  const isSpaceMember = computed(() => isSpaceAdmin.value || currentRole.value === 'member')

  async function login(username, password) {
    const res = await authApi.login({ username, password })
    const data = res.data.data
    refreshToken.value = data.refresh_token
    user.value = data.user
    spaces.value = data.user?.spaces || []
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('user', JSON.stringify(data.user))
    localStorage.setItem('spaces', JSON.stringify(spaces.value))
  }

  async function register(username, password, displayName) {
    const res = await authApi.register({ username, password, display_name: displayName })
    return res.data.data
  }

  async function switchSpace(spaceId) {
    const res = await authApi.switchSpace(spaceId, refreshToken.value)
    const data = res.data.data
    contextToken.value = data.access_token
    localStorage.setItem('context_token', data.access_token)
    // v4: role 来自 getSpaces 返回的 space 列表
    const spaceInfo = spaces.value.find(s => s.space_id === spaceId)
    activeSpace.value = {
      space_id: spaceId,
      space_name: spaceInfo?.space_name || '',
      role: spaceInfo?.role || 'member'
    }
    localStorage.setItem('active_space', JSON.stringify(activeSpace.value))
    return activeSpace.value
  }

  function logout() {
    refreshToken.value = ''
    contextToken.value = ''
    user.value = null
    spaces.value = []
    activeSpace.value = null
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('context_token')
    localStorage.removeItem('user')
    localStorage.removeItem('spaces')
    localStorage.removeItem('active_space')
  }

  return {
    refreshToken, contextToken, user, spaces, activeSpace,
    isLoggedIn, hasActiveSpace, currentRole,
    isGlobalAdmin, isOwner, isSpaceAdmin, isSpaceMember,
    login, register, switchSpace, logout
  }
})
