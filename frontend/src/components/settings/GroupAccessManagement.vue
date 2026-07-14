<template>
  <div>
    <div class="section-header">
      <h3>准入组管理</h3>
      <el-button type="primary" size="small" @click="openAddDialog">添加准入组</el-button>
    </div>
    <el-table :data="groups" stripe>
      <el-table-column label="组名称" min-width="200">
        <template #default="{ row }">{{ row.group_name || row.group_id }}</template>
      </el-table-column>
      <el-table-column label="加入时间" width="180">
        <template #default="{ row }">{{ fmtTime(row.joined_at) || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button type="danger" size="small" text @click="removeGroup(row.group_id)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="添加准入组" width="400px">
      <el-select v-model="selectedGroupId" placeholder="选择用户组" style="width:100%">
        <el-option v-for="g in allGroups" :key="g.group_id"
          :label="g.name" :value="g.group_id" />
      </el-select>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!selectedGroupId" @click="addGroup">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { spaceApi, groupsApi } from '../../api'
import { fmtTime } from '../../utils/datetime'
import { confirmDelete } from '../../composables/useConfirmAction'

const props = defineProps({ spaceId: { type: String, required: true } })

const groups = ref([])
const allGroups = ref([])
const dialogVisible = ref(false)
const selectedGroupId = ref('')

async function loadGroups() {
  try {
    const res = await spaceApi.getGroups(props.spaceId)
    groups.value = res.data.data || []
  } catch { groups.value = [] }
}

async function openAddDialog() {
  try {
    const res = await groupsApi.list()
    allGroups.value = res.data.data || []
    selectedGroupId.value = ''
    dialogVisible.value = true
  } catch { /* ignore */ }
}

async function addGroup() {
  if (!selectedGroupId.value) return
  try {
    await spaceApi.addGroup(props.spaceId, selectedGroupId.value)
    ElMessage.success('已添加准入组')
    dialogVisible.value = false
    loadGroups()
  } catch { /* handled */ }
}

async function removeGroup(groupId) {
  if (!await confirmDelete('该准入组')) return
  try {
    await spaceApi.removeGroup(props.spaceId, groupId)
    ElMessage.success('已移除')
    loadGroups()
  } catch { /* handled */ }
}

onMounted(loadGroups)
</script>

<style scoped>
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; }
</style>
