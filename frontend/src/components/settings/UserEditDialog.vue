<template>
  <el-dialog
    :model-value="visible"
    :title="mode === 'create' ? '创建用户' : '编辑用户'"
    width="480px"
    @update:model-value="$emit('update:visible', $event)"
    @close="resetForm"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="100px"
      @submit.prevent="submit"
    >
      <el-form-item label="用户名" prop="username">
        <el-input v-model="form.username" :disabled="mode === 'edit'" maxlength="32" />
      </el-form-item>
      <el-form-item label="显示名称" prop="display_name">
        <el-input v-model="form.display_name" maxlength="64" />
      </el-form-item>
      <el-form-item label="邮箱" prop="email">
        <el-input v-model="form.email" maxlength="255" />
      </el-form-item>
      <el-form-item v-if="mode === 'create'" label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          show-password
          maxlength="128"
          placeholder="留空则自动生成随机密码"
        />
      </el-form-item>
      <el-form-item v-if="mode === 'edit'" label="状态" prop="status">
        <el-radio-group v-model="form.status">
          <el-radio value="active">正常</el-radio>
          <el-radio value="disabled">已禁用</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">
        {{ mode === 'create' ? '创建' : '保存' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { adminApi } from '../../api'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: Boolean,
  mode: { type: String, default: 'create' },
  user: { type: Object, default: null },
})

const emit = defineEmits(['update:visible', 'saved'])

const formRef = ref(null)
const submitting = ref(false)

const form = reactive({
  username: '',
  display_name: '',
  email: '',
  password: '',
  status: 'active',
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 32, message: '用户名长度 3-32 字符', trigger: 'blur' },
  ],
  display_name: [
    { required: true, message: '请输入显示名称', trigger: 'blur' },
  ],
  email: [
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

watch(() => props.visible, (val) => {
  if (val) {
    if (props.mode === 'edit' && props.user) {
      form.username = props.user.username || ''
      form.display_name = props.user.display_name || ''
      form.email = props.user.email || ''
      form.status = props.user.status || 'active'
      form.password = ''
    } else {
      resetForm()
    }
  }
})

function resetForm() {
  form.username = ''
  form.display_name = ''
  form.email = ''
  form.password = ''
  form.status = 'active'
  formRef.value?.resetFields()
}

async function submit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    if (props.mode === 'create') {
      const body = {
        username: form.username,
        display_name: form.display_name,
        email: form.email || null,
        password: form.password || null,
      }
      await adminApi.createUser(body)
      ElMessage.success('用户已创建')
    } else {
      const body = {
        display_name: form.display_name,
        email: form.email || null,
        status: form.status,
      }
      await adminApi.updateUser(props.user.user_id, body)
      ElMessage.success('用户信息已更新')
    }
    emit('saved')
  } catch (e) {
    const msg = e?.response?.data?.message || '操作失败'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}
</script>
