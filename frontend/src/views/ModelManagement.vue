<template>
  <div class="model-mgmt">
    <!-- ========== Provider 管理 ========== -->
    <el-card class="section">
      <template #header>
        <span>模型供应商</span>
        <el-button size="small" type="primary" @click="openProviderDialog()" style="float:right">+ 添加</el-button>
      </template>
      <el-table :data="providers" stripe>
        <el-table-column prop="name" label="名称" width="120" />
        <el-table-column prop="type" label="类型" width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'ollama' ? 'success' : row.type === 'cross_encoder' ? 'warning' : ''">
              {{ row.type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="base_url" label="Base URL" min-width="200" show-overflow-tooltip />
        <el-table-column label="API Key" width="160">
          <template #default="{ row }">{{ row.api_key_env || '(无需)' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'danger'" size="small">
              {{ row.is_enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button size="small" @click="openProviderDialog(row)">编辑</el-button>
            <el-button size="small" @click="testProvider(row)" :loading="testing[row.id]">测试</el-button>
            <el-popconfirm title="删除后关联的模型也将删除，确认？" @confirm="doDeleteProvider(row.id)">
              <template #reference><el-button size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ========== Provider 对话框 ========== -->
    <el-dialog v-model="providerDlg.visible" :title="providerDlg.isEdit ? '编辑供应商' : '添加供应商'" width="500px">
      <el-form label-width="100px">
        <el-form-item label="名称"><el-input v-model="providerDlg.form.name" placeholder="如 dashscope, ollama" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="providerDlg.form.type">
            <el-option value="openai_compatible" label="OpenAI 兼容" />
            <el-option value="ollama" label="Ollama (本地)" />
            <el-option value="cross_encoder" label="Cross Encoder (本地)" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL"><el-input v-model="providerDlg.form.baseUrl" placeholder="https://..." /></el-form-item>
        <el-form-item label="API Key 环境变量"><el-input v-model="providerDlg.form.apiKeyEnv" placeholder="${DASHSCOPE_API_KEY}" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="providerDlg.form.isEnabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDlg.visible = false">取消</el-button>
        <el-button type="primary" @click="doSaveProvider" :loading="providerDlg.saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- ========== Model Config 管理 ========== -->
    <el-card class="section">
      <template #header>
        <span>模型实例</span>
        <el-select v-model="selectedProviderId" placeholder="选择供应商" clearable style="width:200px;margin-left:16px" @change="loadConfigs">
          <el-option v-for="p in providers" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-button v-if="selectedProviderId" size="small" type="primary" @click="discoverModels" :loading="discovering" style="float:right;margin-left:8px">自动发现</el-button>
        <el-button v-if="selectedProviderId" size="small" @click="openConfigDialog()" style="float:right">+ 添加</el-button>
      </template>
      <el-table :data="configs" stripe v-if="selectedProviderId">
        <el-table-column prop="model_name" label="模型名" min-width="160" />
        <el-table-column prop="model_type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.model_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="dimension" label="维度" width="80">
          <template #default="{ row }">{{ row.dimension || '-' }}</template>
        </el-table-column>
        <el-table-column prop="max_tokens" label="Max Tokens" width="100">
          <template #default="{ row }">{{ row.max_tokens ? row.max_tokens.toLocaleString() : '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_enabled ? 'success' : 'danger'" size="small">{{ row.is_enabled ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="openConfigDialog(row)">编辑</el-button>
            <el-popconfirm title="确认删除？" @confirm="doDeleteConfig(row.id)">
              <template #reference><el-button size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="请先选择一个供应商" />
    </el-card>

    <!-- ========== Config 对话框 ========== -->
    <el-dialog v-model="configDlg.visible" :title="configDlg.isEdit ? '编辑模型' : '添加模型'" width="450px">
      <el-form label-width="100px">
        <el-form-item label="模型名"><el-input v-model="configDlg.form.modelName" placeholder="qwen-plus" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="configDlg.form.modelType">
            <el-option value="chat" label="Chat (对话)" />
            <el-option value="embedding" label="Embedding (向量)" />
            <el-option value="reranker" label="Reranker (重排)" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="configDlg.form.modelType === 'embedding'" label="向量维度"><el-input-number v-model="configDlg.form.dimension" :min="128" :max="8192" /></el-form-item>
        <el-form-item v-if="configDlg.form.modelType === 'chat'" label="Max Tokens"><el-input-number v-model="configDlg.form.maxTokens" :min="512" :max="1048576" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="configDlg.form.isEnabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configDlg.visible = false">取消</el-button>
        <el-button type="primary" @click="doSaveConfig" :loading="configDlg.saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- ========== 环节映射 ========== -->
    <el-card class="section">
      <template #header><span>环节 → 模型映射</span></template>
      <el-form label-width="120px" v-loading="assignmentLoading">
        <el-form-item v-for="p in purposes" :key="p.key" :label="p.label">
          <el-select v-model="assignments[p.key]" :placeholder="'选择 ' + p.label + ' 模型'" clearable style="width:400px" @change="doSaveAssignments">
            <el-option v-for="c in chatModels" :key="c.id" :label="`${c.provider_name}:${c.model_name}`" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { modelAdminApi } from '../api'

const purposes = [
  { key: 'chat', label: '对话生成 (chat)' },
  { key: 'rewrite', label: 'Query 改写 (rewrite)' },
  { key: 'intent', label: '意图分类 (intent)' },
  { key: 'embedding', label: '向量嵌入 (embedding)' },
  { key: 'reranker', label: '重排序 (reranker)' },
  { key: 'rerank_llm', label: 'LLM 重排降级' },
]

// ---- Provider ----
const providers = ref([])
const testing = reactive({})
const providerDlg = reactive({ visible: false, isEdit: false, saving: false, form: {} })

function resetProviderForm() {
  return { name: '', type: 'openai_compatible', baseUrl: '', apiKeyEnv: '', isEnabled: true }
}

function openProviderDialog(row) {
  providerDlg.isEdit = !!row
  providerDlg.form = row ? { ...row, baseUrl: row.base_url, apiKeyEnv: row.api_key_env, isEnabled: row.is_enabled } : resetProviderForm()
  providerDlg.visible = true
}

async function doSaveProvider() {
  providerDlg.saving = true
  try {
    const f = providerDlg.form
    const data = { name: f.name, type: f.type, base_url: f.baseUrl, api_key_env: f.apiKeyEnv, is_enabled: f.isEnabled }
    if (providerDlg.isEdit) {
      await modelAdminApi.updateProvider(f.id, data)
      ElMessage.success('已更新')
    } else {
      await modelAdminApi.createProvider(data)
      ElMessage.success('已添加')
    }
    providerDlg.visible = false
    loadProviders()
  } catch { ElMessage.error('保存失败') } finally { providerDlg.saving = false }
}

async function doDeleteProvider(id) {
  try {
    await modelAdminApi.deleteProvider(id)
    ElMessage.success('已删除')
    loadProviders()
  } catch { ElMessage.error('删除失败') }
}

async function testProvider(row) {
  testing[row.id] = true
  try {
    await modelAdminApi.test(row.id)
    ElMessage.success('连接成功')
  } catch { ElMessage.error('连接失败') } finally { testing[row.id] = false }
}

async function loadProviders() {
  try {
    const res = await modelAdminApi.listProviders()
    providers.value = res.data.data || []
  } catch { providers.value = [] }
}

// ---- Config ----
const selectedProviderId = ref('')
const configs = ref([])
const discovering = ref(false)
const configDlg = reactive({ visible: false, isEdit: false, saving: false, form: {} })

function resetConfigForm() {
  return { modelName: '', modelType: 'chat', dimension: null, maxTokens: null, isEnabled: true }
}

function openConfigDialog(row) {
  configDlg.isEdit = !!row
  configDlg.form = row ? { ...row, modelName: row.model_name, modelType: row.model_type, isEnabled: row.is_enabled } : resetConfigForm()
  if (!configDlg.form.providerId) configDlg.form.providerId = selectedProviderId.value
  configDlg.visible = true
}

async function doSaveConfig() {
  configDlg.saving = true
  try {
    const f = configDlg.form
    const data = { provider_id: selectedProviderId.value, model_name: f.modelName, model_type: f.modelType, dimension: f.dimension, max_tokens: f.maxTokens, is_enabled: f.isEnabled }
    if (configDlg.isEdit) {
      await modelAdminApi.updateConfig(f.id, data)
      ElMessage.success('已更新')
    } else {
      await modelAdminApi.createConfig(data)
      ElMessage.success('已添加')
    }
    configDlg.visible = false
    loadConfigs()
  } catch { ElMessage.error('保存失败') } finally { configDlg.saving = false }
}

async function doDeleteConfig(id) {
  try {
    await modelAdminApi.deleteConfig(id)
    ElMessage.success('已删除')
    loadConfigs()
  } catch { ElMessage.error('删除失败') }
}

async function loadConfigs() {
  if (!selectedProviderId.value) { configs.value = []; return }
  try {
    const res = await modelAdminApi.listConfigs(selectedProviderId.value)
    configs.value = res.data.data || []
  } catch { configs.value = [] }
}

async function discoverModels() {
  discovering.value = true
  try {
    const res = await modelAdminApi.discover(selectedProviderId.value)
    const models = res.data.data?.models || []
    if (models.length === 0) { ElMessage.warning('未发现模型'); return }
    // 批量添加
    let added = 0
    for (const m of models) {
      try {
        await modelAdminApi.createConfig({ provider_id: selectedProviderId.value, model_name: m.id, model_type: 'chat', is_enabled: true })
        added++
      } catch { /* skip duplicates */ }
    }
    ElMessage.success(`发现 ${models.length} 个模型，已添加 ${added} 个`)
    loadConfigs()
  } catch { ElMessage.error('模型发现失败') } finally { discovering.value = false }
}

// ---- Assignment ----
const assignmentLoading = ref(false)
const assignments = reactive({})
const allModels = ref([])

const chatModels = computed(() => allModels.value.filter(m => m.model_type === 'chat' || m.model_type === 'embedding'))

async function loadAssignments() {
  assignmentLoading.value = true
  try {
    const [aRes, cRes] = await Promise.all([
      modelAdminApi.getAssignments(),
      modelAdminApi.listConfigs(),
    ])
    const aMap = aRes.data.data || {}
    purposes.forEach(p => { assignments[p.key] = aMap[p.key] || null })
    allModels.value = cRes.data.data || []
  } catch {
    purposes.forEach(p => { assignments[p.key] = null })
  } finally { assignmentLoading.value = false }
}

async function doSaveAssignments() {
  const data = {}
  purposes.forEach(p => { data[p.key] = assignments[p.key] })
  try {
    await modelAdminApi.updateAssignments({ assignments: data })
    ElMessage.success('映射已保存')
  } catch { ElMessage.error('保存失败') }
}

// ---- Lifecycle ----
onMounted(() => { loadProviders(); loadAssignments() })
watch(selectedProviderId, () => loadConfigs())
</script>

<style scoped>
.model-mgmt { padding: 0; }
.section { margin-bottom: 16px; }
</style>
