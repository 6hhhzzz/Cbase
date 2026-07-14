/** Groups API */
import api from './client.js'

export const groupsApi = {
  list(params) {
    return api.get('/groups', { params })
  },
  create(data) {
    return api.post('/groups', data)
  },
  update(id, data) {
    return api.put(`/groups/${id}`, data)
  },
  delete(id) {
    return api.delete(`/groups/${id}`)
  },
  getMembers(id) {
    return api.get(`/groups/${id}/members`)
  },
  addMember(id, userId) {
    return api.post(`/groups/${id}/members`, { user_id: userId })
  },
  removeMember(id, userId) {
    return api.delete(`/groups/${id}/members/${userId}`)
  },
  getAdmins(id) {
    return api.get(`/groups/${id}/admins`)
  },
  addAdmin(id, userId) {
    return api.post(`/groups/${id}/admins`, { user_id: userId })
  },
  removeAdmin(id, userId) {
    return api.delete(`/groups/${id}/admins/${userId}`)
  },
}
