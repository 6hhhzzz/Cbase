/** Auth API — 登录/注册/Token/用户搜索 */
import api from './client.js'

export const authApi = {
  login(credentials) {
    return api.post('/auth/login', credentials, {
      headers: { Authorization: undefined },
    })
  },
  register(data) {
    return api.post('/auth/register', data, {
      headers: { Authorization: undefined },
    })
  },
  getSpaces() {
    return api.get('/auth/spaces')
  },
  switchSpace(spaceId) {
    return api.post('/auth/switch-space', { space_id: spaceId })
  },
  getAccessibleKBs() {
    return api.get('/auth/accessible-kbs')
  },
  changePassword(oldPassword, newPassword) {
    return api.put('/auth/password', { old_password: oldPassword, new_password: newPassword })
  },
}

export const userApi = {
  search(query) {
    return api.get('/auth/users/search', { params: { q: query } })
  },
}
