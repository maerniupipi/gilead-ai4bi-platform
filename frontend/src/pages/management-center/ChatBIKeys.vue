<template>
  <div class="keys-page" v-loading="loading">
    <div class="keys-header">
      <div>
        <h1>服务 Key 与工作流</h1>
        <p>每次 API 调用携带服务 Key，平台按绑定的工作流和固定版本执行。</p>
      </div>
      <div>
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">创建 / 导入 Key</el-button>
      </div>
    </div>

    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon class="keys-note" />
    <el-alert class="keys-note" type="info" :closable="false" show-icon
      title="问答、PPT、XLSX、任务查询和获取下载链接统一使用 Authorization: Bearer <Key>。调整绑定后，新会话使用新版本；不同 Key 的数据分别保存。" />

    <el-table :data="keys" border empty-text="暂无服务 Key，可创建新 Key 或导入已有 Key">
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column label="环境" width="90">
        <template #default="{ row }"><el-tag :type="row.environment === 'prod' ? 'warning' : 'info'">{{ row.environment.toUpperCase() }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="key_hint" label="Key 掩码" min-width="185" />
      <el-table-column label="工作流" min-width="200">
        <template #default="{ row }">
          <span v-if="row.workflow_id">{{ row.workflow_name }} <small>#{{ row.workflow_id }}</small></span>
          <span v-else-if="row.legacy_config">{{ legacyLabel(row.legacy_config) }}</span>
          <span v-else>待绑定</span>
        </template>
      </el-table-column>
      <el-table-column label="固定版本" min-width="170">
        <template #default="{ row }">
          <span v-if="row.version_id">{{ row.version_name }} <small>#{{ row.version_id }} · rev {{ row.workflow_rev }}</small></span>
          <el-tag v-else type="warning" size="small">保留原配置，待选版本</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="85">
        <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '已启用' : '已停用' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑绑定</el-button>
          <el-button link :type="row.enabled ? 'danger' : 'primary'" :loading="changing === row.id" @click="toggle(row)">{{ row.enabled ? '停用' : '启用' }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <p class="keys-footer">UAT 与 Prod 各自使用本环境的 Key。已有 Key 可以直接导入；原有 Key 的编辑不会改变凭证值。</p>

    <el-dialog v-model="visible" :title="editing ? '编辑 Key 绑定' : '创建 / 导入服务 Key'" width="560px" @closed="clearImport">
      <el-alert v-if="legacyConfig" type="warning" :closable="false" class="keys-note"
        :title="`目前保留 ${legacyLabel(legacyConfig)}。选择工作流和已发布版本后保存，会切换后续新会话的执行配置。`" />
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="名称" prop="name"><el-input v-model="form.name" maxlength="100" placeholder="例如 数据问答服务 UAT" /></el-form-item>
        <el-form-item label="环境">
          <el-select v-model="form.environment" :disabled="Boolean(editing)" style="width: 100%">
            <el-option label="UAT" value="uat" /><el-option label="Prod" value="prod" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="!editing" label="Key 来源">
          <el-radio-group v-model="source"><el-radio value="generate">生成新 Key</el-radio><el-radio value="import">导入已有 Key</el-radio></el-radio-group>
        </el-form-item>
        <el-form-item v-if="!editing && source === 'import'" label="已有 Key">
          <el-input v-model="form.api_key" type="password" show-password autocomplete="off" :placeholder="`app-${form.environment}-…`" />
        </el-form-item>
        <el-form-item label="工作流" prop="workflow_id">
          <el-select v-model="form.workflow_id" filterable placeholder="选择工作流" style="width: 100%" @change="form.version_id = null">
            <el-option v-for="app in workflows" :key="app.id" :value="app.id" :label="`${app.name} (#${app.id})`" />
          </el-select>
        </el-form-item>
        <el-form-item label="固定版本" prop="version_id">
          <el-select v-model="form.version_id" :disabled="!form.workflow_id" placeholder="选择已发布 / 已上线版本" style="width: 100%">
            <el-option v-for="version in versions" :key="version.id" :value="version.id" :label="`${version.name} (#${version.id} · rev ${version.workflow_rev})`" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
      <p v-if="!workflows.length" class="keys-footer">暂无可选版本，请先在智能体平台发布需要的工作流版本，然后刷新此页。</p>
      <template #footer><el-button @click="visible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="secretVisible" title="服务 Key 已创建" width="590px" :close-on-click-modal="false" @closed="newSecret = ''">
      <p>请保存以下 Key，关闭后平台仅显示掩码。每次调用时填入 Authorization 请求头。</p>
      <el-input :model-value="newSecret" readonly type="textarea" :rows="3" />
      <template #footer><el-button @click="copySecret">复制 Key</el-button><el-button type="primary" @click="secretVisible = false">已保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listChatBIKeys, chatBIWorkflowOptions, createChatBIKey, updateChatBIKey, setChatBIKeyEnabled } from '@/api/chatbiKeys'

const keys = ref([]), workflows = ref([]), loading = ref(false), loadError = ref('')
const visible = ref(false), editing = ref(null), legacyConfig = ref(''), source = ref('generate')
const saving = ref(false), changing = ref(null), formRef = ref(null)
const secretVisible = ref(false), newSecret = ref('')
const form = reactive({ name: '', environment: 'uat', api_key: '', workflow_id: null, version_id: null, enabled: true })
const versions = computed(() => workflows.value.find(app => app.id === form.workflow_id)?.versions || [])
const rules = {
  name: [{ required: true, whitespace: true, message: '请输入名称', trigger: 'blur' }],
  workflow_id: [{ required: true, message: '请选择工作流', trigger: 'change' }],
  version_id: [{ required: true, message: '请选择固定版本', trigger: 'change' }],
}
const legacyLabel = value => value.startsWith('autobi:') ? `AutoBI 项目 ${value.split(':')[1]}` : value

async function load() {
  loading.value = true; loadError.value = ''
  try { [keys.value, workflows.value] = await Promise.all([listChatBIKeys(), chatBIWorkflowOptions()]) }
  catch (error) { loadError.value = error.message || '加载 Key 配置失败' }
  finally { loading.value = false }
}
function openCreate() {
  editing.value = null; legacyConfig.value = ''; source.value = 'generate'
  Object.assign(form, { name: '', environment: 'uat', api_key: '', workflow_id: null, version_id: null, enabled: true })
  formRef.value?.clearValidate(); visible.value = true
}
function openEdit(row) {
  editing.value = row.id; legacyConfig.value = row.legacy_config || ''
  Object.assign(form, { name: row.name, environment: row.environment, api_key: '', workflow_id: row.workflow_id, version_id: row.version_id, enabled: row.enabled })
  formRef.value?.clearValidate(); visible.value = true
}
const clearImport = () => { form.api_key = '' }
async function save() {
  if (!(await formRef.value.validate().catch(() => false))) return
  if (!editing.value && source.value === 'import' && !form.api_key.trim()) { ElMessage.warning('请输入已有 Key'); return }
  saving.value = true
  try {
    const data = { name: form.name.trim(), workflow_id: form.workflow_id, version_id: form.version_id, enabled: form.enabled }
    if (editing.value) await updateChatBIKey(editing.value, data)
    else {
      const result = await createChatBIKey({ ...data, environment: form.environment, ...(source.value === 'import' ? { api_key: form.api_key.trim() } : {}) })
      if (result.api_key) { newSecret.value = result.api_key; secretVisible.value = true }
    }
    visible.value = false; clearImport(); ElMessage.success('已保存 Key 绑定'); await load()
  } catch { /* The shared request client displays the server error. */ }
  finally { saving.value = false }
}
async function toggle(row) {
  changing.value = row.id
  try { const updated = await setChatBIKeyEnabled(row.id, !row.enabled); Object.assign(row, updated) }
  catch { /* Shared request error handling. */ }
  finally { changing.value = null }
}
async function copySecret() {
  try { await navigator.clipboard.writeText(newSecret.value); ElMessage.success('已复制') }
  catch { ElMessage.warning('复制失败，请手动选择并保存 Key') }
}
onMounted(load)
</script>

<style scoped>
.keys-page { padding: 28px; }
.keys-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
.keys-header h1 { margin: 0 0 10px; font-size: 22px; font-weight: 600; color: #1f2937; }
.keys-header p, .keys-footer { color: #64748b; font-size: 13px; line-height: 1.7; }
.keys-header p { margin: 0; }
.keys-note { margin-bottom: 20px; }
small { color: #64748b; margin-left: 5px; }
.keys-footer { margin-top: 18px; }
@media (max-width: 800px) { .keys-page { padding: 16px; } .keys-header { align-items: flex-start; flex-direction: column; } }
</style>
