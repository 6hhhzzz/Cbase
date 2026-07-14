<template>
  <div class="space-switcher">
    <!-- ========== 顶部导航栏 ========== -->
    <header class="top-bar">
      <div class="brand">
        <span class="brand-dot"></span>
        <span class="brand-text">CBase</span>
      </div>
      <div class="top-actions">
        <template v-if="authStore.isGlobalAdmin">
          <el-button text size="small" class="top-link" @click="router.push('/groups')">用户组管理</el-button>
          <el-button text size="small" class="top-link" @click="router.push('/roles')">角色管理</el-button>
          <el-button text size="small" class="top-link" @click="router.push('/admin')">全局管理</el-button>
        </template>
        <el-dropdown trigger="click" @command="handleUserCommand">
          <span class="user-trigger">
            <span class="user-avatar">{{ (authStore.user?.display_name || authStore.user?.username || '?')[0] }}</span>
            <span class="user-name">{{ authStore.user?.display_name || authStore.user?.username }}</span>
            <span class="user-arrow">▾</span>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- ========== 主体内容 ========== -->
    <main class="main-content">
      <div class="page-header">
        <h1>选择空间</h1>
        <p class="page-desc">选择一个 Space 开始工作</p>
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

      <!-- ===== 空间网格 ===== -->
      <div class="space-grid" v-if="spaces.length > 0">
        <div
          v-for="space in spaces"
          :key="space.space_id"
          class="space-cell"
          @click="enterSpace(space)"
        >
          <div class="cell-icon">
            {{ (space.space_name || 'S')[0] }}
          </div>
          <div class="cell-body">
            <h3 class="cell-name">{{ space.space_name }}</h3>
            <p class="cell-desc" v-if="space.description">{{ space.description }}</p>
            <p class="cell-desc" v-else-if="space.type_label">{{ space.type_label }}</p>
          </div>
          <span class="cell-role" :class="'role-' + space.role">{{ roleLabel(space.role) }}</span>
        </div>

        <!-- 创建入口：虚线占位卡片 -->
        <div class="space-cell space-cell--create" @click="showCreate = true">
          <div class="cell-icon cell-icon--create">
            <span class="plus-sign">+</span>
          </div>
          <div class="cell-body">
            <h3 class="cell-name">创建新空间</h3>
            <p class="cell-desc">创建新的 Space 来组织和管理知识</p>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div class="empty-state" v-else>
        <div class="empty-icon">🏢</div>
        <h2>欢迎使用 CBase</h2>
        <p>你还未加入任何空间，创建第一个空间开始吧</p>
        <el-button type="primary" size="large" @click="showCreate = true">
          创建我的第一个空间
        </el-button>
      </div>

      <!-- 创建 Space 对话框 -->
      <el-dialog v-model="showCreate" title="创建新空间" width="440px">
        <el-form :model="createForm" label-position="top">
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
    </main>
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

onMounted(async () => {
  if (!authStore.isLoggedIn) {
    router.push('/login')
    return
  }
  // ★ 每次进入空间选择页都从服务端拉取最新空间列表，避免缓存过期
  try {
    const res = await authApi.getSpaces(authStore.refreshToken)
    authStore.spaces = res.data.data || []
    localStorage.setItem('spaces', JSON.stringify(authStore.spaces))
  } catch { /* 非致命，使用缓存数据 */ }
})
</script>

<style scoped>
/* ============================================================
   空间选择页 — 企业级网格布局
   设计基调：可靠 / 克制 / 高密度
   ============================================================ */

/* ---- 全局底色 ---- */
.space-switcher {
  min-height: 100vh;
  background: #f5f7fa;
}

/* ---- 顶部导航 ---- */
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 32px;
  background: #fff;
  border-bottom: 1px solid #f3f4f6;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #1677ff;
  box-shadow: 0 0 0 4px rgba(22, 119, 255, 0.12);
}

.brand-text {
  font-size: 17px;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: -0.3px;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.top-link {
  color: #6b7280 !important;
  font-size: 13px;
}

.top-link:hover {
  color: #1f2937 !important;
  background: #f3f4f6 !important;
}

.user-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  margin-left: 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #4b5563;
  transition: background 0.15s;
}

.user-trigger:hover {
  background: #f5f7fa;
}

.user-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #e6f4ff;
  color: #1677ff;
  font-size: 14px;
  font-weight: 600;
}

.user-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-arrow {
  font-size: 10px;
  color: #9ca3af;
}

/* ---- 主体内容 ---- */
.main-content {
  max-width: 1060px;
  margin: 0 auto;
  padding: 40px 32px 60px;
}

/* ---- 页面标题 ---- */
.page-header {
  margin-bottom: 32px;
}

.page-header h1 {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  color: #1f2937;
  letter-spacing: -0.5px;
}

.page-desc {
  margin: 8px 0 0;
  font-size: 14px;
  color: #9ca3af;
}

/* ---- 空间网格 ---- */
.space-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

/* ---- 单个空间卡片 ---- */
.space-cell {
  display: flex;
  flex-direction: column;
  padding: 24px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
  position: relative;
}

.space-cell:hover {
  border-color: #93c5fd;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  transform: translateY(-2px);
}

/* ---- 卡片图标 ---- */
.cell-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  font-size: 18px;
  font-weight: 700;
  background: #e6f4ff;
  color: #1677ff;
  flex-shrink: 0;
  margin-bottom: 14px;
}

/* ---- 卡片正文 ---- */
.cell-body {
  flex: 1;
  min-width: 0;
}

.cell-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: #9ca3af;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ---- 角色标签 ---- */
.cell-role {
  display: inline-block;
  align-self: flex-start;
  margin-top: 10px;
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.6;
}

.role-owner {
  background: #fff7ed;
  color: #c2410c;
}

.role-admin {
  background: #eff6ff;
  color: #1d4ed8;
}

.role-member {
  background: #f3f4f6;
  color: #6b7280;
}

/* ---- 创建入口卡片（虚线占位） ---- */
.space-cell--create {
  border-style: dashed;
  border-color: #d1d5db;
  background: #fafbfc;
  align-items: center;
  text-align: center;
  justify-content: center;
  min-height: 168px;
}

.space-cell--create:hover {
  border-color: #1677ff;
  background: #f3f4f6;
}

.cell-icon--create {
  background: #f0f5ff !important;
}

.plus-sign {
  font-size: 24px;
  font-weight: 300;
  color: #1677ff;
  line-height: 1;
}

.space-cell--create .cell-name {
  color: #1677ff;
}

/* ---- 空状态 ---- */
.empty-state {
  text-align: center;
  padding: 80px 0;
}

.empty-icon {
  font-size: 56px;
  margin-bottom: 16px;
}

.empty-state h2 {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
}

.empty-state p {
  margin: 0 0 24px;
  font-size: 14px;
  color: #9ca3af;
}

/* ---- 响应式 ---- */
@media (max-width: 900px) {
  .space-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .top-bar {
    padding: 0 20px;
  }

  .main-content {
    padding: 28px 20px 40px;
  }
}

@media (max-width: 560px) {
  .space-grid {
    grid-template-columns: 1fr;
  }

  .top-actions {
    gap: 0;
  }

  .top-link {
    padding: 4px 6px;
    font-size: 12px;
  }

  .user-name {
    display: none;
  }
}
</style>
