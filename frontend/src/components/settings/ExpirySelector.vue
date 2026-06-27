<template>
  <div>
    <el-select :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)" style="width:100%">
      <el-option :value="7" label="7 天" />
      <el-option :value="30" label="30 天" />
      <el-option :value="90" label="90 天" />
      <el-option :value="365" label="365 天" />
      <el-option :value="36500" label="100 年（永久）" />
    </el-select>
    <div style="font-size:12px;color:#999;margin-top:4px;">过期后密钥将无法使用，需续期或创建新密钥</div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: Number, default: 36500 },
})
defineEmits(['update:modelValue'])
</script>
