<template>
  <div class="doc-layout">
    <div class="doc-header">
      <h2>文档管理</h2>
      <div>
        <el-button @click="router.push(`/app/${route.params.spaceId}/chat`)">返回对话</el-button>
        <el-button v-if="authStore.isSpaceAdmin"
          @click="router.push(`/app/${route.params.spaceId}/approvals`)">审批管理</el-button>
        <el-button v-if="authStore.isSpaceMember" type="primary" @click="showUpload = true">上传文档</el-button>
      </div>
    </div>

    <el-table :data="documents" stripe v-loading="loading" style="width:100%">
      <el-table-column prop="filename" label="文件名" min-width="180" />
      <el-table-column prop="doc_version" label="版本" width="100" />
      <el-table-column prop="file_type" label="类型" width="70" />
      <el-table-column label="大小" width="90">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column label="KB" width="140">
        <template #default="{ row }">
          <span style="font-size:12px;color:#909399">{{ kbName(row.kb_id) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="入库状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType(row.ingest_status)">{{ statusText(row.ingest_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="生效日期" width="110">
        <template #default="{ row }">
          <span v-if="row.doc_effective_date">{{ row.doc_effective_date }}</span>
          <span v-else style="color:#999">-</span>
        </template>
      </el-table-column>
      <el-table-column label="失效日期" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.doc_expiry_date" size="small" type="warning">{{ row.doc_expiry_date }}</el-tag>
          <span v-else style="color:#999;font-size:12px">长期有效</span>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) || '-' }}</template>
      </el-table-column>
      <el-table-column v-if="authStore.isSpaceAdmin" label="继承权限" width="110" align="center">
        <template #default="{ row }">
          <el-switch :model-value="row.inherit_permissions !== false"
            @change="(val) => toggleInherit(row, val)" active-text="KB" inactive-text="隔离" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click="handleView(row.id)">查看</el-button>
          <el-button type="warning" size="small" text @click="openUpdateDialog(row)">更新</el-button>
          <el-button type="danger" size="small" text @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination v-model:current-page="page" :total="total" :page-size="pageSize"
        layout="total, prev, pager, next" @current-change="onPageChange" />
    </div>

    <UploadDialog v-model="showUpload" :kbs="kbs" :uploading="uploading" @upload="onUpload" />
    <UpdateDialog v-model="showUpdate" :target="updateTarget" :updating="updating"
      :is-admin="authStore.isSpaceAdmin" @update="loadDocuments(currentKbId)" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { documentsApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fmtTime } from '../utils/datetime'
import { INGEST_STATUS_TEXT_MAP, INGEST_STATUS_TYPE_MAP } from '../utils/constants'
import { useKbFetcher } from '../composables/useKbFetcher'
import { useDocuments } from '../composables/useDocuments'
import UploadDialog from '../components/documents/UploadDialog.vue'
import UpdateDialog from '../components/documents/UpdateDialog.vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const { kbs, loadKBs, kbName } = useKbFetcher({ autoSelectFirst: true })
const { documents, loading, page, pageSize, total, uploading,
  loadDocuments, doUpload, doDelete, toggleInherit, formatSize } = useDocuments()

const currentKbId = ref('')
const showUpload = ref(false)
const showUpdate = ref(false)
const updating = ref(false)
const updateTarget = reactive({ id: '', filename: '' })

function statusType(s) { return INGEST_STATUS_TYPE_MAP[s] || 'info' }
function statusText(s) { return INGEST_STATUS_TEXT_MAP[s] || s }

onMounted(async () => {
  await loadKBs()
  if (kbs.value.length > 0) currentKbId.value = kbs.value[0].kb_id
  loadDocuments(currentKbId.value)
})

function onPageChange(p) {
  page.value = p
  loadDocuments(currentKbId.value)
}

async function onUpload(form) {
  const formData = new FormData()
  formData.append('file', form.file)
  formData.append('kb_id', form.kb_id || currentKbId.value)
  if (form.effective_date) formData.append('effective_date', form.effective_date)
  if (form.expiry_date) formData.append('expiry_date', form.expiry_date)
  if (form.version) formData.append('version', form.version)
  const ok = await doUpload(formData)
  if (ok) {
    showUpload.value = false
    loadDocuments(currentKbId.value)
  }
}

function openUpdateDialog(row) {
  updateTarget.id = row.id
  updateTarget.filename = row.filename
  showUpdate.value = true
}

async function handleDelete(docId) {
  try {
    await ElMessageBox.confirm('确认删除该文档？', '提示', { type: 'warning' })
    await doDelete(docId)
    loadDocuments(currentKbId.value)
  } catch { /* cancel or error */ }
}

function handleView(docId) {
  window.open(documentsApi.viewUrl(docId), '_blank')
}
</script>

<style scoped>
.doc-layout { max-width: 1200px; margin: 0 auto; padding: 24px; }
.doc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.doc-header h2 { margin: 0; }
.pagination { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
