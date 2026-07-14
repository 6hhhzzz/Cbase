<template>
  <el-menu class="conv-list" :default-active="currentConvId">
    <el-menu-item v-for="conv in conversations" :key="conv.id"
      :index="conv.id" @click="$emit('select', conv)">
      <span class="conv-item-title">{{ conv.title || '新对话' }}</span>
      <el-icon class="conv-item-delete" @click.stop="$emit('delete', conv)">
        <Delete />
      </el-icon>
    </el-menu-item>
  </el-menu>
</template>

<script setup>
import { Delete } from '@element-plus/icons-vue'

defineProps({
  conversations: { type: Array, default: () => [] },
  currentConvId: { type: String, default: '' },
})

defineEmits(['select', 'delete'])
</script>

<style scoped>
.conv-list { flex: 1; overflow-y: auto; border-right: none; }

:deep(.conv-list .el-menu-item) {
  display: flex;
  align-items: center;
}

.conv-item-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-item-delete {
  display: none;
  margin-left: auto;
  font-size: 14px;
  color: #dc2626;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  flex-shrink: 0;
}

.conv-item-delete:hover {
  background: #fef2f2;
}

:deep(.el-menu-item:hover .conv-item-delete) {
  display: inline-flex;
}
</style>
