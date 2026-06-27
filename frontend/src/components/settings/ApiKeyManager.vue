<template>
  <div class="api-key-manager">
    <div style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center;">
      <div>
        <el-button type="primary" size="small" @click="showCreate = true">创建密钥</el-button>
      </div>
      <div style="color:#999;font-size:12px;">
        Space ID: <code>{{ spaceId }}</code>
        <el-tooltip content="配置 MCP Client 时需要填入此 Space ID">
          <el-icon style="margin-left:4px;cursor:help;"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
    </div>

    <el-table :data="keys" stripe v-loading="loading">
      <el-table-column prop="name" label="名称" min-width="130" />
      <el-table-column prop="key_prefix" label="密钥前缀" width="170">
        <template #default="{ row }">{{ row.key_prefix }}****</template>
      </el-table-column>
      <el-table-column label="KB 范围" width="120">
        <template #default="{ row }">
          <span v-if="!row.scope_kb_ids" style="color:#67c23a;">全部</span>
          <el-tooltip v-else :content="formatScopeNames(row.scope_kb_ids)" placement="top">
            <span style="color:#409eff;cursor:help;">{{ scopeCount(row.scope_kb_ids) }} 个 KB</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.revoked" type="danger" size="small">已撤销</el-tag>
          <el-tag v-else-if="row.expired" type="warning" size="small">已过期</el-tag>
          <el-tag v-else type="success" size="small">有效</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="过期时间" width="150">
        <template #default="{ row }">{{ fmtTime(row.expires_at) }}</template>
      </el-table-column>
      <el-table-column label="最后使用" width="150">
        <template #default="{ row }">{{ row.last_used_at ? fmtTime(row.last_used_at) : '从未' }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="220">
        <template #default="{ row }">
          <el-button v-if="!row.revoked" size="small" :loading="scoping === row.id"
            @click="openScope(row)">修改范围</el-button>
          <el-button v-if="!row.revoked && !row.expired" size="small" type="danger"
            :loading="revoking === row.id" @click="revoke(row)">撤销</el-button>
          <el-button v-else-if="!row.revoked && row.expired" size="small" type="warning"
            :loading="extending === row.id" @click="openExtend(row)">续期</el-button>
          <span v-else style="color:#999;">&mdash;</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="!loading && keys.length === 0" style="text-align:center;padding:40px;color:#999;">
      还没有 API 密钥。创建后可将 KES 知识库接入 Claude Desktop、Cursor 等 AI 工具。
    </div>

    <!-- 创建弹窗 -->
    <el-dialog v-model="showCreate" title="创建 API 密钥" width="560px" @closed="resetCreate">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="名称" prop="name" required>
          <el-input v-model="createForm.name" placeholder="如: Cursor Agent" maxlength="64" />
        </el-form-item>
        <el-form-item label="有效期" required>
          <ExpirySelector v-model="createForm.expires_days" />
        </el-form-item>
        <el-form-item label="KB 范围">
          <KbScopeSelect v-model="createForm.scope_kb_ids" :kb-options="kbOptions" />
        </el-form-item>
      </el-form>
      <CreatedKeyDisplay v-if="createdKey" :api-key="createdKey.api_key" :config-snippet="configSnippet" />
      <template #footer>
        <el-button v-if="!createdKey" @click="showCreate = false">取消</el-button>
        <el-button v-if="!createdKey" type="primary" :loading="creating" @click="doCreate">创建</el-button>
        <el-button v-else type="primary" @click="showCreate = false; createdKey = null">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 续期弹窗 -->
    <el-dialog v-model="showExtend" title="续期 API 密钥" width="400px" @closed="resetExtend">
      <el-form :model="extendForm" label-width="100px">
        <el-form-item label="密钥名称">
          <span>{{ extendTarget?.name }}</span>
        </el-form-item>
        <el-form-item label="新有效期" required>
          <ExpirySelector v-model="extendForm.expires_days" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showExtend = false">取消</el-button>
        <el-button type="primary" :loading="extending" @click="doExtend">确认续期</el-button>
      </template>
    </el-dialog>

    <!-- 修改范围弹窗 -->
    <el-dialog v-model="showScope" title="修改 KB 范围" width="500px" @closed="resetScope">
      <el-form :model="scopeForm" label-width="100px">
        <el-form-item label="密钥名称">
          <span>{{ scopeTarget?.name }}</span>
        </el-form-item>
        <el-form-item label="KB 范围">
          <KbScopeSelect v-model="scopeForm.scope_kb_ids" :kb-options="kbOptions" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showScope = false">取消</el-button>
        <el-button type="primary" :loading="scoping" @click="doScopeUpdate">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { fmtTime } from '../../utils/datetime'
import ExpirySelector from './ExpirySelector.vue'
import KbScopeSelect from './KbScopeSelect.vue'
import CreatedKeyDisplay from './CreatedKeyDisplay.vue'

const props = defineProps({ spaceId: { type: String, required: true } })

const keys = ref([])
const kbOptions = ref([])
const kbNameMap = ref({})
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const createdKey = ref(null)
const showExtend = ref(false)
const extending = ref(false)
const extendTarget = ref(null)
const extendForm = ref({ expires_days: 36500 })
const showScope = ref(false)
const scoping = ref(false)
const scopeTarget = ref(null)
const scopeForm = ref({ scope_kb_ids: [] })
const revoking = ref(null)
const createForm = ref({ name: '', expires_days: 36500, scope_kb_ids: [] })
const createRules = { name: [{ required: true, message: '请输入密钥名称', trigger: 'blur' }] }

const configSnippet = computed(() => {
  if (!createdKey.value) return ''
  return JSON.stringify({
    mcpServers: {
      kes: {
        command: 'python',
        args: ['-m', 'kes_mcp.server'],
        env: { KES_API_KEY: createdKey.value.api_key, KES_SPACE_ID: props.spaceId },
      },
    },
  }, null, 2)
})

async function loadKeys() {
  loading.value = true
  try {
    const res = await api.get('/auth/mcp/keys')
    keys.value = (res.data.data || []).map(k => ({ ...k }))
  } catch { /* interceptor */ }
  finally { loading.value = false }
}

async function loadKbs() {
  try {
    const res = await api.get(`/spaces/${props.spaceId}/kbs`)
    const kbs = res.data.data || []
    kbOptions.value = kbs.map(k => ({ label: k.name || k.kb_id, value: k.kb_id }))
    kbNameMap.value = {}
    kbs.forEach(k => { kbNameMap.value[k.kb_id] = k.name || k.kb_id })
  } catch { /* ignore */ }
}

function parseScopeIds(raw) {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  try { return JSON.parse(raw) } catch { return [] }
}

function scopeCount(raw) { return parseScopeIds(raw).length }

function formatScopeNames(raw) {
  const ids = parseScopeIds(raw)
  if (!ids.length) return '全部'
  return ids.map(id => kbNameMap.value[id] || id).join('、')
}

async function doCreate() {
  if (!createForm.value.name.trim()) { ElMessage.warning('请输入密钥名称'); return }
  creating.value = true
  try {
    const body = { name: createForm.value.name, expires_days: createForm.value.expires_days }
    if (createForm.value.scope_kb_ids && createForm.value.scope_kb_ids.length > 0) {
      body.scope_kb_ids = createForm.value.scope_kb_ids
    }
    const res = await api.post('/auth/mcp/keys', body)
    createdKey.value = res.data.data
    loadKeys()
  } catch { /* interceptor */ }
  finally { creating.value = false }
}

async function revoke(row) {
  try {
    await ElMessageBox.confirm(`确定撤销密钥「${row.name}」吗？撤销后立即失效。`, '确认撤销', { type: 'warning' })
  } catch { return }
  revoking.value = row.id
  try {
    await api.delete(`/auth/mcp/keys/${row.id}`)
    ElMessage.success('已撤销')
    loadKeys()
  } catch { /* interceptor */ }
  finally { revoking.value = null }
}

function openExtend(row) {
  extendTarget.value = row
  extendForm.value.expires_days = 36500
  showExtend.value = true
}

async function doExtend() {
  extending.value = true
  try {
    await api.post(`/auth/mcp/keys/${extendTarget.value.id}/extend`, { expires_days: extendForm.value.expires_days })
    ElMessage.success('密钥已续期')
    showExtend.value = false
    loadKeys()
  } catch { /* interceptor */ }
  finally { extending.value = false }
}

function openScope(row) {
  scopeTarget.value = row
  scopeForm.value.scope_kb_ids = parseScopeIds(row.scope_kb_ids) || []
  showScope.value = true
}

async function doScopeUpdate() {
  scoping.value = true
  try {
    const body = {}
    if (scopeForm.value.scope_kb_ids && scopeForm.value.scope_kb_ids.length > 0) {
      body.scope_kb_ids = scopeForm.value.scope_kb_ids
    } else { body.scope_kb_ids = null }
    await api.put(`/auth/mcp/keys/${scopeTarget.value.id}/scope`, body)
    ElMessage.success('KB 范围已更新')
    showScope.value = false
    loadKeys()
  } catch { /* interceptor */ }
  finally { scoping.value = false }
}

function resetCreate() {
  createForm.value = { name: '', expires_days: 36500, scope_kb_ids: [] }
  createdKey.value = null
}

function resetExtend() {
  extendTarget.value = null
  extendForm.value = { expires_days: 36500 }
}

function resetScope() {
  scopeTarget.value = null
  scopeForm.value = { scope_kb_ids: [] }
}

onMounted(() => { loadKeys(); loadKbs() })
</script>

<style scoped>
.api-key-manager { padding: 4px 0; }
pre { background: #fff; padding: 10px; border-radius: 4px; font-family: monospace; }
</style>
