<template>
  <div class="agents-studio-page">
    <div class="agents-studio-body">
      <aside class="folder-aside">
        <div class="folder-list">
          <div
            v-for="(f, folderIndex) in folders"
            :key="f.id"
            class="folder-row"
            :class="{ 'is-active': f.id === selectedFolderId }"
            @click="onSelectFolder(f.id)"
          >
            <div class="folder-row-main">
              <el-icon class="folder-item-icon"><Folder /></el-icon>
              <span class="folder-item-text">{{ f.name }}</span>
            </div>
            <el-dropdown trigger="click" @click.stop>
              <button type="button" class="folder-more-btn" aria-label="文件夹操作" @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="openRenameFolderDialog(f)">修改名称</el-dropdown-item>
                  <el-dropdown-item :disabled="folderIndex === 0" @click="handleFolderMove(f, 'up')">
                    上移
                  </el-dropdown-item>
                  <el-dropdown-item
                    :disabled="folderIndex === folders.length - 1"
                    @click="handleFolderMove(f, 'down')"
                  >
                    下移
                  </el-dropdown-item>
                  <el-dropdown-item divided :disabled="f.is_system" @click="handleFolderDelete(f)">
                    删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
        <div class="folder-footer">
          <el-button class="folder-create-btn" plain @click="openCreateFolderDialog">创建文件夹</el-button>
        </div>
      </aside>

      <div class="agents-studio-main">
        <div class="agents-toolbar">
          <span class="agents-toolbar-title">工作流应用</span>
          <div class="toolbar-spacer" />
          <el-input
            v-model="keyword"
            class="agents-search"
            placeholder="搜索应用…"
            clearable
            @clear="loadApps"
            @keyup.enter="loadApps"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>

        <div class="agents-quick-actions">
          <el-button type="primary" :icon="Plus" @click="openCreate">空白创建</el-button>
          <el-button plain :icon="Upload" :disabled="importing" @click="triggerImport">导入</el-button>
          <!-- <el-button type="primary" plain :icon="MagicStick" class="btn-ai-inline" @click="goAiCreate">
            AI 生成
          </el-button> -->
          <input
            ref="importInputRef"
            type="file"
            class="agents-import-input"
            accept="application/json,.json"
            @change="onImportFile"
          />
        </div>

        <div
          ref="cardScrollRef"
          v-loading="loading || importing"
          class="agents-card-scroll"
          @scroll.passive="handleCardScroll"
        >
          <div class="agents-card-grid">
            <article
              v-for="(app, index) in apps"
              :key="app.id"
              class="agents-card"
              :style="{ animationDelay: `${Math.min(index, 12) * 40}ms` }"
            >
              <div
                class="card-top"
                role="link"
                tabindex="0"
                @click="goDetail(app.id)"
                @keydown.enter.prevent="goDetail(app.id)"
              >
                <div class="card-text">
                  <h3 class="card-title">{{ app.name }}</h3>
                  <p class="card-desc">
                    {{ app.description?.trim() ? app.description : '暂无描述' }}
                  </p>
                  <p class="card-time">
                    负责人：{{ (app.owner_display_name || '').trim() || '—' }}
                  </p>
                  <p class="card-time">创建时间：{{ formatDate(app.created_at) }}</p>
                </div>
                <div class="card-logo" aria-hidden="true">
                  <span class="logo-shard logo-shard--a" />
                  <span class="logo-shard logo-shard--b" />
                  <span class="logo-shard logo-shard--c" />
                  <span class="card-logo-emoji">{{ app.icon || '*' }}</span>
                </div>
              </div>
              <div class="card-actions" @click.stop>
                <button type="button" class="action-link" @click="goDetail(app.id)">开发</button>
                <span class="action-divider" />
                <button type="button" class="action-link" @click="openEdit(app)">编辑</button>
                <span class="action-divider" />
                <button type="button" class="action-link" @click="openExport(app)">导出</button>
                <span class="action-divider" />
                <button type="button" class="action-link" @click="goApiDebug(app)">API调试</button>
                <span class="action-divider" />
                <button type="button" class="action-link danger" @click="confirmDelete(app)">删除</button>
              </div>
            </article>
          </div>
          <div v-if="selectedFolderId != null" class="agents-load-state">
            <span v-if="loadingMore">正在加载更多工作流…</span>
            <span v-else-if="apps.length && !hasMoreApps">已显示全部工作流</span>
            <span v-else-if="!apps.length && !loading">暂无工作流应用</span>
          </div>
        </div>
      </div>
    </div>

    <AgentAppCreateDialog
      v-model="createVisible"
      :folder-id="createDialogFolderId"
      :import-payload="pendingImportPayload"
      @created="onCreated"
      @closed="onCreateDialogClosed"
    />
    <AgentAppEditDialog v-model="editVisible" :app="editingApp" :folders="folders" @updated="onEdited" />

    <el-dialog
      v-model="renameFolderVisible"
      title="修改文件夹名称"
      width="400px"
      append-to-body
      @close="renameFolderId = null; renameFolderName = ''"
    >
      <el-form label-position="top">
        <el-form-item label="文件夹名称" required>
          <el-input
            v-model="renameFolderName"
            placeholder="请输入文件夹名称"
            maxlength="128"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameFolderVisible = false">取消</el-button>
        <el-button type="primary" :loading="renameFolderLoading" @click="submitRenameFolder">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="createFolderVisible"
      title="创建文件夹"
      width="400px"
      append-to-body
      @close="newFolderName = ''"
    >
      <el-form label-position="top">
        <el-form-item label="文件夹名称" required>
          <el-input v-model="newFolderName" placeholder="请输入文件夹名称" maxlength="128" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createFolderVisible = false">取消</el-button>
        <el-button type="primary" :loading="createFolderLoading" @click="submitCreateFolder">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="exportVisible"
      class="agent-studio-dialog"
      title="导出配置"
      width="440px"
      align-center
      append-to-body
      destroy-on-close
      @closed="onExportClosed"
    >
      <p v-if="exportApp" class="agents-export-hint">
        应用「{{ exportApp.name }}」：选择要导出的版本，将下载 JSON 文件（含应用信息与画布）。
      </p>
      <el-select
        v-model="exportVersionId"
        class="agents-export-select"
        placeholder="选择版本"
        filterable
        style="width: 100%"
      >
        <el-option
          v-for="v in exportVersions"
          :key="v.id"
          :label="`${v.name}（${versionStatusLabel(v.status)}）`"
          :value="v.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="exportVisible = false">取消</el-button>
        <el-button type="primary" :loading="exportLoading" @click="confirmExport">下载 JSON</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder, MagicStick, MoreFilled, Plus, Search, Upload } from '@element-plus/icons-vue'
import agentAppApi from '@/api/agentApp'
import {
  buildExportPayload,
  downloadJson,
  parseImportPayload,
  safeFilenamePart
} from '@/utils/agentAppExport'
import AgentAppCreateDialog from './AgentAppCreateDialog.vue'
import AgentAppEditDialog from './AgentAppEditDialog.vue'

const router = useRouter()
const APP_PAGE_SIZE = 12
const keyword = ref('')
const apps = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const hasMoreApps = ref(true)
const appSkip = ref(0)
const cardScrollRef = ref(null)
const folders = ref([])
const selectedFolderId = ref(null)
const createFolderVisible = ref(false)
const newFolderName = ref('')
const createFolderLoading = ref(false)
const renameFolderVisible = ref(false)
const renameFolderId = ref(null)
const renameFolderName = ref('')
const renameFolderLoading = ref(false)

const createVisible = ref(false)
const editVisible = ref(false)
const editingApp = ref(null)
const importInputRef = ref(null)
const importing = ref(false)
const pendingImportPayload = ref(null)

const exportVisible = ref(false)
const exportLoading = ref(false)
const exportApp = ref(null)
const exportVersions = ref([])
const exportVersionId = ref(null)

const createDialogFolderId = computed(() =>
  selectedFolderId.value != null ? Number(selectedFolderId.value) : undefined
)

function formatDate(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${d} ${h}:${min}`
}

async function loadFolders() {
  try {
    const data = await agentAppApi.listAgentFolders()
    folders.value = Array.isArray(data) ? data : []
    if (folders.value.length === 0) {
      selectedFolderId.value = null
      return
    }
    const exists =
      selectedFolderId.value != null &&
      folders.value.some((f) => Number(f.id) === Number(selectedFolderId.value))
    if (!exists) {
      selectedFolderId.value = folders.value[0].id
    }
  } catch (e) {
    folders.value = []
    selectedFolderId.value = null
    ElMessage.error('加载文件夹失败：' + (e.response?.data?.detail || e.message))
  }
}

function onSelectFolder(id) {
  selectedFolderId.value = id
  loadApps({ reset: true })
}

function openCreateFolderDialog() {
  newFolderName.value = ''
  createFolderVisible.value = true
}

async function submitCreateFolder() {
  const name = newFolderName.value.trim()
  if (!name) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  createFolderLoading.value = true
  try {
    const row = await agentAppApi.createAgentFolder({ name })
    ElMessage.success('文件夹已创建')
    createFolderVisible.value = false
    await loadFolders()
    if (row && row.id != null) {
      selectedFolderId.value = row.id
      await loadApps()
    }
  } catch (e) {
    ElMessage.error('创建失败：' + (e.response?.data?.detail || e.message))
  } finally {
    createFolderLoading.value = false
  }
}

function openRenameFolderDialog(f) {
  renameFolderId.value = f.id
  renameFolderName.value = f.name || ''
  renameFolderVisible.value = true
}

async function submitRenameFolder() {
  const name = renameFolderName.value.trim()
  if (!name) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  const fid = renameFolderId.value
  if (fid == null) return
  renameFolderLoading.value = true
  try {
    await agentAppApi.updateAgentFolder(fid, { name })
    ElMessage.success('已更新')
    renameFolderVisible.value = false
    await loadFolders()
  } catch (e) {
    ElMessage.error('更新失败：' + (e.response?.data?.detail || e.message))
  } finally {
    renameFolderLoading.value = false
  }
}

async function handleFolderDelete(f) {
  if (!f?.id || f.is_system) return
  try {
    await ElMessageBox.confirm(`确定删除文件夹「${f.name}」？其中工作流将移至默认文件夹。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await agentAppApi.deleteAgentFolder(f.id)
    ElMessage.success('已删除')
    await loadFolders()
    await loadApps()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

async function handleFolderMove(f, direction) {
  try {
    await agentAppApi.moveAgentFolder(f.id, { direction })
    await loadFolders()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message || '移动失败')
  }
}

async function loadApps(options = {}) {
  const reset = options.reset !== false
  if (selectedFolderId.value == null) {
    apps.value = []
    appSkip.value = 0
    hasMoreApps.value = false
    return
  }
  if (reset) {
    loading.value = true
    appSkip.value = 0
    hasMoreApps.value = true
  } else {
    if (loading.value || loadingMore.value || !hasMoreApps.value) return
    loadingMore.value = true
  }
  try {
    const kw = keyword.value.trim()
    const rows = await agentAppApi.listAgentApps({
      skip: reset ? 0 : appSkip.value,
      limit: APP_PAGE_SIZE,
      folder_id: selectedFolderId.value,
      ...(kw ? { keyword: kw } : {})
    })
    const list = Array.isArray(rows) ? rows : []
    apps.value = reset ? list : [...apps.value, ...list]
    appSkip.value = apps.value.length
    hasMoreApps.value = list.length === APP_PAGE_SIZE
    if (reset) {
      await nextTick()
      if (cardScrollRef.value) cardScrollRef.value.scrollTop = 0
    }
  } catch (e) {
    ElMessage.error(e.message || '加载应用列表失败')
    if (reset) apps.value = []
  } finally {
    loading.value = false
    loadingMore.value = false
    scheduleFillVisibleCards()
  }
}

function handleCardScroll(ev) {
  const el = ev?.target
  if (!el || loading.value || loadingMore.value || !hasMoreApps.value) return
  const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  if (distanceToBottom < 220) {
    loadApps({ reset: false })
  }
}

function scheduleFillVisibleCards() {
  window.setTimeout(() => {
    const el = cardScrollRef.value
    if (!el || loading.value || loadingMore.value || !hasMoreApps.value) return
    if (el.scrollHeight <= el.clientHeight + 24) {
      loadApps({ reset: false })
    }
  }, 0)
}

function goAiCreate() {
  router.push({ name: 'AgentAICreatorChat' })
}

function openCreate() {
  pendingImportPayload.value = null
  createVisible.value = true
}

function onCreateDialogClosed() {
  pendingImportPayload.value = null
}

function triggerImport() {
  if (importing.value) return
  importInputRef.value?.click?.()
}

function versionStatusLabel(status) {
  if (status === 'designing') return '设计中'
  if (status === 'published') return '已发布'
  if (status === 'online') return '已上线'
  return status || '—'
}

async function openExport(app) {
  if (!app?.id) return
  exportApp.value = app
  try {
    const detail = await agentAppApi.getAgentApp(app.id)
    exportVersions.value = detail.versions || []
    exportVersionId.value = exportVersions.value[0]?.id ?? null
    if (!exportVersions.value.length) {
      ElMessage.warning('该应用暂无版本可导出')
      return
    }
    exportVisible.value = true
  } catch (e) {
    ElMessage.error(e.message || '加载版本失败')
  }
}

function onExportClosed() {
  exportApp.value = null
  exportVersions.value = []
  exportVersionId.value = null
}

async function confirmExport() {
  const app = exportApp.value
  const vid = exportVersionId.value
  if (!app?.id || vid == null) return
  const vmeta = exportVersions.value.find((x) => x.id === vid)
  if (!vmeta) {
    ElMessage.error('请选择有效版本')
    return
  }
  exportLoading.value = true
  try {
    const wf = await agentAppApi.getWorkflow(app.id, vid)
    const payload = buildExportPayload({
      app,
      versionMeta: vmeta,
      workflowGetOut: wf
    })
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    const fn = `${safeFilenamePart(app.name)}-${safeFilenamePart(vmeta.name)}-${stamp}.json`
    downloadJson(fn, payload)
    ElMessage.success('已开始下载')
    exportVisible.value = false
  } catch (e) {
    ElMessage.error(e.message || '导出失败')
  } finally {
    exportLoading.value = false
  }
}

async function onImportFile(ev) {
  const input = ev.target
  const file = input?.files?.[0]
  if (input) input.value = ''
  if (!file) return
  if (importing.value) return
  importing.value = true
  try {
    const text = await file.text()
    let payload
    try {
      payload = parseImportPayload(text)
    } catch (parseErr) {
      if (parseErr instanceof SyntaxError) {
        throw new Error('文件不是合法的 JSON，请检查格式')
      }
      throw parseErr
    }
    pendingImportPayload.value = payload
    createVisible.value = true
  } catch (e) {
    ElMessage.error(e?.message || '文件校验失败')
  } finally {
    importing.value = false
  }
}

function goDetail(id) {
  router.push(`/agent-platform/agents/${id}`)
}

function openEdit(app) {
  editingApp.value = app
  editVisible.value = true
}

function onEdited() {
  loadApps({ reset: true })
}

function goApiDebug(app) {
  if (!app?.id) return
  router.push(`/agent-platform/agents/${app.id}`)
}

async function confirmDelete(app) {
  if (!app?.id) return
  try {
    await ElMessageBox.confirm(`确定删除工作流「${app.name}」？删除后不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await agentAppApi.deleteAgentApp(app.id)
    ElMessage.success('已删除')
    if (editingApp.value?.id === app.id) {
      editVisible.value = false
      editingApp.value = null
    }
    loadApps({ reset: true })
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

function onCreated(app) {
  loadApps({ reset: true })
  if (app?.id != null) {
    router.push(`/agent-platform/agents/${app.id}`)
  }
}

let debounceTimer
watch(keyword, () => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => loadApps({ reset: true }), 320)
})

watch(editVisible, (v) => {
  if (!v) editingApp.value = null
})

onMounted(async () => {
  await loadFolders()
  await loadApps({ reset: true })
})
</script>

<style scoped>
.agents-studio-page {
  --agent-brand: #3d8d82;
  --agent-brand-hover: #326f66;
  --agent-brand-soft: #e8f4f1;
  --agent-card-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
  --agent-card-border: #e5ebe9;

  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
  overflow: hidden;
}

.agents-studio-body {
  display: flex;
  align-items: stretch;
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.folder-aside {
  width: 168px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-self: stretch;
  min-height: 0;
  height: 100%;
  max-height: 100%;
  overflow: hidden;
  border-right: 1px solid #e4e7ed;
  background: #f7f8fa;
}

.folder-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  padding: 8px 0 12px;
}

.folder-row {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 6px 6px 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #303133;
  transition: background 0.15s;
}

.folder-row:hover {
  background: rgba(61, 141, 130, 0.1);
}

.folder-row.is-active {
  background: #e8f4f1;
  color: #3d8d82;
  font-weight: 500;
}

.folder-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.folder-more-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #909399;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s;
}

.folder-more-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #606266;
}

.folder-row.is-active .folder-more-btn {
  color: #3d8d82;
}

.folder-item-icon {
  flex-shrink: 0;
}

.folder-item-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-footer {
  flex-shrink: 0;
  position: sticky;
  bottom: 0;
  z-index: 2;
  padding: 10px 12px 12px;
  border-top: 1px solid #e4e7ed;
  background:
    linear-gradient(180deg, rgba(247, 248, 250, 0.82), #f7f8fa 34%),
    #f7f8fa;
  box-shadow: 0 -10px 18px rgba(15, 23, 42, 0.04);
}

.folder-create-btn {
  width: 100%;
  margin: 0;
  border-radius: 8px;
  background: #fff;
  border-color: #d7e2df;
  color: #3d524d;
  font-weight: 600;
}

.agents-studio-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: 100%;
  max-height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.agents-quick-actions {
  flex-shrink: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 10px 20px 12px;
  border-bottom: 1px solid #eef2f0;
  background: #fafcfb;
}

.agents-quick-actions :deep(.el-button) {
  margin: 0;
}

.btn-ai-inline {
  border-color: rgba(61, 141, 130, 0.45) !important;
  color: #3d8d82 !important;
}

.btn-ai-inline:hover {
  background: rgba(61, 141, 130, 0.08) !important;
}

.agents-toolbar {
  display: flex;
  align-items: center;
  padding: 16px 20px 12px;
  gap: 16px;
  flex-shrink: 0;
  border-bottom: 1px solid #eef2f0;
}

.agents-toolbar-title {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.toolbar-spacer {
  flex: 1;
}

.agents-search {
  width: min(320px, 100%);
}

.agents-search :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px #e0ebe8 inset;
  background: #fff;
}

.agents-card-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
}

.agents-card-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-auto-rows: min-content;
  align-content: start;
  gap: 20px;
  padding: 16px 20px 10px;
}

.agents-load-state {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px 20px 22px;
  font-size: 12px;
  color: #94a3b8;
}

@media (max-width: 1200px) {
  .agents-card-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .agents-card-grid {
    grid-template-columns: 1fr;
  }
}

@keyframes agents-card-rise {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.agents-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: var(--agent-card-shadow);
  border: 1px solid var(--agent-card-border);
  padding: 20px 20px 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  animation: agents-card-rise 0.42s ease backwards;
}

.card-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex: 1;
  padding-bottom: 16px;
  cursor: pointer;
}

.card-top:hover .card-title {
  color: var(--agent-brand);
}

.card-top:focus-visible {
  outline: 2px solid var(--agent-brand);
  outline-offset: 4px;
  border-radius: 4px;
}

.card-text {
  min-width: 0;
  flex: 1;
}

.card-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.4;
  transition: color 0.2s ease;
}

.card-desc {
  margin: 0 0 10px;
  font-size: 13px;
  color: #475569;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-time {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
}

.card-time + .card-time {
  margin-top: 4px;
}

.card-logo {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  position: relative;
  border-radius: 9px;
  background:
    radial-gradient(circle at 75% 25%, rgba(61, 141, 130, 0.18), transparent 48%),
    radial-gradient(circle at 20% 85%, rgba(15, 118, 110, 0.14), transparent 56%),
    linear-gradient(145deg, #f7fbfa 0%, #edf4f2 100%);
  overflow: hidden;
  border: 1px solid #dfe9e6;
  display: grid;
  place-items: center;
}

.logo-shard {
  display: none;
}

.card-logo::before {
  content: '';
  position: absolute;
  inset: 1px;
  border-radius: 8px;
  background:
    repeating-linear-gradient(
      -45deg,
      rgba(255, 255, 255, 0.32) 0 3px,
      rgba(255, 255, 255, 0.06) 3px 8px
    );
  pointer-events: none;
}

.card-logo-emoji {
  position: relative;
  z-index: 1;
  display: block;
  font-size: 22px;
  line-height: 1;
  text-shadow: none;
  pointer-events: none;
}

.card-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px 4px;
  margin: 0 -20px;
  padding: 10px 12px 12px;
  border-top: 1px solid #eef2f0;
  background: linear-gradient(180deg, #fbfcfc 0%, #f4f8f6 100%);
}

.agents-import-input {
  display: none;
}

.agents-export-hint {
  margin: 0 0 14px;
  font-size: 13px;
  line-height: 1.55;
  color: #475569;
}

.agents-export-select {
  width: 100%;
}

.action-link {
  flex: 1 1 auto;
  min-width: 0;
  text-align: center;
  border: 1px solid transparent;
  border-radius: 8px;
  background: #fff;
  padding: 7px 6px;
  font-size: 12px;
  color: var(--agent-brand);
  cursor: pointer;
  font-weight: 600;
  box-shadow: 0 0 0 1px #e2ebe8 inset;
  transition:
    color 0.15s ease,
    background 0.15s ease,
    box-shadow 0.15s ease;
}

.action-link:hover:not(:disabled) {
  color: var(--agent-brand-hover);
  background: #f0faf7;
  box-shadow: 0 0 0 1px rgba(61, 141, 130, 0.25) inset;
}

.action-link.danger {
  color: #c2415c;
  box-shadow: 0 0 0 1px #fce8ec inset;
}

.action-link.danger:hover:not(:disabled) {
  color: #9f2f46;
  background: #fff5f5;
  box-shadow: 0 0 0 1px rgba(194, 65, 92, 0.28) inset;
}

.action-divider {
  width: 1px;
  height: 14px;
  background: #e2e8f0;
  flex-shrink: 0;
}
</style>
