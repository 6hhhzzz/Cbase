<template>
  <div>
    <el-select
      :model-value="modelValue"
      @update:model-value="$emit('update:modelValue', $event)"
      multiple
      filterable
      placeholder="全部（继承完整权限）"
      style="width:100%"
      collapse-tags
      collapse-tags-tooltip
    >
      <el-option v-for="kb in kbOptions" :key="kb.value" :label="kb.label" :value="kb.value" />
    </el-select>
    <div style="font-size:12px;color:#999;margin-top:4px;">不选表示允许访问所有有权限的知识库</div>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: Array, default: () => [] },
  kbOptions: { type: Array, default: () => [] },
})
defineEmits(['update:modelValue'])
</script>
