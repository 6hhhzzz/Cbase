/**
 * ChatMessage 组件测试 — 渲染、Markdown、XSS 防护
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

// Mock ElementPlus components used in ChatMessage
const MockComponents = {
  'el-collapse': { template: '<div><slot /></div>', props: ['modelValue'] },
  'el-collapse-item': { template: '<div><slot name="title" /><slot /></div>', props: ['title'] },
}

import ChatMessage from '../components/chat/ChatMessage.vue'

function mountMessage(props = {}) {
  return mount(ChatMessage, {
    props: { msg: { role: 'user', content: '' }, streaming: false, ...props },
    global: { components: MockComponents },
  })
}

describe('ChatMessage', () => {
  it('renders user message', () => {
    const wrapper = mountMessage({ msg: { role: 'user', content: '你好' } })
    expect(wrapper.find('.user-msg').exists()).toBe(true)
    expect(wrapper.find('.msg-role').text()).toBe('我')
    expect(wrapper.text()).toContain('你好')
  })

  it('renders assistant message with markdown', () => {
    const wrapper = mountMessage({ msg: { role: 'assistant', content: '**加粗** 文本' } })
    expect(wrapper.find('.assistant-msg').exists()).toBe(true)
    expect(wrapper.find('.msg-role').text()).toBe('AI 助手')
    expect(wrapper.html()).toContain('<strong>加粗</strong>')
  })

  it('shows thinking placeholder when streaming with empty content', () => {
    const wrapper = mountMessage({ msg: { role: 'assistant', content: '' }, streaming: true })
    expect(wrapper.text()).toContain('思考中...')
  })

  it('sanitizes dangerous HTML via DOMPurify', () => {
    const wrapper = mountMessage({
      msg: { role: 'assistant', content: '<script>alert("xss")</script> 正常文本' },
    })
    expect(wrapper.html()).not.toContain('<script>')
    expect(wrapper.text()).toContain('正常文本')
  })

  it('renders sources when provided', () => {
    const wrapper = mountMessage({
      msg: {
        role: 'assistant', content: '答案',
        sources: [{ filename: 'doc.pdf', score: 0.95, chunk_text: '段落内容' }],
      },
    })
    // The collapse component text should include the filename and score
    expect(wrapper.text()).toContain('doc.pdf')
    expect(wrapper.text()).toContain('95.0')
  })

  it('renders plain text for non-assistant messages', () => {
    const wrapper = mountMessage({ msg: { role: 'user', content: '普通消息' } })
    // User messages use span, not markdown-body
    expect(wrapper.find('.markdown-body').exists()).toBe(false)
    expect(wrapper.text()).toContain('普通消息')
  })
})
