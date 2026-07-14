/** Documents API */
import api from './client.js'

export const documentsApi = {
  list(params) {
    return api.get('/documents', { params })
  },
  upload(formData, onProgress) {
    return api.post('/documents', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    })
  },
  update(docId, formData, onProgress) {
    return api.put(`/documents/${docId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: onProgress,
    })
  },
  delete(docId) {
    return api.delete(`/documents/${docId}`)
  },
  batchDelete(docIds) {
    return api.delete('/documents/batch', { data: docIds })
  },
  batchPermanentDelete(docIds) {
    return api.delete('/documents/batch/permanent', { data: docIds })
  },
  updateMetadata(docId, metadata) {
    return api.put(`/documents/${docId}/metadata`, metadata)
  },
  restore(docId) {
    return api.post(`/documents/${docId}/restore`)
  },
  permanentDelete(docId) {
    return api.delete(`/documents/${docId}/permanent`)
  },
  getApprovals() {
    return api.get('/documents/approvals')
  },
  approve(id) {
    return api.post(`/documents/approvals/${id}/approve`)
  },
  reject(id, comment) {
    return api.post(`/documents/approvals/${id}/reject`, { comment })
  },
  viewUrl(docId, token) {
    return `/api/documents/${docId}/file?token=${encodeURIComponent(token)}`
  },
}
