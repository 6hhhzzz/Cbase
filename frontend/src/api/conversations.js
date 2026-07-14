/** Conversations API */
import api from './client.js'

export const conversationsApi = {
  list(kbId) {
    return api.get('/conversations', { params: { kb_id: kbId } })
  },
  messages(id) {
    return api.get(`/conversations/${id}/messages`)
  },
  delete(id) {
    return api.delete(`/conversations/${id}`)
  },
}
