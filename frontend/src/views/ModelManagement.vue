<template>
  <div class="model-mgmt">
    <!-- ========== Provider 管理 ========== -->
    <el-card class="section">
      <template #header>
        <span>模型供应商</span>
        <el-button size="small" type="primary" @click="openProviderDialog()" style="float:right">+ 添加</el-button>
      </template>
      <el-table :data="providerList" stripe>
        <el-table-column prop="name" label="名称" width="120" />
        <el-table-column prop="type" label="类型" width="150">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'local' ? 'warning' : row.type === 'ollama' ? 'success' : ''">
              {{ row.type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="base_url" label="Base URL" min-width="200" show-overflow-tooltip />
        <el-table-column label="API Key" width="160">
          <template #default="{ row }">{{ row.api_key || '(无需)' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="openProviderDialog(row.name)">编辑</el-button>
            <el-button size="small" @click="testProvider(row)" :loading="testing[row.name]">测试</el-button>
            <el-popconfirm title="确认删除？" @confirm="doDeleteProvider(row.name)">
              <template #reference><el-button size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Provider 对话框 -->
    <el-dialog v-model="providerDlg.visible" :title="providerDlg.isEdit ? '编辑供应商' : '添加供应商'" width="500px">
      <el-form label-width="120px">
        <el-form-item label="Key (唯一标识)"><el-input v-model="providerDlg.form.name" placeholder="如 dashscope, ollama-local" :disabled="providerDlg.isEdit" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="providerDlg.form.type">
            <el-option value="openai_compatible" label="OpenAI 兼容 (API)" />
            <el-option value="ollama" label="Ollama (本地 API)" />
            <el-option value="local" label="本地 (HuggingFace)" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL" v-if="providerDlg.form.type !== 'local'"><el-input v-model="providerDlg.form.base_url" placeholder="https://..." /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="providerDlg.form.api_key" placeholder="${DASHSCOPE_API_KEY}" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="providerDlg.form.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDlg.visible = false">取消</el-button>
        <el-button type="primary" @click="doSaveProvider">保存</el-button>
      </template>
    </el-dialog>

    <!-- ========== Model 管理 ========== -->
    <el-card class="section">
      <template #header>
        <span>模型实例</span>
        <el-button size="small" type="primary" @click="openModelDialog()" style="float:right">+ 添加</el-button>
      </template>
      <el-table :data="modelList" stripe>
        <el-table-column prop="name" label="Key" width="140" />
        <el-table-column prop="model_name" label="模型名" min-width="200" />
        <el-table-column prop="model_type" label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.model_type === 'chat' ? '' : row.model_type === 'embedding' ? 'success' : row.model_type === 'reranker' ? 'warning' : 'info'">
              {{ row.model_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="供应商" width="100" />
        <el-table-column prop="dimension" label="维度" width="70">
          <template #default="{ row }">{{ row.dimension || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="openModelDialog(row.name)">编辑</el-button>
            <el-popconfirm title="确认删除？" @confirm="doDeleteModel(row.name)">
              <template #reference><el-button size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Model 对话框 -->
    <el-dialog v-model="modelDlg.visible" :title="modelDlg.isEdit ? '编辑模型' : '添加模型'" width="500px">
      <el-form label-width="120px">
        <el-form-item label="Key (唯一标识)"><el-input v-model="modelDlg.form.name" placeholder="如 qwen-plus" :disabled="modelDlg.isEdit" /></el-form-item>
        <el-form-item label="模型名"><el-input v-model="modelDlg.form.model_name" placeholder="实际 API 模型名" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="modelDlg.form.model_type">
            <el-option v-for="t in modelTypes" :key="t" :value="t" :label="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="供应商">
          <el-select v-model="modelDlg.form.provider">
            <el-option v-for="p in providerList" :key="p.name" :value="p.name" :label="p.name" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="modelDlg.form.model_type === 'embedding'" label="向量维度"><el-input-number v-model="modelDlg.form.dimension" :min="128" :max="8192" /></el-form-item>
        <el-form-item v-if="modelDlg.form.model_type === 'chat'" label="Max Tokens"><el-input-number v-model="modelDlg.form.max_tokens" :min="512" :max="1048576" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDlg.visible = false">取消</el-button>
        <el-button type="primary" @click="doSaveModel">保存</el-button>
      </template>
    </el-dialog>

    <!-- ========== 环节映射 ========== -->
    <el-card class="section">
      <template #header>
        <span>环节 → 模型映射</span>
        <el-button size="small" @click="openAssignmentDialog()" style="float:right">+ 添加环节</el-button>
      </template>
      <el-table :data="assignmentList" stripe>
        <el-table-column prop="purpose" label="环节 Key" width="140" />
        <el-table-column prop="description" label="说明" min-width="200" />
        <el-table-column prop="model" label="模型" width="150" />
        <el-table-column prop="fallback" label="降级目标" width="120">
          <template #default="{ row }">{{ row.fallback || '无' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" @click="openAssignmentDialog(row.purpose)">编辑</el-button>
            <el-popconfirm title="确认删除？" @confirm="doDeleteAssignment(row.purpose)">
              <template #reference><el-button size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Assignment 对话框 -->
    <el-dialog v-model="assignmentDlg.visible" :title="assignmentDlg.isEdit ? '编辑环节' : '添加环节'" width="450px">
      <el-form label-width="100px">
        <el-form-item label="环节 Key"><el-input v-model="assignmentDlg.form.purpose" placeholder="如 code, vision" :disabled="assignmentDlg.isEdit" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="assignmentDlg.form.description" placeholder="用途说明" /></el-form-item>
        <el-form-item label="模型">
          <el-select v-model="assignmentDlg.form.model" placeholder="选择模型">
            <el-option v-for="m in modelList" :key="m.name" :value="m.name" :label="`${m.name} (${m.model_type})`" />
          </el-select>
        </el-form-item>
        <el-form-item label="降级目标">
          <el-select v-model="assignmentDlg.form.fallback" clearable placeholder="无降级">
            <el-option v-for="a in assignmentList" :key="a.purpose" :value="a.purpose" :label="a.purpose" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignmentDlg.visible = false">取消</el-button>
        <el-button type="primary" @click="doSaveAssignment">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { modelAdminApi } from '../api'

// ── 配置数据（models.yaml 的 JSON 镜像）──
const configData = reactive({
  providers: {},
  models: {},
  assignments: {},
})

const testing = reactive({})

// ── 计算属性 ──
const providerList = computed(() => Object.entries(configData.providers).map(([name, p]) => ({ name, ...p })))
const modelList = computed(() => Object.entries(configData.models).map(([name, m]) => ({ name, ...m })))
const assignmentList = computed(() => Object.entries(configData.assignments).map(([purpose, a]) => ({ purpose, ...a })))
const modelTypes = ['chat', 'embedding', 'reranker', 'splade']

// ── 加载配置 ──
async function loadConfig() {
  try {
    const res = await modelAdminApi.getConfig()
    const data = res.data?.data || res.data
    if (!data.error) {
      configData.providers = data.providers || {}
      configData.models = data.models || {}
      configData.assignments = {}
      for (const [k, v] of Object.entries(data.assignments || {})) {
        configData.assignments[k] = { model: v.model, fallback: v.fallback || null, description: v.description || '' }
      }
    }
  } catch {
    ElMessage.warning('加载模型配置失败')
  }
}

// ── 保存配置（JSON → PUT）──
async function saveConfig() {
  const raw = {
    version: 2,
    providers: configData.providers,
    models: configData.models,
    assignments: configData.assignments,
  }
  try {
    await modelAdminApi.updateConfig(JSON.stringify(raw))
    ElMessage.success('配置已保存，30 秒内生效')
  } catch {
    ElMessage.error('保存失败')
  }
}

// ── Provider CRUD ──
const providerDlg = reactive({ visible: false, isEdit: false, form: {} })
function resetProviderForm() { return { name: '', type: 'openai_compatible', base_url: '', api_key: '', description: '' } }
function openProviderDialog(key) {
  providerDlg.isEdit = !!key
  providerDlg.form = key ? { name: key, ...configData.providers[key] } : resetProviderForm()
  providerDlg.visible = true
}
function doSaveProvider() {
  const f = providerDlg.form
  configData.providers[f.name] = { type: f.type, base_url: f.base_url || '', api_key: f.api_key || '', description: f.description || '' }
  providerDlg.visible = false
  saveConfig()
}
function doDeleteProvider(key) { delete configData.providers[key]; saveConfig() }

async function testProvider(row) {
  testing[row.name] = true
  try {
    await modelAdminApi.test(row.name)
    ElMessage.success('连接成功')
  } catch { ElMessage.error('连接失败') } finally { testing[row.name] = false }
}

// ── Model CRUD ──
const modelDlg = reactive({ visible: false, isEdit: false, form: {} })
function resetModelForm() { return { name: '', model_name: '', model_type: 'chat', provider: '', max_tokens: 8192, dimension: 0 } }
function openModelDialog(key) {
  modelDlg.isEdit = !!key
  modelDlg.form = key ? { name: key, ...configData.models[key] } : resetModelForm()
  modelDlg.visible = true
}
function doSaveModel() {
  const f = modelDlg.form
  const entry = { provider: f.provider, model_name: f.model_name, model_type: f.model_type }
  if (f.model_type === 'chat') { entry.max_tokens = f.max_tokens || 8192; entry.params = {}; entry.timeout = {} }
  if (f.model_type === 'embedding') { entry.dimension = f.dimension || 1024 }
  configData.models[f.name] = entry
  modelDlg.visible = false
  saveConfig()
}
function doDeleteModel(key) { delete configData.models[key]; saveConfig() }

// ── Assignment CRUD ──
const assignmentDlg = reactive({ visible: false, isEdit: false, form: {} })
function resetAssignmentForm() { return { purpose: '', model: '', fallback: null, description: '' } }
function openAssignmentDialog(key) {
  assignmentDlg.isEdit = !!key
  assignmentDlg.form = key ? { purpose: key, ...configData.assignments[key] } : resetAssignmentForm()
  assignmentDlg.visible = true
}
function doSaveAssignment() {
  const f = assignmentDlg.form
  configData.assignments[f.purpose] = { model: f.model, fallback: f.fallback || null, description: f.description || '' }
  assignmentDlg.visible = false
  saveConfig()
}
function doDeleteAssignment(key) { delete configData.assignments[key]; saveConfig() }

onMounted(loadConfig)
</script>

<style scoped>
.model-mgmt { padding: 0; }
.section { margin-bottom: 16px; }
</style>
