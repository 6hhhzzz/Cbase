import { ref } from 'vue'
import { documentsApi } from '../api'
import { ElMessage } from 'element-plus'

/**
 * 文档管理 Composable — 文档列表、上传、更新、删除、元数据编辑。
 */
export function useDocuments() {
  const documents = ref([])
  const loading = ref(false)
  const page = ref(1)
  const pageSize = ref(20)
  const total = ref(0)

  // ---- 上传 ----
  const uploading = ref(false)

  async function loadDocuments(kbId) {
    loading.value = true
    try {
      const params = { page: page.value, page_size: pageSize.value, kb_id: kbId }
      const res = await documentsApi.list(params)
      const data = res.data.data
      documents.value = data.items || []
      total.value = data.total || 0
    } finally {
      loading.value = false
    }
  }

  async function doUpload(formData) {
    uploading.value = true
    try {
      await documentsApi.upload(formData)
      ElMessage.success('上传成功，文档将异步入库')
      return true
    } catch {
      ElMessage.error('上传失败，请稍后重试')
      return false
    } finally {
      uploading.value = false
    }
  }

  // ---- 删除 ----
  async function doDelete(docId) {
    const res = await documentsApi.delete(docId)
    const body = res.data
    if (body.data?.action === 'pending_approval') {
      ElMessage.info(body.data.message || '删除请求已提交，待管理员审批')
    } else {
      ElMessage.success('删除成功')
    }
  }

  // ---- 元数据 ----
  async function toggleInherit(doc, val) {
    try {
      await documentsApi.updateMetadata(doc.id, { inherit_permissions: val })
      doc.inherit_permissions = val
      ElMessage.success(val ? '已恢复继承 KB 权限' : '已阻断继承，请前往 ACE 矩阵配置文档权限')
    } catch { /* handled by interceptor */ }
  }

  // ---- 工具 ----
  function formatSize(bytes) {
    if (!bytes) return '-'
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / 1024 / 1024).toFixed(1) + ' MB'
  }

  return {
    documents, loading, page, pageSize, total,
    uploading, loadDocuments, doUpload, doDelete, toggleInherit, formatSize,
  }
}
