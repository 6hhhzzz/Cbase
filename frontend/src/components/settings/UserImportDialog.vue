<template>
  <el-dialog
    :model-value="visible"
    title="批量导入用户"
    width="600px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div style="margin-bottom:16px;">
      <p style="color:#666;margin-bottom:8px;">上传 CSV 文件，表头需包含 <code>username</code> 和 <code>display_name</code> 列，可选 <code>email</code> 列。</p>
      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :limit="1"
        accept=".csv"
        :on-change="onFileChange"
        :on-remove="onFileRemove"
        :file-list="fileList"
      >
        <el-button size="small" type="primary">选择 CSV 文件</el-button>
      </el-upload>
    </div>

    <!-- 预览 -->
    <div v-if="preview.length > 0" style="margin-bottom:16px;">
      <h4>预览（前 5 行）</h4>
      <el-table :data="preview" size="small" max-height="200" stripe>
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="display_name" label="显示名称" width="140" />
        <el-table-column prop="email" label="邮箱" />
      </el-table>
    </div>

    <!-- 结果 -->
    <div v-if="result">
      <el-alert
        :type="result.failed > 0 ? 'warning' : 'success'"
        :title="`导入完成：共 ${result.total} 条，成功 ${result.success} 条` + (result.failed > 0 ? `，失败 ${result.failed} 条` : '')"
        :closable="false"
      />
      <div v-if="result.errors && result.errors.length" style="margin-top:12px;">
        <h4>失败明细</h4>
        <el-table :data="result.errors" size="small" max-height="200">
          <el-table-column prop="row" label="行号" width="80" />
          <el-table-column prop="username" label="用户名" width="140" />
          <el-table-column prop="reason" label="原因" />
        </el-table>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
      <el-button
        v-if="!result"
        type="primary"
        :loading="importing"
        :disabled="!selectedFile"
        @click="doImport"
      >
        开始导入
      </el-button>
      <el-button v-else type="primary" @click="$emit('done')">完成</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { adminApi } from '../../api'
import { ElMessage } from 'element-plus'

const props = defineProps({ visible: Boolean })
const emit = defineEmits(['update:visible', 'done'])

const uploadRef = ref(null)
const selectedFile = ref(null)
const fileList = ref([])
const preview = ref([])
const result = ref(null)
const importing = ref(false)

watch(() => props.visible, (val) => {
  if (!val) {
    selectedFile.value = null
    fileList.value = []
    preview.value = []
    result.value = null
  }
})

function onFileChange(file) {
  selectedFile.value = file.raw
  fileList.value = [file]
  parsePreview(file.raw)
}

function onFileRemove() {
  selectedFile.value = null
  preview.value = []
  result.value = null
}

function parsePreview(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    const text = e.target.result
    const lines = text.split('\n').filter(l => l.trim())
    if (lines.length < 2) {
      preview.value = []
      return
    }
    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''))
    preview.value = lines.slice(1, 6).map(line => {
      const cols = parseLine(line)
      const row = {}
      headers.forEach((h, i) => { row[h] = cols[i] || '' })
      return row
    })
  }
  reader.readAsText(file, 'UTF-8')
}

function parseLine(line) {
  const result = []
  let inQuotes = false, current = ''
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (inQuotes) {
      if (c === '"' && i + 1 < line.length && line[i + 1] === '"') {
        current += '"'; i++
      } else if (c === '"') {
        inQuotes = false
      } else {
        current += c
      }
    } else {
      if (c === '"') { inQuotes = true }
      else if (c === ',') { result.push(current.trim()); current = '' }
      else { current += c }
    }
  }
  result.push(current.trim())
  return result
}

async function doImport() {
  if (!selectedFile.value) return
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const res = await adminApi.batchImportUsers(formData)
    result.value = res.data.data
    if (result.value.failed === 0) {
      ElMessage.success(`全部 ${result.value.success} 个用户导入成功`)
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '导入失败')
  } finally {
    importing.value = false
  }
}
</script>
