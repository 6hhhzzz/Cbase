<template>
  <div class="kb-selector">
    <div class="kb-header" :class="{ 'kb-all': kbMode === 'all', 'kb-custom': kbMode === 'custom' }"
      @click="$emit('update:expanded', !expanded)">
      <span class="kb-header-text">【所有知识库】</span>
      <span class="kb-header-dot" :style="{ color: kbMode === 'all' ? '#67c23a' : '#409eff' }">
        {{ kbMode === 'all' ? '🟢' : '🔵' }}
      </span>
    </div>
    <div v-if="expanded" class="kb-list">
      <div v-for="kb in kbs" :key="kb.kb_id" class="kb-item" @click.stop="$emit('toggleKb', kb.kb_id)">
        <span class="kb-item-name">{{ kb.name || '未命名' }}</span>
        <el-tag v-if="kb.visibility === 'restricted'" size="small" type="warning" style="margin:0 4px">受限</el-tag>
        <span class="kb-item-toggle" :class="{ excluded: isExcluded(kb.kb_id) }"
          :title="isExcluded(kb.kb_id) ? '点击包含此知识库' : '点击排除此知识库'">
          {{ isExcluded(kb.kb_id) ? '✗' : '✓' }}
        </span>
      </div>
      <div v-if="excludedKbIds.length > 0" class="kb-reset" @click.stop="$emit('resetFilter')">
        重置为所有知识库
      </div>
    </div>
    <el-button size="small" style="width:100%;margin-top:6px" @click="$emit('manageKb')">管理知识库</el-button>
  </div>
</template>

<script setup>
const props = defineProps({
  kbs: { type: Array, required: true },
  kbMode: { type: String, default: 'all' },
  expanded: { type: Boolean, default: false },
  excludedKbIds: { type: Array, default: () => [] },
})

defineEmits(['update:expanded', 'toggleKb', 'resetFilter', 'manageKb'])

function isExcluded(kbId) {
  return (props.excludedKbIds || []).includes(kbId)
}
</script>

<style scoped>
.kb-selector { padding: 0 16px 12px; }
.kb-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px;
  border-radius: 6px; cursor: pointer; border: 1px solid #dcdfe6; font-size: 13px; user-select: none; }
.kb-header.kb-all { border-color: #67c23a; background: #f0f9eb; }
.kb-header.kb-custom { border-color: #409eff; background: #ecf5ff; }
.kb-header-text { font-weight: 600; }
.kb-header-dot { font-size: 14px; }
.kb-list { margin-top: 4px; border: 1px solid #ebeef5; border-radius: 4px; max-height: 200px; overflow-y: auto; }
.kb-item { display: flex; align-items: center; padding: 6px 10px; cursor: pointer; font-size: 13px;
  border-bottom: 1px solid #f2f3f5; }
.kb-item:last-child { border-bottom: none; }
.kb-item:hover { background: #f5f7fa; }
.kb-item-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-item-toggle { font-weight: bold; font-size: 14px; color: #67c23a; margin-left: 8px; }
.kb-item-toggle.excluded { color: #f56c6c; }
.kb-reset { padding: 6px 10px; text-align: center; cursor: pointer; font-size: 12px; color: #909399;
  border-top: 1px solid #f2f3f5; }
.kb-reset:hover { color: #409eff; background: #ecf5ff; }
</style>
