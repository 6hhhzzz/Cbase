<template>
  <div class="space-switcher">
    <div class="header">
      <h1>选择空间</h1>
      <p class="subtitle">选择一个 Space 开始工作</p>
      <div class="header-links">
        <template v-if="authStore.isGlobalAdmin">
          <el-button text @click="router.push('/groups')">用户组管理</el-button>
          <el-button text @click="router.push('/roles')">角色管理</el-button>
          <el-button text @click="router.push('/admin')">全局管理</el-button>
        </template>
        <el-dropdown trigger="click" @command="handleUserCommand">
          <el-button text type="primary">
            👤 {{ authStore.user?.display_name || authStore.user?.username }} ▾
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 修改密码对话框 -->
    <el-dialog v-model="pwdVisible" title="修改密码" width="400px">
      <el-form label-width="80px">
        <el-form-item label="旧密码">
          <el-input v-model="pwdForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" @click="handleChangePassword">确认修改</el-button>
      </template>
    </el-dialog>

    <div class="space-list" v-if="spaces.length > 0">
      <el-card
        v-for="space in spaces"
        :key="space.space_id"
        class="space-card"
        shadow="hover"
        @click="enterSpace(space)"
      >
        <div class="space-info">
          <h3>{{ space.space_name }}</h3>
          <el-tag size="small" type="info">{{ roleLabel(space.role) }}</el-tag>
        </div>
      </el-card>
    </div>

    <el-empty v-else description="暂无可用空间">
      <el-button type="primary" @click="showCreate = true">创建我的第一个空间</el-button>
    </el-empty>

    <div style="text-align:center;margin-top:16px" v-if="spaces.length > 0">
      <el-button type="primary" @click="showCreate = true">创建新空间</el-button>
    </div>

    <!-- 创建 Space 对话框 -->
    <el-dialog v-model="showCreate" title="创建新空间" width="400px">
      <el-form :model="createForm">
        <el-form-item label="空间名称">
          <el-input v-model="createForm.name" placeholder="例如：我的项目、技术团队" />
        </el-form-item>
        <el-form-item label="类型标签">
          <el-input v-model="createForm.type_label" placeholder="例如：company, lab, project（可选）" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" placeholder="空间描述（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createSpace">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { spaceApi, authApi } from '../api'
import { ElMessage } from 'element-plus'
import { ROLE_LABEL_MAP } from '../utils/constants'

const router = useRouter()
const authStore = useAuthStore()

const spaces = authStore.spaces
const pwdVisible = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })

function handleUserCommand(cmd) {
  if (cmd === 'password') { pwdVisible.value = true }
  else if (cmd === 'logout') { handleLogout() }
}

async function handleChangePassword() {
  if (!pwdForm.old_password || !pwdForm.new_password) {
    ElMessage.warning('请填写旧密码和新密码')
    return
  }
  if (pwdForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  try {
    await authApi.changePassword({ old_password: pwdForm.old_password, new_password: pwdForm.new_password })
    ElMessage.success('密码已修改')
    pwdVisible.value = false
    pwdForm.old_password = ''; pwdForm.new_password = ''; pwdForm.confirm = ''
  } catch { /* handled by interceptor */ }
}
const showCreate = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', type_label: '', description: '' })

function roleLabel(role) {
  return ROLE_LABEL_MAP[role] || role
}

async function enterSpace(space) {
  try {
    await authStore.switchSpace(space.space_id)
    router.push(`/app/${space.space_id}/chat`)
  } catch {
    ElMessage.error('进入空间失败')
  }
}

async function createSpace() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请输入空间名称')
    return
  }
  creating.value = true
  try {
    const res = await spaceApi.create(createForm.name, createForm.type_label, createForm.description)
    const data = res.data.data
    showCreate.value = false
    createForm.name = ''
    createForm.type_label = ''
    createForm.description = ''
    // 刷新 spaces 列表
    const spacesRes = await authApi.getSpaces(authStore.refreshToken)
    authStore.spaces = spacesRes.data.data || []
    localStorage.setItem('spaces', JSON.stringify(authStore.spaces))
    ElMessage.success('空间创建成功')
    // 自动进入新空间
    await authStore.switchSpace(data.space_id)
    router.push(`/app/${data.space_id}/chat`)
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

onMounted(() => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
  }
})
</script>

<style scoped>
.space-switcher {
  max-width: 600px;
  margin: 80px auto;
  padding: 0 20px;
}

.header {
  text-align: center;
  margin-bottom: 32px;
}

.header h1 {
  font-size: 24px;
  margin-bottom: 8px;
}

.subtitle {
  color: #999;
}

.space-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.space-card {
  cursor: pointer;
  transition: border-color 0.2s;
}

.space-card:hover {
  border-color: #409eff;
}

.space-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.space-info h3 {
  margin: 0;
  font-size: 16px;
}
</style>
