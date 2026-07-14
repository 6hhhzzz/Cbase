<template>
  <div class="chat-layout">
    <div class="sidebar">
      <div class="sidebar-header">
        <h3>对话</h3>
        <el-button type="primary" size="small" @click="newChat">新建对话</el-button>
      </div>

      <KbSelector
        :kbs="kbs"
        :kb-mode="kbMode"
        :expanded="expanded"
        :excluded-kb-ids="excludedKbIds"
        @update:expanded="expanded = $event"
        @toggle-kb="toggleKb"
        @reset-filter="resetKbFilter"
        @manage-kb="router.push(`/app/${spaceId}/settings`)"
      />

      <ConversationList
        :conversations="conversations"
        :current-conv-id="currentConvId"
        @select="selectConversation"
        @delete="deleteConversation"
      />

      <SidebarFooter
        :space-name="activeSpace?.space_name || ''"
        :role-label="roleLabel"
        :kb-count="kbs.length"
        @go-settings="router.push(`/app/${spaceId}/settings`)"
        @go-documents="router.push(`/app/${spaceId}/documents`)"
        @switch-space="router.push('/spaces')"
        @logout="handleLogout"
      />
    </div>

    <div class="chat-main">
      <div class="messages" ref="messagesContainer">
        <ChatMessage v-for="(msg, i) in messages" :key="i" :msg="msg" :streaming="streaming" />
      </div>

      <ChatInput v-model="input" :disabled="streaming" @send="onSend" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { conversationsApi } from '../api'
import { confirmDelete } from '../composables/useConfirmAction'
import { ROLE_LABEL_MAP } from '../utils/constants'
import { useKbFetcher } from '../composables/useKbFetcher'
import { useChatKbFilter } from '../composables/useChatKbFilter'
import { useChatMessages } from '../composables/useChatMessages'
import { useChatSSE } from '../composables/useChatSSE'
import KbSelector from '../components/chat/KbSelector.vue'
import ConversationList from '../components/chat/ConversationList.vue'
import ChatMessage from '../components/chat/ChatMessage.vue'
import ChatInput from '../components/chat/ChatInput.vue'
import SidebarFooter from '../components/chat/SidebarFooter.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const spaceId = computed(() => route.params.spaceId)
const currentConvId = computed(() => route.params.convId || '')

const activeSpace = computed(() => authStore.activeSpace)
const roleLabel = computed(() => ROLE_LABEL_MAP[authStore.currentRole] || authStore.currentRole)

// Composables
const { kbs, loadKBs } = useKbFetcher()
const { kbMode, excludedKbIds, expanded, toggleKb, resetKbFilter } = useChatKbFilter()
const { messages, input, loadMessages } = useChatMessages()
const conversations = ref([])

async function loadConversations() {
  try {
    const res = await conversationsApi.list({})
    const data = res.data.data
    conversations.value = (data && data.items) ? data.items : []
  } catch { /* 非致命 */ }
}

const { streaming, send, newChat, selectConversation, cancelStreaming } = useChatSSE({
  spaceId,
  currentConvId,
  messages,
  excludedKbIds,
  onConversationsChanged: loadConversations,
})

async function deleteConversation(conv) {
  const name = conv.title || '该对话'
  if (!await confirmDelete(name)) return
  try {
    await conversationsApi.delete(conv.id)
    ElMessage.success('对话已删除')
    if (conv.id === currentConvId.value) {
      router.push(`/app/${spaceId.value}/chat`)
    }
    await loadConversations()
  } catch { /* 响应拦截器已处理错误 */ }
}

function onSend(text) {
  send(text)
  input.value = ''
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

// 路由变更时加载对应消息（发送消息期间跳过，避免覆盖本地流式内容）
watch(() => route.params.convId, async (newId) => {
  if (streaming.value) return
  await loadMessages(newId || '')
  if (newId) await loadConversations()
}, { immediate: false })

onMounted(async () => {
  await loadKBs()
  await loadConversations()
  if (currentConvId.value) {
    await loadMessages(currentConvId.value)
  }
})

// 组件卸载时取消正在进行的 SSE 流，避免内存泄漏和状态污染
onUnmounted(() => {
  cancelStreaming()
})
</script>

<style scoped>
.chat-layout { display: flex; height: 100vh; }
.sidebar { width: 260px; border-right: 1px solid #eee; display: flex; flex-direction: column; }
.sidebar-header { padding: 16px; display: flex; justify-content: space-between; align-items: center; }
.chat-main { flex: 1; display: flex; flex-direction: column; }
.messages { flex: 1; overflow-y: auto; padding: 20px; }
</style>
