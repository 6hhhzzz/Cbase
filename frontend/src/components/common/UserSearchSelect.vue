<template>
  <el-select :model-value="modelValue" filterable remote :remote-method="searchUsers"
    placeholder="输入用户名搜索" style="width:100%"
    :loading="searching" clearable @update:model-value="$emit('update:modelValue', $event)">
    <el-option v-for="u in userOptions" :key="u.user_id"
      :label="`${u.username} (${u.display_name || ''})`" :value="u.user_id" />
  </el-select>
</template>

<script setup>
import { useUserSearch } from '../../composables/useUserSearch'

defineProps({
  modelValue: { type: String, default: '' },
})

defineEmits(['update:modelValue'])

const { userOptions, searching, searchUsers } = useUserSearch()
</script>
