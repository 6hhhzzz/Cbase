<template>
  <div class="sidebar-footer">
    <div class="ctx-badge">{{ spaceName }} · {{ roleLabel }}</div>
    <el-button text @click="$emit('goSettings')">空间设置</el-button>
    <el-button text @click="$emit('goDocuments')">文档管理</el-button>
    <el-button text @click="$emit('switchSpace')">切换空间</el-button>
    <el-button text type="danger" @click="$emit('logout')">退出</el-button>
  </div>
</template>

<script setup>
defineProps({
  spaceName: { type: String, default: '' },
  roleLabel: { type: String, default: '' },
})

defineEmits(['goSettings', 'goDocuments', 'switchSpace', 'logout'])
</script>

<style scoped>
.sidebar-footer { padding: 12px 16px; border-top: 1px solid #eee; }
.ctx-badge { font-size: 12px; color: #666; margin-bottom: 4px; }
</style>
