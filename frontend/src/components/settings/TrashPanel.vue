<template>
  <div>
    <h3 style="margin-top:0">回收站</h3>
    <el-table :data="items" stripe v-loading="loading">
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-tag :type="row.type === 'kb' ? 'warning' : 'info'" size="small">
            {{ row.type === 'kb' ? 'KB' : '文档' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="200" />
      <el-table-column label="删除时间" width="180">
        <template #default="{ row }">{{ row.deleted_at ? fmtTime(row.deleted_at) : '-' }}</template>
      </el-table-column>
      <el-table-column label="剩余天数" width="100">
        <template #default="{ row }">{{ row.days_remaining }} 天</template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button type="success" size="small" @click="$emit('restore', row)">恢复</el-button>
          <el-button type="danger" size="small" @click="$emit('permanentDelete', row)">永久删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!loading && items.length === 0" style="text-align:center;color:#909399;padding:20px">
      回收站为空
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { spaceApi } from '../../api'
import { fmtTime } from '../../utils/datetime'

const props = defineProps({ spaceId: { type: String, required: true } })
defineEmits(['restore', 'permanentDelete'])

const items = ref([])
const loading = ref(false)

async function loadTrash() {
  loading.value = true
  try {
    const res = await spaceApi.getTrash(props.spaceId)
    const data = res.data.data || {}
    const kbItems = (data.kb_items || []).map(it => ({ ...it, type: 'kb' }))
    const docItems = (data.doc_items || []).map(it => ({ ...it, type: 'document' }))
    const all = [...kbItems, ...docItems]
    all.forEach(it => {
      if (it.deleted_at) {
        const del = new Date(it.deleted_at).getTime()
        it.days_remaining = Math.max(0, Math.ceil((del + 30 * 86400000 - Date.now()) / 86400000))
      } else { it.days_remaining = '-' }
    })
    items.value = all
  } catch { items.value = [] }
  finally { loading.value = false }
}

onMounted(loadTrash)
</script>
