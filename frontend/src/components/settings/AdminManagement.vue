<template>
  <div>
    <div class="section-header">
      <h3>管理员管理</h3>
      <el-button type="primary" size="small" @click="openAddDialog">添加管理员</el-button>
    </div>
    <el-table :data="admins" stripe>
      <el-table-column label="用户" min-width="180">
        <template #default="{ row }">
          {{ row.username || row.user_id }}<br/><small style="color:#999">{{ row.display_name }}</small>
        </template>
      </el-table-column>
      <el-table-column prop="role" label="角色" width="100">
        <template #default="{ row }">
          <el-tag :type="row.role === 'owner' ? 'danger' : 'warning'" size="small">
            {{ row.role === 'owner' ? '拥有者' : '管理员' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="加入时间" width="180">
        <template #default="{ row }">{{ fmtTime(row.created_at) || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <template v-if="row.role !== 'owner'">
            <el-button type="danger" size="small" text @click="removeAdmin(row.user_id)">移除</el-button>
          </template>
          <template v-if="isOwner && row.role !== 'owner'">
            <el-button type="warning" size="small" text @click="transferOwnership(row.user_id)">转让</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="addDialogVisible" title="添加管理员" width="400px">
      <el-form label-width="80px">
        <el-form-item label="用户">
          <UserSearchSelect v-model="selectedUserId" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="selectedRole" style="width:100%">
            <el-option label="管理员" value="admin" />
            <el-option label="拥有者" value="owner" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!selectedUserId" @click="addAdmin">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { spaceApi } from '../../api'
import { fmtTime } from '../../utils/datetime'
import { confirmDelete } from '../../composables/useConfirmAction'
import UserSearchSelect from '../common/UserSearchSelect.vue'

const props = defineProps({
  spaceId: { type: String, required: true },
  isOwner: { type: Boolean, default: false },
})

const admins = ref([])
const addDialogVisible = ref(false)
const selectedUserId = ref('')
const selectedRole = ref('admin')

async function loadAdmins() {
  try {
    const res = await spaceApi.getAdmins(props.spaceId)
    admins.value = res.data.data || []
  } catch { admins.value = [] }
}

function openAddDialog() {
  selectedUserId.value = ''
  selectedRole.value = 'admin'
  addDialogVisible.value = true
}

async function addAdmin() {
  if (!selectedUserId.value) return
  try {
    await spaceApi.addAdmin(props.spaceId, selectedUserId.value, selectedRole.value)
    ElMessage.success('已添加管理员')
    addDialogVisible.value = false
    loadAdmins()
  } catch { /* handled by interceptor */ }
}

async function removeAdmin(userId) {
  if (!await confirmDelete('该管理员')) return
  try {
    await spaceApi.removeAdmin(props.spaceId, userId)
    ElMessage.success('已移除')
    loadAdmins()
  } catch { /* handled */ }
}

async function transferOwnership(userId) {
  try {
    await ElMessageBox.confirm('确认将 Space 所有权转让给该用户？你将降级为管理员。', '转让确认', { type: 'warning' })
    await spaceApi.transferOwnership(props.spaceId, userId)
    ElMessage.success('已转让所有权')
    loadAdmins()
  } catch { /* cancel or error */ }
}

onMounted(loadAdmins)
</script>

<style scoped>
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; }
</style>
