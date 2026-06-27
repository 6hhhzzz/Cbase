<template>
  <div class="admin-layout">
    <div class="admin-header">
      <h2>全局管理面板</h2>
      <div>
        <el-button @click="router.push('/groups')">用户组管理</el-button>
        <el-button @click="router.push('/roles')">角色管理</el-button>
        <el-button text @click="router.push('/spaces')">← 返回空间列表</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- ========== Tab: 空间管理 ========== -->
      <el-tab-pane label="空间管理" name="spaces">
        <el-table :data="spaces" stripe v-loading="spaceLoading">
          <el-table-column prop="name" label="空间名称" />
          <el-table-column prop="type_label" label="类型" width="120" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'archived' ? 'warning' : 'success'" size="small">
                {{ row.status === 'archived' ? '已归档' : '活跃' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="180">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="最后活跃" width="180">
            <template #default="{ row }">{{ row.last_accessed_at ? fmtTime(row.last_accessed_at) : '从未' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button size="small" @click="archiveSpace(row)">归档</el-button>
              <el-button size="small" type="danger" @click="deleteSpace(row)">删除</el-button>
              <el-button v-if="row.status === 'archived' || row._deleted" size="small" type="success" @click="restoreSpace(row)">恢复</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ========== Tab: 用户管理 ========== -->
      <el-tab-pane label="用户管理" name="users">
        <div style="margin-bottom:12px;display:flex;gap:8px;">
          <el-button type="primary" size="small" @click="openCreateUser">创建用户</el-button>
          <el-button size="small" @click="openImportUsers">导入用户</el-button>
        </div>
        <el-table :data="users" stripe v-loading="userLoading">
          <el-table-column label="用户" min-width="180">
            <template #default="{ row }">
              {{ row.display_name }}<br/><small style="color:#999">{{ row.username }}</small>
            </template>
          </el-table-column>
          <el-table-column prop="email" label="邮箱" width="200">
            <template #default="{ row }">{{ row.email || '-' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'disabled' ? 'danger' : 'success'" size="small">
                {{ row.status === 'disabled' ? '已禁用' : '正常' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="全局管理员" width="120" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.is_global_admin"
                @change="(val) => toggleGlobalAdmin(row, val)"
                :disabled="row.username === authStore.user?.username"
                size="small"
              />
            </template>
          </el-table-column>
          <el-table-column label="注册时间" width="160">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEditUser(row)">编辑</el-button>
              <el-button
                size="small"
                :type="row.status === 'disabled' ? 'success' : 'danger'"
                :disabled="row.username === authStore.user?.username"
                @click="toggleUserStatus(row)"
              >
                {{ row.status === 'disabled' ? '启用' : '禁用' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ========== Tab: 模型管理 (v6) ========== -->
      <el-tab-pane label="模型管理" name="models">
        <ModelManagement />
      </el-tab-pane>
    </el-tabs>

    <!-- 创建/编辑用户对话框 -->
    <UserEditDialog
      v-model:visible="userEditVisible"
      :mode="userEditMode"
      :user="editingUser"
      @saved="onUserSaved"
    />

    <!-- 批量导入对话框 -->
    <UserImportDialog
      v-model:visible="importVisible"
      @done="onImportDone"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '../api'
import { useAuthStore } from '../stores/auth'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fmtTime } from '../utils/datetime'
import { confirmAction } from '../composables/useConfirmAction'
import { handleError } from '../utils/errorHandler'
import ModelManagement from './ModelManagement.vue'
import UserEditDialog from '../components/settings/UserEditDialog.vue'
import UserImportDialog from '../components/settings/UserImportDialog.vue'

const router = useRouter()
const authStore = useAuthStore()

const activeTab = ref('spaces')
const spaces = ref([])
const users = ref([])
const spaceLoading = ref(false)
const userLoading = ref(false)

// 对话框状态
const userEditVisible = ref(false)
const userEditMode = ref('create')  // 'create' | 'edit'
const editingUser = ref(null)
const importVisible = ref(false)

function onTabChange(tab) {
  if (tab === 'users' && users.value.length === 0) loadUsers()
}

async function loadSpaces() {
  spaceLoading.value = true
  try {
    const res = await adminApi.getAllSpaces()
    spaces.value = res.data.data || []
  } catch { ElMessage.error('加载失败') }
  finally { spaceLoading.value = false }
}

async function loadUsers() {
  userLoading.value = true
  try {
    const res = await adminApi.listUsers()
    users.value = res.data.data || []
  } catch { ElMessage.error('加载用户列表失败') }
  finally { userLoading.value = false }
}

async function toggleGlobalAdmin(user, val) {
  try {
    await adminApi.setGlobalAdmin(user.user_id, val)
    user.is_global_admin = val
    ElMessage.success(val ? `已设置 ${user.display_name} 为全局管理员` : `已取消 ${user.display_name} 的全局管理员`)
  } catch (e) { handleError(e) }
}

function openCreateUser() {
  userEditMode.value = 'create'
  editingUser.value = null
  userEditVisible.value = true
}

function openEditUser(user) {
  userEditMode.value = 'edit'
  editingUser.value = { ...user }
  userEditVisible.value = true
}

async function onUserSaved() {
  userEditVisible.value = false
  await loadUsers()
}

async function toggleUserStatus(user) {
  const newStatus = user.status === 'disabled' ? 'active' : 'disabled'
  const action = newStatus === 'disabled' ? '禁用' : '启用'
  if (!await confirmAction(`确定${action}用户 ${user.display_name} 吗？`, '确认')) return
  try {
    await adminApi.setUserStatus(user.user_id, newStatus)
    user.status = newStatus
    ElMessage.success(`已${action}`)
  } catch (e) { handleError(e) }
}

function openImportUsers() {
  importVisible.value = true
}

function onImportDone() {
  importVisible.value = false
  loadUsers()
}

// ---- Space 管理 ----

async function archiveSpace(row) {
  if (!await confirmAction('确定归档该空间吗？', '确认')) return
  try {
    await adminApi.archiveSpace(row.space_id)
    ElMessage.success('已归档')
    loadSpaces()
  } catch (e) { handleError(e) }
}

async function deleteSpace(row) {
  if (!await confirmAction('确定软删除该空间吗？', '确认')) return
  try {
    await adminApi.deleteSpace(row.space_id)
    ElMessage.success('已删除')
    loadSpaces()
  } catch (e) { handleError(e) }
}

async function restoreSpace(row) {
  try {
    await adminApi.restoreSpace(row.space_id)
    ElMessage.success('已恢复')
    loadSpaces()
  } catch { /* cancel */ }
}

onMounted(loadSpaces)
</script>

<style scoped>
.admin-layout { padding: 20px; max-width: 1200px; margin: 0 auto; }
.admin-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.admin-header h2 { margin: 0; }
</style>
