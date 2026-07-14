<template>
  <div class="group-management">
    <div class="page-header">
      <h2>全局用户组管理</h2>
      <el-button v-if="canManageGroups" type="primary" @click="showCreateDialog(null)">创建根组</el-button>
    </div>

    <div class="content-area">
      <!-- 左侧：树形列表 -->
      <div class="tree-panel">
        <el-tree
          :data="treeData"
          :props="{ label: 'name', children: 'children' }"
          node-key="id"
          default-expand-all
          highlight-current
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <span>{{ data.name }}</span>
              <el-tag v-if="data.is_system_admin" type="danger" size="small">超级管理员</el-tag>
              <el-tag size="small" class="member-count">{{ data.member_count }}人</el-tag>
            </span>
          </template>
        </el-tree>
      </div>

      <!-- 右侧：详情 -->
      <div class="detail-panel" v-if="selectedGroup">
        <h3>
          {{ selectedGroup.name }}
          <el-tag v-if="selectedGroup.is_system_admin" type="danger" size="small" style="margin-left:8px">超级管理员组</el-tag>
        </h3>
        <p class="desc">{{ selectedGroup.description || '暂无描述' }}</p>

        <div v-if="canManageGroups" class="sysadmin-toggle">
          <el-switch
            :model-value="selectedGroup.is_system_admin"
            @change="(val) => toggleSystemAdmin(selectedGroup, val)"
            active-text="超级管理员组"
            size="small"
          />
          <span style="color:#999;font-size:12px;margin-left:8px">组成员自动获得全局管理员权限</span>
        </div>

        <div class="actions" v-if="canManageGroups">
          <el-button @click="showCreateDialog(selectedGroup.id)">添加子组</el-button>
          <el-button @click="showEditDialog">编辑</el-button>
          <el-button type="danger" @click="handleDelete">删除</el-button>
        </div>

        <el-divider />

        <h4>组管理员</h4>
        <div style="margin-bottom:8px">
          <el-tag v-for="a in groupAdmins" :key="a.user_id" size="small" :type="a.role==='owner'?'danger':'warning'" style="margin-right:4px">
            {{ a.user_id?.substring(0,8) }} ({{ a.role === 'owner' ? '拥有者' : '管理员' }})
            <el-button v-if="canManageThisGroup" text size="small" @click="removeGroupAdmin(a.user_id)" style="margin-left:4px">✕</el-button>
          </el-tag>
        </div>
        <div v-if="canManageThisGroup" style="margin-bottom:12px">
          <el-select v-model="newAdminUserId" filterable remote :remote-method="searchUsers" placeholder="搜索用户设为管理员..." size="small" style="width:200px">
            <el-option v-for="u in userOptions" :key="u.user_id" :label="`${u.username} (${u.display_name})`" :value="u.user_id" />
          </el-select>
          <el-button size="small" @click="addGroupAdmin">添加</el-button>
        </div>

        <el-divider />

        <h4>组成员 ({{ selectedGroup.member_count }}人)</h4>
        <div v-if="canManageThisGroup" class="add-member">
          <el-select
            v-model="selectedUserId"
            filterable
            remote
            :remote-method="searchUsers"
            placeholder="搜索用户..."
            style="width: 250px"
          >
            <el-option v-for="u in userOptions" :key="u.user_id" :label="`${u.username} (${u.display_name})`" :value="u.user_id" />
          </el-select>
          <el-button type="primary" @click="addMember" :disabled="!selectedUserId">添加</el-button>
        </div>

        <el-table :data="members" style="margin-top: 12px">
          <el-table-column label="用户" width="200">
            <template #default="{ row }">{{ row.display_name || row.username }}<br/><small style="color:#999">{{ row.username }}</small></template>
          </el-table-column>
          <el-table-column label="操作" width="100" v-if="canManageThisGroup">
            <template #default="{ row }">
              <el-button type="danger" size="small" @click="removeMember(row.user_id)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="detail-panel empty" v-else>
        <p>选择一个用户组查看详情</p>
      </div>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="450px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="组名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" placeholder="可选" />
        </el-form-item>
        <el-form-item label="父组">
          <el-input :model-value="parentGroupName" disabled />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveGroup">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { groupsApi } from '../api'
import { useAuthStore } from '../stores/auth'
import { useUserSearch } from '../composables/useUserSearch'
import { ElMessage, ElMessageBox } from 'element-plus'

const authStore = useAuthStore()
// 权限：全局管理员 或 该组的 admin/owner
const canManageGroups = computed(() => authStore.isGlobalAdmin)
const canManageThisGroup = computed(() => {
  if (authStore.isGlobalAdmin) return true
  if (!selectedGroup.value) return false
  return selectedGroup.value._isAdmin === true
})

const { userOptions, searchUsers } = useUserSearch()

const treeData = ref([])
const selectedGroup = ref(null)
const members = ref([])
const selectedUserId = ref(null)

const dialogVisible = ref(false)
const editingGroup = ref(null)
const parentGroupId = ref(null)
// Group admins
const groupAdmins = ref([])
const newAdminUserId = ref('')
const form = ref({ name: '', description: '' })

const dialogTitle = computed(() => editingGroup.value ? '编辑用户组' : '创建用户组')
const parentGroupName = computed(() => {
  if (editingGroup.value) return '（不可修改）'
  if (parentGroupId.value) {
    const findName = (nodes, id) => {
      for (const n of nodes) {
        if (n.id === id) return n.name
        if (n.children) { const r = findName(n.children, id); if (r) return r }
      }
      return null
    }
    return findName(treeData.value, parentGroupId.value) || '根组'
  }
  return '根组'
})

const treeLoading = ref(false)

async function loadTree() {
  treeLoading.value = true
  try {
    const res = await groupsApi.list()
    const roots = (res.data.data || []).map(normalizeGroup)
    treeData.value = await Promise.all(roots.map(buildTreeNode))
  } catch (e) {
    ElMessage.error('加载用户组失败')
    console.error('loadTree:', e)
  } finally {
    treeLoading.value = false
  }
}

/** 将后端 snake_case 字段归一化为前端使用的 camelCase */
function normalizeGroup(g) {
  return {
    ...g,
    id: g.group_id || g.id,
    member_count: g.member_count ?? 0,
  }
}

async function buildTreeNode(g) {
  let children = []
  try {
    const res = await groupsApi.list({ parent_id: g.id })
    const subs = (res.data.data || []).map(normalizeGroup)
    children = await Promise.all(subs.map(buildTreeNode))
  } catch (e) {
    console.error('buildTreeNode:', g.id, e)
  }
  return { ...g, children }
}

async function onNodeClick(data) {
  selectedGroup.value = data
  try {
    const res = await groupsApi.getMembers(data.id)
    members.value = res.data.data || []
  } catch { members.value = []; ElMessage.warning('加载成员列表失败') }
  loadGroupAdmins()
}

async function loadGroupAdmins() {
  try {
    const res = await groupsApi.getAdmins(selectedGroup.value.id)
    groupAdmins.value = res.data.data || []
    // 标记当前用户是否是该组的 admin
    selectedGroup.value._isAdmin = groupAdmins.value.some(a => a.user_id === authStore.user?.id)
  } catch { groupAdmins.value = []; ElMessage.warning('加载管理员列表失败') }
}

async function addGroupAdmin() {
  if (!newAdminUserId.value) return
  try {
    await groupsApi.addAdmin(selectedGroup.value.id, newAdminUserId.value, 'admin')
    newAdminUserId.value = ''
    loadGroupAdmins()
  } catch { /* handled */ }
}

async function removeGroupAdmin(userId) {
  try {
    await groupsApi.removeAdmin(selectedGroup.value.id, userId)
    loadGroupAdmins()
  } catch { /* handled */ }
}

async function addMember() {
  try {
    await groupsApi.addMember(selectedGroup.value.id, selectedUserId.value)
    ElMessage.success('成员已添加')
    selectedUserId.value = null
    onNodeClick(selectedGroup.value)
    loadTree()
  } catch { /* error handled by interceptor */ }
}

async function removeMember(userId) {
  try {
    await ElMessageBox.confirm('确认移除该成员？', '提示', { type: 'warning' })
    await groupsApi.removeMember(selectedGroup.value.id, userId)
    ElMessage.success('已移除')
    onNodeClick(selectedGroup.value)
    loadTree()
  } catch { /* cancel or error */ }
}

function showCreateDialog(parentId) {
  editingGroup.value = null
  parentGroupId.value = parentId
  form.value = { name: '', description: '' }
  dialogVisible.value = true
}

function showEditDialog() {
  editingGroup.value = selectedGroup.value
  form.value = { name: selectedGroup.value.name, description: selectedGroup.value.description || '' }
  dialogVisible.value = true
}

async function saveGroup() {
  if (!form.value.name) { ElMessage.warning('请输入组名称'); return }
  try {
    if (editingGroup.value) {
      await groupsApi.update(editingGroup.value.id, {
        name: form.value.name,
        description: form.value.description
      })
    } else {
      await groupsApi.create({
        name: form.value.name,
        description: form.value.description,
        parent_group_id: parentGroupId.value || null
      })
    }
    ElMessage.success(editingGroup.value ? '已更新' : '已创建')
    dialogVisible.value = false
    loadTree()
  } catch { /* error handled by interceptor */ }
}

async function toggleSystemAdmin(group, val) {
  try {
    await groupsApi.update(group.id, { is_system_admin: val })
    group.is_system_admin = val
    ElMessage.success(val ? '已设为超级管理员组' : '已取消超级管理员组')
    loadTree()
  } catch { /* handled by interceptor */ }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(`确认删除用户组「${selectedGroup.value.name}」？`, '警告', { type: 'warning' })
    await groupsApi.delete(selectedGroup.value.id)
    ElMessage.success('已删除')
    selectedGroup.value = null
    loadTree()
  } catch { /* cancel or error */ }
}

onMounted(loadTree)
</script>

<style scoped>
.group-management { padding: 20px; max-width: 1200px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; }
.content-area { display: flex; gap: 20px; min-height: 400px; }
.tree-panel { width: 320px; border: 1px solid #e4e7ed; border-radius: 4px; padding: 12px; overflow-y: auto; }
.detail-panel { flex: 1; border: 1px solid #e4e7ed; border-radius: 4px; padding: 20px; }
.detail-panel.empty { display: flex; align-items: center; justify-content: center; color: #999; }
.detail-panel h3 { margin-top: 0; }
.detail-panel .desc { color: #666; }
.actions { margin: 12px 0; }
.tree-node { display: flex; align-items: center; gap: 8px; }
.member-count { margin-left: auto; }
.add-member { display: flex; gap: 8px; }
</style>
