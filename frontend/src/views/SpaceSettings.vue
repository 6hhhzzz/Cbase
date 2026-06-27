<template>
  <div class="settings-layout">
    <div class="settings-sidebar">
      <h3>空间设置</h3>
      <el-menu :default-active="activeTab" @select="activeTab = $event">
        <el-menu-item index="members">成员总览</el-menu-item>
        <el-menu-item index="admins">管理员</el-menu-item>
        <el-menu-item index="groups">准入组</el-menu-item>
        <el-menu-item index="kbs">KB 管理</el-menu-item>
        <el-menu-item index="api-keys">API 密钥</el-menu-item>
        <el-menu-item index="trash">回收站</el-menu-item>
        <el-menu-item index="logs">操作日志</el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <el-button style="width:100%;margin-bottom:4px" @click="router.push(`/app/${spaceId}/aces`)">ACE 矩阵配置</el-button>
        <el-button style="width:100%" @click="router.push(`/app/${spaceId}/chat`)">返回聊天</el-button>
      </div>
    </div>
    <div class="settings-main">
      <MemberOverview v-if="activeTab === 'members'" :space-id="spaceId" />
      <AdminManagement v-if="activeTab === 'admins'" :space-id="spaceId"
        :is-owner="authStore.isOwner" />
      <GroupAccessManagement v-if="activeTab === 'groups'" :space-id="spaceId" />
      <KbSettings v-if="activeTab === 'kbs'" :space-id="spaceId" />
      <TrashPanel v-if="activeTab === 'trash'" :space-id="spaceId"
        @restore="restoreItem" @permanent-delete="permanentDeleteItem" />
      <ApiKeyManager v-if="activeTab === 'api-keys'" :space-id="spaceId" />
      <AuditLogTable v-if="activeTab === 'logs'" :space-id="spaceId" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { spaceApi, documentsApi } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import AdminManagement from '../components/settings/AdminManagement.vue'
import GroupAccessManagement from '../components/settings/GroupAccessManagement.vue'
import KbSettings from '../components/settings/KbSettings.vue'
import TrashPanel from '../components/settings/TrashPanel.vue'
import AuditLogTable from '../components/settings/AuditLogTable.vue'
import MemberOverview from '../components/settings/MemberOverview.vue'
import ApiKeyManager from '../components/settings/ApiKeyManager.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const spaceId = computed(() => route.params.spaceId)
const activeTab = ref('members')

async function restoreItem(item) {
  const label = item.type === 'kb' ? 'KB' : '文档'
  try {
    await ElMessageBox.confirm(`确认恢复该${label}？`, '提示', { type: 'info' })
    if (item.type === 'kb') {
      await spaceApi.restoreKb(spaceId.value, item.id)
    } else {
      await documentsApi.restore(item.id)
    }
    ElMessage.success(`已恢复${label}`)
    activeTab.value = 'trash'
    // force re-render by toggling tab
    setTimeout(() => activeTab.value = 'trash', 50)
  } catch { /* cancel or error */ }
}

async function permanentDeleteItem(item) {
  const label = item.type === 'kb' ? 'KB' : '文档'
  try {
    await ElMessageBox.confirm(`确认永久删除该${label}？此操作不可撤销！`, '警告', { type: 'error' })
    if (item.type === 'kb') {
      await spaceApi.deleteKb(spaceId.value, item.id, true)
    } else {
      await documentsApi.permanentDelete(item.id)
    }
    ElMessage.success(`已永久删除${label}`)
    setTimeout(() => activeTab.value = 'trash', 50)
  } catch { /* cancel or error */ }
}
</script>

<style scoped>
.settings-layout { display: flex; height: 100vh; }
.settings-sidebar { width: 200px; border-right: 1px solid #eee; padding: 16px 0; display: flex; flex-direction: column; }
.settings-sidebar h3 { padding: 0 16px; margin: 0 0 12px; }
.sidebar-footer { padding: 16px; border-top: 1px solid #eee; margin-top: auto; }
.settings-main { flex: 1; padding: 24px; overflow-y: auto; }
</style>
