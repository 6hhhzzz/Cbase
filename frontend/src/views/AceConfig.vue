<template>
  <div class="ace-config">
    <div class="page-header">
      <h2>ACE 权限矩阵 — {{ spaceName }}</h2>
      <div class="header-actions">
        <el-button @click="loadAll">刷新</el-button>
        <el-button v-if="mode === 'kb'" type="primary" @click="showNewKbDialog">新建 KB</el-button>
      </div>
    </div>

    <el-radio-group v-model="mode" @change="onModeChange" style="margin-bottom:12px">
      <el-radio-button value="kb">KB 矩阵</el-radio-button>
      <el-radio-button value="document">文档矩阵</el-radio-button>
    </el-radio-group>

    <p class="hint">{{ mode === 'kb' ? '配置「用户组 ↔ KB ↔ 角色」关系。Deny 始终覆盖 Allow。' : '仅显示已阻断继承的文档。先在文档管理中关闭「继承权限」开关。Deny 始终覆盖 Allow。' }}</p>

    <!-- Matrix Table -->
    <div class="matrix-wrapper" v-if="rows.length > 0">
      <table class="ace-matrix">
        <thead>
          <tr>
            <th class="kb-col">{{ mode === 'kb' ? '知识库' : '文档' }}</th>
            <th v-for="col in columns" :key="col.id" class="principal-col">
              <div class="col-header">
                <span>{{ col.name }}</span>
                <el-tag size="small" :type="col.type === 'group' ? '' : 'info'">
                  {{ col.type === 'group' ? '组' : '用户' }}
                </el-tag>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td class="kb-col">
              <template v-if="mode === 'kb'">
                <div class="kb-name">{{ row.name }}</div>
                <el-tag size="small">{{ row.visibility === 'space_wide' ? '公开' : '受限' }}</el-tag>
              </template>
              <template v-else>
                <div class="kb-name">{{ row.filename || row.name }}</div>
                <el-tag size="small" type="info">{{ row.kb_name || '' }}</el-tag>
              </template>
            </td>
            <td v-for="col in columns" :key="col.id" class="cell" @click="openCellEditor(row, col)">
              <template v-if="getAce(row.id, col.id)">
                <span class="ace-display" :class="{ deny: getAce(row.id, col.id).effect === 'deny' }">
                  {{ getRoleName(getAce(row.id, col.id).role_id) }}
                </span>
                <span class="effect-tag" :class="getAce(row.id, col.id).effect">
                  {{ getAce(row.id, col.id).effect === 'deny' ? '✕' : '✓' }}
                </span>
              </template>
              <span v-else class="empty-cell">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-empty v-else :description="mode === 'kb' ? '暂无知识库，请先创建 KB' : '暂无阻断继承的文档。请先在文档管理中关闭某个文档的「继承权限」开关。'" />

    <!-- 新建 KB 对话框 -->
    <el-dialog v-model="newKbVisible" title="新建知识库" width="450px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="newKbForm.name" placeholder="KB 名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newKbForm.description" type="textarea" placeholder="可选" />
        </el-form-item>
        <el-form-item label="可见性">
          <el-radio-group v-model="newKbForm.visibility">
            <el-radio value="space_wide">公开</el-radio>
            <el-radio value="restricted">受限</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newKbVisible = false">取消</el-button>
        <el-button type="primary" @click="createKb">创建</el-button>
      </template>
    </el-dialog>

    <!-- 单元格编辑弹窗 -->
    <el-dialog v-model="cellVisible" :title="`配置: ${cellRow?.filename || cellRow?.name} ← ${cellCol?.name}`" width="400px">
      <el-form label-width="80px">
        <el-form-item label="角色">
          <el-select v-model="cellForm.role_id" placeholder="选择角色" style="width: 100%">
            <el-option v-for="r in allRoles" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="效果">
          <el-radio-group v-model="cellForm.effect">
            <el-radio value="allow">允许</el-radio>
            <el-radio value="deny">拒绝</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="优先级">
          <el-input-number v-model="cellForm.priority" :min="0" :max="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="existingAce" type="danger" @click="deleteAce">删除此规则</el-button>
        <el-button @click="cellVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAce">{{ existingAce ? '更新' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { spaceApi, rolesApi, documentsApi } from '../api'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const spaceId = computed(() => route.params.spaceId)
const spaceName = ref('')

const mode = ref(route.query.type === 'document' ? 'document' : 'kb')
const rows = ref([])       // KBs or documents
const columns = ref([])    // [{ id, name, type: 'group'|'user' }]
const aces = ref([])       // raw ACE list
const allRoles = ref([])

// New KB
const newKbVisible = ref(false)
const newKbForm = ref({ name: '', description: '', visibility: 'space_wide' })

// Cell editor
const cellVisible = ref(false)
const cellRow = ref(null)  // renamed from cellKb
const cellCol = ref(null)
const cellForm = ref({ role_id: '', effect: 'allow', priority: 0 })
const existingAce = ref(null)

const isSpaceAdmin = computed(() => authStore.isSpaceAdmin)

function getAce(resourceId, principalId) {
  return aces.value.find(a => a.resource_id === resourceId && a.principal_id === principalId)
}

function getRoleName(roleId) {
  return allRoles.value.find(r => r.id === roleId)?.name || '未知角色'
}

async function loadAll() {
  try {
    const rt = mode.value === 'kb' ? 'kb' : 'document'
    // Resources (KBs or docs)
    if (mode.value === 'kb') {
      const kbRes = await spaceApi.listKbs(spaceId.value)
      rows.value = (kbRes.data.data || []).map(k => ({ ...k, id: k.kb_id }))
    } else {
      // Document mode: get all docs, filter inherit_permissions=false
      const allKbs = (await spaceApi.listKbs(spaceId.value)).data.data || []
      const kbNames = {}
      allKbs.forEach(k => { kbNames[k.kb_id] = k.name })
      const kbIds = allKbs.map(k => k.kb_id)
      let docs = []
      for (const kbId of kbIds) {
        try {
          const r = await documentsApi.list({ kb_id: kbId, page_size: 200 })
          const pageData = r.data.data || {}
          docs.push(...(pageData.items || []))
        } catch { ElMessage.warning('部分 KB 文档加载失败') }
      }
      // 先加载文档 ACE，得到已配置了 ACE 的 doc_id
      const aceRes = await spaceApi.getAces(spaceId.value, rt)
      aces.value = aceRes.data.data || []
      const acedDocIds = new Set(aces.value.map(a => a.resource_id))

      // 显示: inherit_permissions=false 的文档 + 已配置 ACE 的文档
      docs = docs.filter(d => d.inherit_permissions === false || acedDocIds.has(d.id))
      docs.forEach(d => { d.kb_name = kbNames[d.kb_id] || '' })
      rows.value = docs.map(d => ({ id: d.id, filename: d.filename, kb_name: d.kb_name, kb_id: d.kb_id }))
    }

    // ACEs (KB 模式在这里获取)
    if (mode.value === 'kb') {
      const aceRes = await spaceApi.getAces(spaceId.value, rt)
      aces.value = aceRes.data.data || []
    }

    // Groups
    const grpRes = await spaceApi.getGroups(spaceId.value)
    const groups = grpRes.data.data || []
    columns.value = groups.map(g => ({ id: g.group_id, name: g.group_name || g.group_id, type: 'group' }))

    // Roles
    const roleRes = await rolesApi.list()
    allRoles.value = roleRes.data.data || []
  } catch (e) {
    console.error('加载 ACE 矩阵失败', e)
    ElMessage.error('加载 ACE 矩阵失败，请确认你是 Space 管理员')
  }
}

function onModeChange(val) {
  router.replace({ query: { type: val === 'document' ? 'document' : undefined } })
  loadAll()
}

function openCellEditor(row, col) {
  if (!isSpaceAdmin.value) return
  cellRow.value = row
  cellCol.value = col
  const ace = getAce(row.id, col.id)
  existingAce.value = ace
  if (ace) {
    cellForm.value = { role_id: ace.role_id, effect: ace.effect, priority: ace.priority || 0 }
  } else {
    cellForm.value = { role_id: allRoles.value[0]?.id || '', effect: 'allow', priority: 0 }
  }
  cellVisible.value = true
}

async function saveAce() {
  try {
    const payload = {
      resource_type: mode.value === 'kb' ? 'kb' : 'document',
      resource_id: cellRow.value.id || cellRow.value.kb_id,
      principal_type: cellCol.value.type,
      principal_id: cellCol.value.id,
      role_id: cellForm.value.role_id,
      effect: cellForm.value.effect,
      priority: cellForm.value.priority
    }
    if (existingAce.value) {
      await spaceApi.updateAce(spaceId.value, existingAce.value.id, payload)
    } else {
      await spaceApi.createAce(spaceId.value, payload)
    }
    ElMessage.success(existingAce.value ? 'ACE 已更新' : 'ACE 已创建')
    cellVisible.value = false
    loadAll()
  } catch { /* error handled by interceptor */ }
}

async function deleteAce() {
  try {
    await spaceApi.deleteAce(spaceId.value, existingAce.value.id)
    ElMessage.success('ACE 已删除')
    cellVisible.value = false
    loadAll()
  } catch { /* error handled by interceptor */ }
}

function showNewKbDialog() {
  newKbForm.value = { name: '', description: '', visibility: 'space_wide' }
  newKbVisible.value = true
}

async function createKb() {
  if (!newKbForm.value.name) { ElMessage.warning('请输入 KB 名称'); return }
  try {
    await spaceApi.createKb(spaceId.value, newKbForm.value.name, newKbForm.value.description, newKbForm.value.visibility)
    ElMessage.success('KB 已创建')
    newKbVisible.value = false
    loadAll()
  } catch { /* error handled by interceptor */ }
}

onMounted(loadAll)
</script>

<style scoped>
.ace-config { padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.page-header h2 { margin: 0; }
.header-actions { display: flex; gap: 8px; }
.hint { color: #999; margin-bottom: 16px; }

.matrix-wrapper { overflow-x: auto; }
.ace-matrix { border-collapse: collapse; width: 100%; min-width: 600px; }
.ace-matrix th, .ace-matrix td { border: 1px solid #e4e7ed; padding: 10px 14px; text-align: center; }
.ace-matrix th { background: #f5f7fa; font-weight: 600; white-space: nowrap; }
.kb-col { min-width: 160px; text-align: left !important; }
.principal-col { min-width: 140px; }
.col-header { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.kb-name { font-weight: 500; margin-bottom: 4px; }

.cell { cursor: pointer; transition: background 0.15s; }
.cell:hover { background: #ecf5ff; }
.ace-display { font-weight: 600; font-size: 14px; display: block; }
.ace-display.deny { color: #f56c6c; text-decoration: line-through; }
.effect-tag { font-size: 11px; display: block; margin-top: 2px; }
.effect-tag.allow { color: #67c23a; }
.effect-tag.deny { color: #f56c6c; }
.empty-cell { color: #ccc; font-size: 18px; }
</style>
