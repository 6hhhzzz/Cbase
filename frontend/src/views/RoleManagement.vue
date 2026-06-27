<template>
  <div class="role-management">
    <div class="page-header">
      <h2>角色管理</h2>
      <el-button type="primary" @click="showCreateDialog">创建自定义角色</el-button>
    </div>

    <el-table :data="roles" style="width: 100%">
      <el-table-column prop="name" label="名称" width="150" />
      <el-table-column prop="description" label="描述" min-width="200" />
      <el-table-column label="权限" min-width="300">
        <template #default="{ row }">
          <el-tag v-if="hasPerm(row, 'kb.read')" size="small" type="success">读取</el-tag>
          <el-tag v-if="hasPerm(row, 'kb.write')" size="small" type="warning">写入</el-tag>
          <el-tag v-if="hasPerm(row, 'kb.delete')" size="small" type="danger">删除</el-tag>
          <el-tag v-if="hasPerm(row, 'kb.manage')" size="small" type="primary">管理</el-tag>
          <el-tag v-if="hasPerm(row, 'ace.manage')" size="small" type="info">权限</el-tag>
          <span v-if="!hasAnyPerm(row)" style="color: #999">无权限（仅用于 Deny）</span>
        </template>
      </el-table-column>
      <el-table-column prop="is_system" label="系统角色" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_system ? 'info' : ''" size="small">{{ row.is_system ? '系统' : '自定义' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" @click="showEditDialog(row)">编辑</el-button>
          <el-button v-if="!row.is_system" size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑角色' : '创建角色'" width="500px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="角色名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" placeholder="可选" />
        </el-form-item>
        <el-form-item label="权限">
          <div v-if="editingSysRole" style="color: #999; margin-bottom: 8px">
            系统角色的权限不可修改
          </div>
          <el-checkbox-group v-model="form.permissions" :disabled="editingSysRole">
            <div v-for="p in permissionOptions" :key="p.key" style="margin-bottom: 4px">
              <el-checkbox :label="p.key" :value="p.key">{{ p.label }}</el-checkbox>
            </div>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { rolesApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const roles = ref([])
const dialogVisible = ref(false)
const editing = ref(null)
const form = ref({ name: '', description: '', permissions: [] })

const permissionOptions = [
  { key: 'kb.read', label: '读取知识库 — 搜索、问答、查看文档' },
  { key: 'kb.write', label: '写入知识库 — 上传、更新文档、编辑元数据' },
  { key: 'kb.delete', label: '删除文档 — 删除、永久删除文档' },
  { key: 'kb.manage', label: '管理知识库 — 改名、改可见性、软删、恢复' },
  { key: 'ace.manage', label: '管理权限 — 增删改 ACE 条目' },
]

const editingSysRole = ref(false)

// 旧格式 key → 新格式 key 映射
const OLD_KEY_MAP = {
  'doc:read': 'kb.read',
  'doc:write': 'kb.write',
  'doc:delete': 'kb.delete',
  'kb:admin': 'kb.manage',
}

function hasPerm(role, perm) {
  try {
    let raw = role.permissions
    // 防御: 如果已经是解析后的数组或对象，直接用
    if (Array.isArray(raw)) return raw.includes(perm)
    if (raw !== null && typeof raw === 'object' && !Array.isArray(raw)) {
      if (raw[perm] === true) return true
      for (const [oldKey, newKey] of Object.entries(OLD_KEY_MAP)) {
        if (newKey === perm && raw[oldKey] === true) return true
      }
      return false
    }
    // 字符串 → JSON 解析
    if (typeof raw !== 'string' || !raw) return false
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) {
      if (arr[perm] === true) return true
      for (const [oldKey, newKey] of Object.entries(OLD_KEY_MAP)) {
        if (newKey === perm && arr[oldKey] === true) return true
      }
      return false
    }
    return arr.includes(perm)
  } catch { return false }
}

function hasAnyPerm(role) {
  return permissionOptions.some(p => hasPerm(role, p.key))
}

async function loadRoles() {
  try {
    const res = await rolesApi.list()
    roles.value = res.data.data || []
  } catch { /* ignore */ }
}

function showCreateDialog() {
  editing.value = null
  editingSysRole.value = false
  form.value = { name: '', description: '', permissions: [] }
  dialogVisible.value = true
}

function showEditDialog(role) {
  editing.value = role
  editingSysRole.value = role.is_system
  form.value = {
    name: role.name,
    description: role.description || '',
    permissions: permissionOptions.filter(p => hasPerm(role, p.key)).map(p => p.key)
  }
  dialogVisible.value = true
}

async function saveRole() {
  if (!form.value.name) { ElMessage.warning('请输入角色名称'); return }
  const payload = {
    name: form.value.name,
    description: form.value.description,
    permissions: JSON.stringify(form.value.permissions)
  }
  try {
    if (editing.value) {
      await rolesApi.update(editing.value.id, payload)
    } else {
      await rolesApi.create(payload)
    }
    ElMessage.success(editing.value ? '已更新' : '已创建')
    dialogVisible.value = false
    loadRoles()
  } catch { /* error handled by interceptor */ }
}

async function handleDelete(role) {
  try {
    await ElMessageBox.confirm(`确认删除角色「${role.name}」？`, '警告', { type: 'warning' })
    await rolesApi.delete(role.id)
    ElMessage.success('已删除')
    loadRoles()
  } catch { /* cancel or error */ }
}

onMounted(loadRoles)
</script>

<style scoped>
.role-management { padding: 20px; max-width: 1000px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; }
</style>
