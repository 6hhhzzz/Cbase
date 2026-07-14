/** Roles API */
import api from './client.js'

export const rolesApi = {
  list() {
    return api.get('/roles')
  },
  create(data) {
    return api.post('/roles', data)
  },
  update(id, data) {
    return api.put(`/roles/${id}`, data)
  },
  delete(id) {
    return api.delete(`/roles/${id}`)
  },
}
