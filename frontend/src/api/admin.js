/** Admin API — 全局管理 + 模型配置 */
import api from './client.js'

export const adminApi = {
  // ---- 空间管理 ----
  getAllSpaces() {
    return api.get('/admin/spaces')
  },
  archiveSpace(spaceId) {
    return api.post(`/admin/spaces/${spaceId}/archive`)
  },
  deleteSpace(spaceId) {
    return api.delete(`/admin/spaces/${spaceId}`)
  },
  restoreSpace(spaceId) {
    return api.post(`/admin/spaces/${spaceId}/restore`)
  },

  // ---- 用户管理 ----
  listUsers() {
    return api.get('/admin/users')
  },
  setGlobalAdmin(userId, value) {
    return api.put(`/admin/users/${userId}/global-admin`, { global_admin: value })
  },
  createUser(data) {
    return api.post('/admin/users', data)
  },
  updateUser(id, data) {
    return api.put(`/admin/users/${id}`, data)
  },
  setUserStatus(id, status) {
    return api.put(`/admin/users/${id}/status`, { status })
  },
  batchImportUsers(formData) {
    return api.post('/admin/users/batch', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

}

export const modelAdminApi = {
  // ---- 供应商 ----
  listProviders() {
    return api.get('/admin/models/providers')
  },
  createProvider(data) {
    return api.post('/admin/models/providers', data)
  },
  updateProvider(id, data) {
    return api.put(`/admin/models/providers/${id}`, data)
  },
  deleteProvider(id) {
    return api.delete(`/admin/models/providers/${id}`)
  },

  // ---- 模型 ----
  listConfigs(providerId) {
    return api.get('/admin/models/configs', { params: { provider_id: providerId } })
  },
  createConfig(data) {
    return api.post('/admin/models/configs', data)
  },
  updateConfig(id, data) {
    return api.put(`/admin/models/configs/${id}`, data)
  },
  deleteConfig(id) {
    return api.delete(`/admin/models/configs/${id}`)
  },

  // ---- 映射 ----
  getAssignments() {
    return api.get('/admin/models/assignments')
  },
  updateAssignments(data) {
    return api.put('/admin/models/assignments', data)
  },

  // ---- 发现/测试 ----
  discover(providerId) {
    return api.post(`/admin/models/discover/${providerId}`)
  },
  test(providerId) {
    return api.post(`/admin/models/test/${providerId}`)
  },

  // ---- 配置中心 ----
  getConfig() {
    return api.get('/admin/models/config')
  },
  updateConfig(rawYaml) {
    return api.put('/admin/models/config', rawYaml, {
      headers: { 'Content-Type': 'application/json' },
    })
  },
}
