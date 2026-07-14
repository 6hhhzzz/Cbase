<template>
  <div :class="['message', msg.role === 'user' ? 'user-msg' : 'assistant-msg']">
    <div class="msg-role">{{ msg.role === 'user' ? '我' : 'AI 助手' }}</div>
    <div class="msg-content">
      <span v-if="!msg.content && streaming && msg.role === 'assistant'">思考中...</span>
      <div
        v-else-if="msg.role === 'assistant'"
        class="markdown-body"
        v-html="renderMarkdown(msg.content)"
      ></div>
      <span v-else>{{ msg.content }}</span>
    </div>
    <div v-if="msg.sources && msg.sources.length" class="msg-sources">
      <el-collapse>
        <el-collapse-item title="参考来源">
          <div v-for="(src, j) in msg.sources" :key="j" class="source-item">
            <strong>{{ src.filename }}</strong> (相关度: {{ (src.score * 100).toFixed(1) }}%)
            <p>{{ src.chunk_text }}</p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
    <!-- 点赞/点踩 — 仅 assistant 消息且非 streaming 时显示 -->
    <div v-if="msg.role === 'assistant' && !streaming && msg.content" class="msg-feedback">
      <button
        :class="['fb-btn', { active: feedbackState === 'like', disabled: feedbackState === 'dislike' }]"
        :disabled="feedbackState !== null"
        title="回答满意"
        @click="doFeedback('like')"
      >👍</button>
      <button
        :class="['fb-btn', { active: feedbackState === 'dislike', disabled: feedbackState === 'like' }]"
        :disabled="feedbackState !== null"
        title="回答不佳"
        @click="doFeedback('dislike')"
      >👎</button>
      <span v-if="feedbackState" class="fb-done">{{ feedbackState === 'like' ? '已反馈 · 感谢' : '已反馈 · 我们会改进' }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { ElMessage } from 'element-plus'
import { submitFeedback } from '../../api'

const props = defineProps({
  msg: { type: Object, required: true },
  streaming: { type: Boolean, default: false },
})

const feedbackState = ref(null) // null | 'like' | 'dislike'

async function doFeedback(rating) {
  if (feedbackState.value) return
  if (!props.msg.traceId) {
    ElMessage({ message: '反馈功能暂不可用（缺少追踪标识）', type: 'warning', duration: 2000 })
    return
  }
  try {
    await submitFeedback(props.msg.traceId, rating)
    feedbackState.value = rating
    ElMessage({ message: rating === 'like' ? '感谢反馈！' : '感谢反馈，我们会持续改进', type: 'success', duration: 2000 })
  } catch {
    ElMessage({ message: '反馈提交失败，请稍后重试', type: 'error', duration: 2000 })
  }
}

// 配置 marked：保留换行渲染为 <br>（GFM 标准行为）
marked.setOptions({
  breaks: true,     // 单个 \n 渲染为 <br>
  gfm: true,        // GitHub Flavored Markdown（表格/任务列表/删除线）
})

function renderMarkdown(text) {
  if (!text) return ''
  // marked.parse 转换 Markdown → HTML，DOMPurify 清理 XSS
  const rawHtml = marked.parse(text)
  return DOMPurify.sanitize(rawHtml, { ALLOWED_TAGS: [
    'h1','h2','h3','h4','h5','h6',
    'p','br','hr',
    'ul','ol','li',
    'strong','em','del','ins',
    'code','pre','blockquote',
    'a','img',
    'table','thead','tbody','tr','th','td',
    'div','span',
  ]})
}
</script>

<style scoped>
.message { margin-bottom: 16px; }
.msg-role { font-size: 12px; color: #999; margin-bottom: 4px; }
.msg-content { line-height: 1.6; }
.source-item { margin-bottom: 8px; }
.source-item p { color: #666; font-size: 13px; margin-top: 4px; }

/* ── Markdown 渲染样式 ── */
.markdown-body :deep(h1) { font-size: 1.5em; font-weight: 700; margin: 0.8em 0 0.4em; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.2em; }
.markdown-body :deep(h2) { font-size: 1.3em; font-weight: 700; margin: 0.7em 0 0.3em; }
.markdown-body :deep(h3) { font-size: 1.15em; font-weight: 700; margin: 0.6em 0 0.2em; }
.markdown-body :deep(h4) { font-size: 1.05em; font-weight: 700; margin: 0.5em 0 0.15em; }
.markdown-body :deep(p) { margin: 0.4em 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 1.5em; margin: 0.4em 0; }
.markdown-body :deep(li) { margin: 0.15em 0; }
.markdown-body :deep(strong) { font-weight: 700; }
.markdown-body :deep(em) { font-style: italic; }
.markdown-body :deep(code) {
  background: #f3f4f6; padding: 0.15em 0.4em; border-radius: 3px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 0.9em;
}
.markdown-body :deep(pre) {
  background: #1e1e1e; color: #d4d4d4; padding: 0.8em 1em; border-radius: 6px;
  overflow-x: auto; margin: 0.5em 0; line-height: 1.5;
}
.markdown-body :deep(pre code) {
  background: none; padding: 0; border-radius: 0; color: inherit; font-size: 0.85em;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid #d1d5db; padding: 0.2em 0.8em; margin: 0.5em 0;
  color: #6b7280;
}
.markdown-body :deep(table) { border-collapse: collapse; margin: 0.5em 0; width: 100%; }
.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid #e5e7eb; padding: 0.4em 0.8em; text-align: left;
}
.markdown-body :deep(th) { background: #f9fafb; font-weight: 600; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid #e5e7eb; margin: 0.8em 0; }
.markdown-body :deep(a) { color: #2563eb; text-decoration: underline; }

/* ── 反馈按钮 ── */
.msg-feedback { margin-top: 8px; display: flex; gap: 6px; align-items: center; }
.fb-btn {
  background: none; border: 1px solid #e5e7eb; border-radius: 6px;
  padding: 2px 8px; cursor: pointer; font-size: 14px; line-height: 1.6;
  transition: all 0.15s; opacity: 0.5;
}
.fb-btn:not(:disabled):hover { opacity: 1; border-color: #1677ff; }
.fb-btn.active { opacity: 1; border-color: #1677ff; background: #e6f4ff; }
.fb-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.fb-btn.active:disabled { opacity: 1; cursor: default; }
.fb-done { font-size: 12px; color: #999; margin-left: 4px; }
</style>
