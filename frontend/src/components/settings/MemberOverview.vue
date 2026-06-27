<template>
  <div>
    <h4 style="margin-bottom:16px">管理员</h4>
    <el-table :data="admins" stripe v-loading="loading">
      <el-table-column label="用户" min-width="200">
        <template #default="{ row }">{{ row.display_name || row.username }}<br/><small style="color:#999">{{ row.username }}</small></template>
      </el-table-column>
      <el-table-column prop="role" label="角色" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="row.role === 'owner' ? 'danger' : 'warning'">{{ row.role === 'owner' ? '拥有者' : '管理员' }}</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <h4 style="margin: 24px 0 16px">准入用户组</h4>
    <el-table :data="groups" stripe v-loading="loading">
      <el-table-column prop="group_name" label="组名" min-width="160" />
      <el-table-column label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_system_admin ? 'danger' : ''">{{ row.is_system_admin ? '系统管理组' : '普通组' }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { spaceApi } from '../../api'

const props = defineProps({ spaceId: { type: String, required: true } })
const loading = ref(false)
const admins = ref([])
const groups = ref([])

async function load() {
  loading.value = true
  try {
    const [aRes, gRes] = await Promise.all([
      spaceApi.getAdmins(props.spaceId),
      spaceApi.getGroups(props.spaceId),
    ])
    admins.value = aRes.data.data || []
    groups.value = gRes.data.data || []
  } catch {
    admins.value = []
    groups.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.spaceId, load)
</script>
