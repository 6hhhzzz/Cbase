<template>
  <div class="doc-layout">
    <div class="doc-header">
      <h2>审批管理</h2>
      <div>
        <el-button @click="router.push(`/app/${route.params.spaceId}/documents`)">
          返回文档管理
        </el-button>
      </div>
    </div>

    <!-- KB 选择器 -->
    <div style="margin-bottom:16px">
      <el-select v-model="activeKbId" placeholder="选择知识库" style="width:280px" @change="loadApprovals">
        <el-option v-for="kb in kbs" :key="kb.kb_id" :label="kb.name || '未命名'" :value="kb.kb_id" />
      </el-select>
    </div>

    <!-- 审批列表 -->
    <el-table :data="approvals" stripe v-loading="loading" style="width:100%">
      <el-table-column prop="filename" label="文件名" min-width="180" />
      <el-table-column label="操作类型" width="90">
        <template #default="{ row }">
          <el-tag :type="actionTypeTag(row.action_type)" size="small">
            {{ actionTypeText(row.action_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="file_type" label="文件类型" width="80" />
      <el-table-column prop="submitted_by" label="提交者" width="160" />
      <el-table-column label="提交时间" width="180">
        <template #default="{ row }">
          {{ fmtTime(row.submitted_at) || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'pending' ? 'warning' : row.status === 'approved' ? 'success' : 'danger'">
            {{ statusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <el-button type="primary" size="small" text @click="handleView(row.document_id)">
            查看
          </el-button>
          <template v-if="row.status === 'pending' && authStore.isSpaceAdmin">
            <el-button type="success" size="small" :loading="approving === row.approval_id" @click="handleApprove(row)">
              通过
            </el-button>
            <el-button type="danger" size="small" @click="showRejectDialog(row)">
              打回
            </el-button>
          </template>
          <span v-else style="color:#909399">已处理</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="approvals.length === 0 && !loading" style="text-align:center;color:#909399;padding:40px">
      暂无待审批文档
    </div>

    <!-- 打回对话框 -->
    <el-dialog v-model="rejectDialog.visible" title="打回文档" width="400px">
      <p>确认打回「{{ rejectDialog.filename }}」？</p>
      <el-input v-model="rejectDialog.comment" type="textarea"
        placeholder="打回原因（可选）" :rows="3" />
      <template #footer>
        <el-button @click="rejectDialog.visible = false">取消</el-button>
        <el-button type="danger" :loading="rejectDialog.loading" @click="handleReject">
          确认打回
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { documentsApi } from '../api'
import { ElMessage } from 'element-plus'
import { fmtTime } from '../utils/datetime'
import { APPROVAL_STATUS_TEXT_MAP, APPROVAL_ACTION_TEXT_MAP, APPROVAL_ACTION_TAG_MAP } from '../utils/constants'
import { useKbFetcher } from '../composables/useKbFetcher'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const { kbs, firstKbId, loadKBs } = useKbFetcher({ autoSelectFirst: true })

const activeKbId = ref(firstKbId.value || '')
const approvals = ref([])
const loading = ref(false)
const approving = ref(null)

const rejectDialog = reactive({
  visible: false,
  loading: false,
  approvalId: '',
  filename: '',
  comment: '',
})

onMounted(async () => {
  await loadKBs()
  if (!activeKbId.value && firstKbId.value) activeKbId.value = firstKbId.value
  loadApprovals()
})

async function loadApprovals() {
  if (!activeKbId.value) return
  loading.value = true
  try {
    const res = await documentsApi.getApprovals({ kb_id: activeKbId.value })
    approvals.value = res.data.data || []
  } catch {
    approvals.value = []
  } finally {
    loading.value = false
  }
}

async function handleApprove(row) {
  approving.value = row.approval_id
  try {
    await documentsApi.approve(row.approval_id)
    ElMessage.success(`「${row.filename}」已通过审批`)
    loadApprovals()
  } catch { /* interceptor */ }
  finally { approving.value = null }
}

function showRejectDialog(row) {
  rejectDialog.approvalId = row.approval_id
  rejectDialog.filename = row.filename
  rejectDialog.comment = ''
  rejectDialog.visible = true
}

async function handleReject() {
  rejectDialog.loading = true
  try {
    await documentsApi.reject(rejectDialog.approvalId, rejectDialog.comment)
    ElMessage.success(`「${rejectDialog.filename}」已打回`)
    rejectDialog.visible = false
    loadApprovals()
  } catch {
    ElMessage.error('审批操作失败')
  } finally {
    rejectDialog.loading = false
  }
}

function handleView(docId) {
  window.open(documentsApi.viewUrl(docId), '_blank')
}

function actionTypeText(type) { return APPROVAL_ACTION_TEXT_MAP[type] || type || '上传' }
function actionTypeTag(type) { return APPROVAL_ACTION_TAG_MAP[type] || 'info' }
function statusText(status) { return APPROVAL_STATUS_TEXT_MAP[status] || status }
</script>

<style scoped>
.doc-layout {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}
.doc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.doc-header h2 {
  margin: 0;
}
</style>
