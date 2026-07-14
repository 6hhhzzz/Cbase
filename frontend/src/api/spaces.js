/** Space API */
import api from './client.js'

export const spaceApi = {
  create(data) {
    return api.post('/spaces', data)
  },
  getAdmins(spaceId) {
    return api.get(`/spaces/${spaceId}/admins`)
  },
  addAdmin(spaceId, userId) {
    return api.post(`/spaces/${spaceId}/admins`, { user_id: userId })
  },
  removeAdmin(spaceId, userId) {
    return api.delete(`/spaces/${spaceId}/admins/${userId}`)
  },
  transferOwnership(spaceId, userId) {
    return api.post(`/spaces/${spaceId}/transfer-ownership`, { user_id: userId })
  },
  getGroups(spaceId) {
    return api.get(`/spaces/${spaceId}/groups`)
  },
  addGroup(spaceId, groupId) {
    return api.post(`/spaces/${spaceId}/groups`, { group_id: groupId })
  },
  removeGroup(spaceId, groupId) {
    return api.delete(`/spaces/${spaceId}/groups/${groupId}`)
  },
  getAces(spaceId, resourceType) {
    return api.get(`/spaces/${spaceId}/aces`, { params: { resource_type: resourceType } })
  },
  createAce(spaceId, ace) {
    return api.post(`/spaces/${spaceId}/aces`, ace)
  },
  updateAce(spaceId, aceId, ace) {
    return api.put(`/spaces/${spaceId}/aces/${aceId}`, ace)
  },
  deleteAce(spaceId, aceId) {
    return api.delete(`/spaces/${spaceId}/aces/${aceId}`)
  },
  listKbs(spaceId) {
    return api.get(`/spaces/${spaceId}/kbs`)
  },
  createKb(spaceId, data) {
    return api.post(`/spaces/${spaceId}/kbs`, data)
  },
  updateKb(spaceId, kbId, data) {
    return api.put(`/spaces/${spaceId}/kbs/${kbId}`, data)
  },
  deleteKb(spaceId, kbId, permanent) {
    return api.delete(`/spaces/${spaceId}/kbs/${kbId}`, { params: { permanent } })
  },
  restoreKb(spaceId, kbId) {
    return api.post(`/spaces/${spaceId}/kbs/${kbId}/restore`)
  },
  getTrash(spaceId) {
    return api.get(`/spaces/${spaceId}/trash`)
  },
  getAuditLogs(spaceId, params) {
    return api.get(`/spaces/${spaceId}/audit-logs`, { params })
  },
}
