<template>
  <el-menu class="conv-list" :default-active="currentConvId">
    <el-menu-item v-for="conv in conversations" :key="conv.id"
      :index="conv.id" @click="$emit('select', conv)">
      <span>{{ conv.title || '新对话' }}</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup>
defineProps({
  conversations: { type: Array, default: () => [] },
  currentConvId: { type: String, default: '' },
})

defineEmits(['select'])
</script>

<style scoped>
.conv-list { flex: 1; overflow-y: auto; border-right: none; }
</style>
