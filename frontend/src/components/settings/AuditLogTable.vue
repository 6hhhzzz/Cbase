<template>
  <div>
    <h3 style="margin-top:0">操作日志</h3>
    <el-table :data="logs" stripe v-loading="loading">
      <el-table-column label="操作人" width="120">
        <template #default="{ row }">{{ row.operator_name || row.operator_id }}</template>
      </el-table-column>
      <el-table-column prop="action" label="操作" width="180" />
      <el-table-column label="目标类型" width="80">
        <template #default="{ row }">{{ row.target_type || '-' }}</template>
      </el-table-column>
      <el-table-column prop="target_name" label="目标名称" min-width="150" />
      <el-table-column label="时间" width="180">
        <template #default="{ row }">{{ fmtTime(row.created_at) || '-' }}</template>
      </el-table-column>
    </el-table>
    <div class="pagination" style="margin-top:12px;display:flex;justify-content:flex-end">
      <el-pagination v-model:current-page="page" :total="total" :page-size="pageSize"
        layout="total, prev, pager, next" @current-change="loadLogs" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { spaceApi } from '../../api'
import { fmtTime } from '../../utils/datetime'

const props = defineProps({ spaceId: { type: String, required: true } })

const logs = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

async function loadLogs() {
  loading.value = true
  try {
    const res = await spaceApi.getAuditLogs(props.spaceId, page.value - 1, pageSize.value)
    const data = res.data.data || {}
    logs.value = data.items || []
    total.value = data.total_elements || 0
  } catch { logs.value = [] }
  finally { loading.value = false }
}

onMounted(loadLogs)
</script>
