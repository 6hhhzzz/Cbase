<template>
  <div>
    <el-alert type="success" title="密钥已创建" :closable="false" style="margin-bottom:12px;" />
    <div style="background:#f5f7fa;padding:12px;border-radius:6px;margin-bottom:12px;">
      <div style="font-size:12px;color:#999;margin-bottom:4px;">密钥（仅显示一次，请立即复制）</div>
      <div style="display:flex;gap:8px;">
        <code style="flex:1;word-break:break-all;font-size:13px;">{{ apiKey }}</code>
        <el-button size="small" @click="copy(apiKey)">复制</el-button>
      </div>
    </div>
    <div style="background:#f5f7fa;padding:12px;border-radius:6px;">
      <div style="font-size:12px;color:#999;margin-bottom:4px;">
        .claude/settings.json（合并到已有配置中，不要整文件覆盖）
        <el-button size="small" text @click="copy(configSnippet)">复制全部</el-button>
      </div>
      <el-alert type="warning" :closable="false" style="margin-bottom:8px;font-size:12px;">
        如果你的 settings.json 已有其他配置（如 enabledPlugins），请只复制 mcpServers.kes 部分合并进去，不要直接覆盖整个文件。
      </el-alert>
      <pre style="font-size:12px;overflow-x:auto;margin:0;">{{ configSnippet }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'

defineProps({
  apiKey: { type: String, default: '' },
  configSnippet: { type: String, default: '' },
})

function copy(text) {
  navigator.clipboard.writeText(text).then(() => ElMessage.success('已复制'))
}
</script>
