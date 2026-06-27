<template>
  <div>
    <div class="section-header">
      <h3>KB 管理</h3>
      <el-button type="primary" size="small" @click="openNewDialog">创建 KB</el-button>
    </div>
    <el-table :data="kbs" stripe>
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column label="可见性" width="100">
        <template #default="{ row }">
          <el-tag :type="row.visibility === 'restricted' ? 'warning' : 'success'" size="small">
            {{ row.visibility === 'restricted' ? '受限' : '空间内' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="150" />
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">{{ fmtTime(row.created_at) || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{ row }">
          <el-button type="warning" size="small" text @click="openEditDialog(row)">编辑</el-button>
          <el-button type="danger" size="small" text @click="deleteKb(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingKb ? '编辑 KB' : '创建 KB'" width="500px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="可见性">
          <el-radio-group v-model="form.visibility">
            <el-radio value="space_wide">空间内可见</el-radio>
            <el-radio value="restricted">受限（通过 ACE 配置）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveKb">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { spaceApi } from '../../api'
import { fmtTime } from '../../utils/datetime'
import { confirmDelete } from '../../composables/useConfirmAction'

const props = defineProps({ spaceId: { type: String, required: true } })

const kbs = ref([])
const dialogVisible = ref(false)
const editingKb = ref(null)
const form = reactive({ name: '', description: '', visibility: 'space_wide' })

async function loadKbs() {
  try { const res = await spaceApi.listKbs(props.spaceId); kbs.value = res.data.data || [] } catch { kbs.value = [] }
}

function openNewDialog() {
  editingKb.value = null
  form.name = ''; form.description = ''; form.visibility = 'space_wide'
  dialogVisible.value = true
}

function openEditDialog(kb) {
  editingKb.value = kb
  form.name = kb.name; form.description = kb.description || ''; form.visibility = kb.visibility
  dialogVisible.value = true
}

async function saveKb() {
  try {
    if (editingKb.value) {
      await spaceApi.updateKb(props.spaceId, editingKb.value.kb_id, form.name, form.visibility)
      ElMessage.success('KB 已更新')
    } else {
      await spaceApi.createKb(props.spaceId, form.name, form.description, form.visibility)
      ElMessage.success('KB 已创建')
    }
    dialogVisible.value = false
    loadKbs()
  } catch { /* handled */ }
}

async function deleteKb(kb) {
  if (!await confirmDelete(`KB「${kb.name}」`)) return
  try {
    await spaceApi.deleteKb(props.spaceId, kb.kb_id)
    ElMessage.success('KB 已删除')
    loadKbs()
  } catch { /* handled */ }
}

onMounted(loadKbs)
</script>

<style scoped>
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; }
</style>
