<template>
  <div class="input-area">
    <el-input v-model="model" placeholder="输入问题，按 Enter 发送"
      :disabled="disabled" @keydown.enter="$emit('send', model)" />
    <el-button type="primary" :disabled="!model.trim() || disabled" @click="$emit('send', model)">发送</el-button>
  </div>
</template>

<script setup>
defineProps({
  disabled: { type: Boolean, default: false },
})

const model = defineModel({ type: String, default: '' })

defineEmits(['send'])
</script>

<style scoped>
.input-area { display: flex; gap: 8px; padding: 16px; border-top: 1px solid #eee; }
</style>
