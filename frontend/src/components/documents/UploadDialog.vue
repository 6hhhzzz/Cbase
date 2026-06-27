<template>
  <el-dialog v-model="visible" title="上传文档" width="520px" @close="resetForm">
    <el-form :model="form" label-width="80px">
      <el-form-item label="选择文件">
        <el-upload :auto-upload="false" :limit="1" :on-change="onFileChange"
          :on-remove="() => form.file = null">
          <el-button type="primary">选择文件</el-button>
          <template #tip>
            <div style="margin-top:4px;color:#909399">
              支持 PDF / DOCX / XLSX / Markdown / HTML / TXT，最大 50MB
            </div>
          </template>
        </el-upload>
      </el-form-item>
      <el-form-item label="目标知识库">
        <el-select v-model="form.kb_id" placeholder="选择知识库" style="width:100%">
          <el-option v-for="kb in kbs" :key="kb.kb_id" :label="kb.name" :value="kb.kb_id" />
        </el-select>
      </el-form-item>
      <el-form-item label="生效日期">
        <el-date-picker v-model="form.effective_date" type="date"
          placeholder="选择生效日期，默认今天" style="width:100%" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item label="失效日期">
        <el-date-picker v-model="form.expiry_date" type="date"
          placeholder="留空表示长期有效" style="width:100%" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item label="版本号">
        <el-input v-model="form.version" placeholder="如 v2.0 / 2026年修订版" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="uploading" @click="handleUpload">上传</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  kbs: { type: Array, default: () => [] },
  uploading: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'upload'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const form = reactive({
  file: null,
  kb_id: '',
  effective_date: '',
  expiry_date: '',
  version: '',
})

function onFileChange(file) {
  form.file = file.raw
}

function handleUpload() {
  if (!form.file) {
    ElMessage.warning('请选择文件')
    return
  }
  emit('upload', { ...form })
}

function resetForm() {
  form.file = null
  form.effective_date = ''
  form.expiry_date = ''
  form.version = ''
}
</script>
