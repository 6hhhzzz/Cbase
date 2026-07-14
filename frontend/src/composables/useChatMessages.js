import { ref } from 'vue'
import { conversationsApi } from '../api'

/**
 * 聊天消息加载 Composable。
 * 管理消息列表加载和历史消息格式化。
 */
export function useChatMessages() {
  const messages = ref([])
  const input = ref('')

  async function loadMessages(convId) {
    if (!convId) {
      messages.value = []
      return
    }
    try {
      const res = await conversationsApi.messages(convId)
      const data = res.data.data
      messages.value = (data && data.items)
        ? data.items.map(m => ({
            role: m.role,
            content: m.content,
            sources: m.sources || [],
          }))
        : []
    } catch {
      messages.value = []
    }
  }

  return { messages, input, loadMessages }
}
