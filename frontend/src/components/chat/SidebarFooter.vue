<template>
  <div class="sidebar-footer">
    <!-- 上下文标识 -->
    <div class="ctx-badge">{{ spaceName }} · {{ roleLabel }}</div>

    <!-- Space 控制台容器 -->
    <div class="console-box">
      <div class="console-title">Space 控制台</div>
      <div class="console-grid">
        <!-- 空间设置 -->
        <div class="console-item" @click="$emit('goSettings')">
          <el-icon :size="16"><Setting /></el-icon>
          <div class="item-content">
            <span class="item-title">空间设置</span>
            <span class="item-desc">{{ roleLabel }}权限</span>
          </div>
        </div>

        <!-- 文档管理 -->
        <div class="console-item" @click="$emit('goDocuments')">
          <el-icon :size="16"><Document /></el-icon>
          <div class="item-content">
            <span class="item-title">文档管理</span>
            <span class="item-desc">{{ docStats }}</span>
          </div>
        </div>

        <!-- MCP 服务 -->
        <div class="console-item console-item--wide" @click="$emit('goSettings')">
          <el-icon :size="16"><Connection /></el-icon>
          <div class="item-content">
            <span class="item-title">MCP 服务</span>
            <span class="item-desc">已启用</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部操作 -->
    <div class="footer-actions">
      <el-button text size="small" class="action-link" @click="$emit('switchSpace')">切换空间</el-button>
      <el-button text size="small" class="action-link action-link--danger" @click="$emit('logout')">退出登录</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Setting, Document, Connection } from '@element-plus/icons-vue'

const props = defineProps({
  spaceName: { type: String, default: '' },
  roleLabel: { type: String, default: '' },
  kbCount: { type: Number, default: 0 },
})

defineEmits(['goSettings', 'goDocuments', 'switchSpace', 'logout'])

const docStats = computed(() => {
  return props.kbCount > 0 ? `${props.kbCount} 个知识库` : '管理文档'
})
</script>

<style scoped>
/* ---- 容器 ---- */
.sidebar-footer {
  padding: 14px 16px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ---- 上下文标识 ---- */
.ctx-badge {
  font-size: 12px;
  color: #6b7280;
  padding: 0 2px;
}

/* ---- Space 控制台卡片 ---- */
.console-box {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
}

.console-title {
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  padding: 0 2px;
}

/* ---- 入口网格 ---- */
.console-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

/* ---- 单个入口 ---- */
.console-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
  color: #4b5563;
}

.console-item:hover {
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.console-item:active {
  background: #f3f4f6;
}

/* MCP 入口占满整行 */
.console-item--wide {
  grid-column: 1 / -1;
}

/* ---- 入口内容 ---- */
.item-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.item-title {
  font-size: 13px;
  font-weight: 500;
  color: #1f2937;
  line-height: 1.4;
}

.item-desc {
  font-size: 11px;
  color: #9ca3af;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ---- 底部操作链接 ---- */
.footer-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 2px;
}

.action-link {
  font-size: 12px;
  color: #9ca3af !important;
  padding: 4px 8px !important;
  height: auto !important;
}

.action-link:hover {
  color: #4b5563 !important;
  background: #f3f4f6 !important;
}

.action-link--danger:hover {
  color: #dc2626 !important;
  background: #fef2f2 !important;
}
</style>
