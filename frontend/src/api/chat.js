/** Chat API — SSE 流式问答 + 反馈提交 */
import api from './client.js'

const SSE_FIRST_TOKEN_TIMEOUT = 60000
const SSE_TOTAL_TIMEOUT = 120000

export function chatSSE(query, convId, excludedKbIds, onToken, onDone, onError) {
  const controller = new AbortController()
  let firstTokenTimer = null
  let totalTimer = null
  let hasFirstToken = false
  let cancelled = false

  const cancel = () => {
    cancelled = true
    controller.abort()
    if (firstTokenTimer) clearTimeout(firstTokenTimer)
    if (totalTimer) clearTimeout(totalTimer)
  }

  const body = {
    query,
    conversation_id: convId || null,
    excluded_kb_ids: excludedKbIds || [],
  }

  firstTokenTimer = setTimeout(() => {
    if (!hasFirstToken) {
      cancel()
      onError(new Error('SSE 首 token 超时'))
    }
  }, SSE_FIRST_TOKEN_TIMEOUT)

  totalTimer = setTimeout(() => {
    cancel()
    onError(new Error('SSE 总超时'))
  }, SSE_TOTAL_TIMEOUT)

  const token = localStorage.getItem('context_token')
  fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const text = await response.text()
        throw new Error(text || `HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (!data.trim()) continue
            try {
              const chunk = JSON.parse(data)
              if (!hasFirstToken) {
                hasFirstToken = true
                if (firstTokenTimer) clearTimeout(firstTokenTimer)
              }
              if (chunk.done) {
                if (totalTimer) clearTimeout(totalTimer)
                onDone(chunk)
                return
              }
              onToken(chunk)
            } catch {
              // ignore parse errors
            }
          }
        }
      }
    })
    .catch((err) => {
      if (!cancelled) {
        onError(err)
      }
    })

  return cancel
}

export function submitFeedback(traceId, rating, reason) {
  return api.post('/chat/feedback', {
    trace_id: traceId,
    rating,
    reason: reason || '',
  })
}
