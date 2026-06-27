import { ref, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { chatSSE, conversationsApi } from '../api'
import { generateUUID } from '../utils/idgen'

/**
 * Chat SSE 流式对话 Composable。
 * 封装 SSE 发送/流式状态管理/会话路由同步。
 *
 * @param {object} options
 * @param {import('vue').Ref<string>} options.spaceId  - 当前 Space ID
 * @param {import('vue').Ref<string>} options.currentConvId - 当前会话 ID
 * @param {import('vue').Ref<Array>} options.messages  - 消息列表
 * @param {import('vue').Ref<Array>} options.excludedKbIds - 排除的 KB ID
 * @param {() => Promise<void>} options.onConversationsChanged - 会话列表更新回调
 */
export function useChatSSE({ spaceId, currentConvId, messages, excludedKbIds, onConversationsChanged }) {
  const route = useRoute()
  const router = useRouter()
  const streaming = ref(false)
  let cancelFn = null

  async function send(inputText) {
    if (!inputText.trim() || streaming.value) return
    const query = inputText.trim()
    streaming.value = true

    // 新会话 → 首条消息发送时分配 UUID
    let convId = currentConvId.value
    if (!convId) {
      convId = generateUUID()
      router.replace(`/app/${spaceId.value}/chat/${convId}`)
    }

    messages.value.push({ role: 'user', content: query })

    // 推入助手消息占位，通过 messages.value[idx] 访问响应式代理
    messages.value.push({ role: 'assistant', content: '', sources: [] })
    const assistantIdx = messages.value.length - 1

    try {
      cancelFn = await chatSSE(
        query, convId, excludedKbIds.value,
        // onToken — 必须通过 messages.value[assistantIdx] 修改内容，
        // 否则直接修改原始对象会绕过 Vue 响应式系统导致 DOM 不更新
        (chunk) => {
          messages.value[assistantIdx].content += chunk.token || ''
          if (chunk.done && chunk.sources) {
            messages.value[assistantIdx].sources = chunk.sources
            streaming.value = false
          }
          nextTick(() => {
            const el = document.querySelector('.messages')
            if (el) el.scrollTop = el.scrollHeight
          })
        },
        // onDone & onError — 避免 chatSSE 内部调用 undefined 报错
        () => {},
        (err) => {
          streaming.value = false
          console.error('SSE 流式错误:', err)
        }
      )
      if (onConversationsChanged) await onConversationsChanged()
    } catch {
      messages.value[assistantIdx].content += ' [请求失败]'
      streaming.value = false
    }
  }

  function newChat() {
    router.push(`/app/${spaceId.value}/chat`)
  }

  async function selectConversation(conv) {
    if (conv.id === currentConvId.value) return
    router.push(`/app/${spaceId.value}/chat/${conv.id}`)
  }

  function cancelStreaming() {
    if (cancelFn) { cancelFn(); cancelFn = null }
    streaming.value = false
  }
  return { streaming, send, newChat, selectConversation, cancelStreaming }
}
