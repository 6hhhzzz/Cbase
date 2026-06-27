<template>
  <el-dialog v-model="visible" title="更新文档" width="520px">
    <p style="margin-bottom:12px;color:#606266">更新「{{ target.filename }}」</p>
    <el-upload :auto-upload="false" :limit="1" :on-change="onFileChange"
      :on-remove="() => file = null">
      <el-button type="primary">选择新文件</el-button>
      <template #tip>
        <div style="margin-top:4px;color:#909399">
          支持 PDF / DOCX / XLSX / Markdown / HTML / TXT，最大 50MB
          <template v-if="!isAdmin">
            <br/>⚠ 非管理员更新需审批
          </template>
        </div>
      </template>
    </el-upload>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="updating" @click="handleUpdate">提交更新</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { documentsApi } from '../../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  target: { type: Object, default: () => ({ id: '', filename: '' }) },
  updating: { type: Boolean, default: false },
  isAdmin: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'update'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const file = ref(null)

function onFileChange(f) {
  file.value = f.raw
}

async function handleUpdate() {
  if (!file.value) {
    ElMessage.warning('请选择文件')
    return
  }
  const formData = new FormData()
  formData.append('file', file.value)
  try {
    const res = await documentsApi.update(props.target.id, formData)
    const result = res.data.data
    if (result && result.action === 'pending_approval') {
      ElMessage.info(result.message || '更新请求已提交，待管理员审批')
    } else {
      ElMessage.success('文档已更新，正在重新入库')
    }
    emit('update:modelValue', false)
    emit('update')
  } catch {
    ElMessage.error('更新请求失败')
  }
}
</script>
