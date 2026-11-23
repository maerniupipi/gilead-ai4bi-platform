<template>
  <div v-if="app" v-loading="loading" class="agent-platform-page agent-version-page u-animate-in">
    <PageHeader :breadcrumbs="breadcrumbs" />

    <div class="agent-version-surface">
    <div class="agent-version-filters">
      <el-input
        v-model="filterName"
        clearable
        placeholder="版本名称"
        class="agent-version-filters__field"
      />
      <el-select
        v-model="filterStatus"
        clearable
        placeholder="版本状态"
        class="agent-version-filters__field"
        style="width: 160px"
      >
        <el-option label="设计中" value="designing" />
        <el-option label="已发布" value="published" />
        <el-option label="已上线" value="online" />
      </el-select>
      <div class="agent-version-filters__actions">
        <el-button type="primary" @click="noopSearch">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>
    </div>

    <div class="agent-version-actions">
      <el-button type="primary" @click="openNewVersionDialog">+ 新建</el-button>
      <el-button :icon="Upload" :loading="importReading" :disabled="importSubmitting" @click="triggerVersionImport">导入版本</el-button>
      <input ref="importInputRef" type="file" accept=".json,application/json" class="agent-version-import-input" aria-label="选择工作流 JSON" @change="onImportFile" />
      <el-button @click="openOutputDialog">当前版本配置</el-button>
      <el-button @click="openApiDebug()">API 调用</el-button>
    </div>

    <el-table
      :data="pagedVersions"
      border
      stripe
      class="agent-version-table"
      style="width: 100%"
      empty-text="暂无版本"
    >
      <el-table-column prop="name" label="版本名称" min-width="200">
        <template #default="{ row }">
          <span>{{ row.name }}</span>
          <el-tag v-if="row.is_output" type="warning" size="small" class="agent-version-output-tag">
            当前版本
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="版本状态" width="140">
        <template #default="{ row }">
          <span
            v-if="row.status === 'designing'"
            class="agent-version-status"
            :class="statusClass(row.status)"
          >
            <span class="agent-version-status__dot" aria-hidden="true" />
            编排中
          </span>
          <span
            v-else-if="row.status === 'published'"
            class="agent-version-status"
            :class="statusClass(row.status)"
          >
            <el-icon class="agent-version-status__icon"><Promotion /></el-icon>
            已发布
          </span>
          <span
            v-else-if="row.status === 'online'"
            class="agent-version-status"
            :class="statusClass(row.status)"
          >
            <el-icon class="agent-version-status__icon"><CircleCheck /></el-icon>
            已上线
          </span>
          <span v-else>{{ row.status }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="版本创建时间" min-width="180">
        <template #default="{ row }">
          {{ formatDt(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="创建方式" min-width="180">
        <template #default="{ row }">
          <span class="agent-version-mode">
            {{ formatVersionMode(row) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="400" fixed="right">
        <template #default="{ row }">
          <div class="agent-version-ops">
            <template v-if="row.status === 'designing'">
              <el-button link type="primary" @click="goWorkflowCanvas(row)">编排</el-button>
              <el-button link type="primary" @click="openClone(row)">克隆</el-button>
            </template>
            <template v-else-if="row.status === 'published'">
              <el-button link type="primary" @click="goWorkflowCanvas(row)">详情</el-button>
              <el-button link type="primary" @click="openClone(row)">克隆</el-button>
            </template>
            <template v-else-if="row.status === 'online'">
              <el-button link type="primary" @click="goWorkflowCanvas(row)">详情</el-button>
              <el-button link type="primary" @click="openClone(row)">克隆</el-button>
            </template>
            <el-button link type="primary" @click="openApiDebug(row)">API 调用</el-button>
            <template v-if="row.status === 'designing'">
              <el-button link type="primary" class="agent-version-op" :loading="actionId === row.id" @click="doPublish(row)">
                <el-icon><Promotion /></el-icon>
                发布
              </el-button>
            </template>
            <template v-else-if="row.status === 'published'">
              <el-button link type="primary" class="agent-version-op agent-version-op--online" :loading="actionId === row.id" @click="doOnline(row)">
                <el-icon><Upload /></el-icon>
                上线
              </el-button>
            </template>
            <template v-else-if="row.status === 'online'">
              <el-button link type="primary" class="agent-version-op agent-version-op--offline" :loading="actionId === row.id" @click="doOffline(row)">
                <el-icon><CircleClose /></el-icon>
                下线
              </el-button>
            </template>
            <el-button
              link
              :type="canDeleteVersion(row) ? 'danger' : 'info'"
              class="agent-version-op agent-version-op--delete"
              :disabled="!canDeleteVersion(row)"
              :loading="deleteId === row.id"
              @click="doDelete(row)"
            >
              <el-icon><DeleteFilled /></el-icon>
              删除
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <div class="agent-version-pagination" v-if="filteredTotal > pageSize">
      <span class="agent-version-pagination__info">
        显示 {{ pageStart }}-{{ pageEnd }}，共 {{ filteredTotal }} 条
      </span>
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="filteredTotal"
        layout="prev, pager, next"
      />
    </div>
    </div>

    <el-dialog
      v-model="importVisible"
      title="导入为新版本"
      width="480px"
      align-center
      destroy-on-close
      append-to-body
      class="agent-version-dialog"
      :close-on-click-modal="!importSubmitting && !importReading"
      :close-on-press-escape="!importSubmitting && !importReading"
      :show-close="!importSubmitting && !importReading"
      @closed="onImportClosed"
    >
      <p class="agent-version-import-hint">导入到工作流「{{ app.name }}」，创建可编辑的新版本，保留历史版本和当前版本配置。</p>
      <div class="agent-version-import-file">
        <span>{{ importFileName }}</span>
        <el-button text type="primary" :loading="importReading" :disabled="importSubmitting" @click="triggerVersionImport">更换文件</el-button>
      </div>
      <p v-if="importPayload?.versionMeta?.name" class="agent-version-import-hint">来源版本：{{ importPayload.versionMeta.name }}</p>
      <el-form label-position="top" @submit.prevent="submitImportVersion">
        <el-form-item label="新版本名称" required>
          <el-input v-model="importVersionName" maxlength="64" show-word-limit placeholder="例如 v2.1" :disabled="importSubmitting" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="importSubmitting || importReading" @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importSubmitting" :disabled="importReading || !importPayload || !importVersionName.trim()" @click="submitImportVersion">导入</el-button>
      </template>
    </el-dialog>

    <!-- 新建版本：仅版本名称 -->
    <el-dialog
      v-model="newVersionVisible"
      title="新建"
      width="440px"
      align-center
      destroy-on-close
      append-to-body
      class="agent-version-dialog"
      @closed="newVersionName = ''"
    >
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="版本名称" required>
          <el-input
            v-model="newVersionName"
            maxlength="64"
            show-word-limit
            placeholder="例如 v2.1"
            clearable
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newVersionVisible = false">取消</el-button>
        <el-button type="primary" :loading="newVersionSubmitting" @click="submitNewVersion">确定</el-button>
      </template>
    </el-dialog>

    <!-- 当前版本：下拉仅已发布 + 已上线 -->
    <el-dialog
      v-model="outputVisible"
      title="当前版本配置"
      width="440px"
      align-center
      destroy-on-close
      append-to-body
      class="agent-version-dialog"
    >
      <p class="agent-version-output-hint">
        仅展示「已发布」「已上线」版本。选定后该版本将成为<strong>唯一当前版本</strong>，并<strong>自动变为已上线</strong>；后续若开放「上线版本号」API，未填写时可默认沿用当前版本号。
      </p>
      <el-select
        v-model="outputVersionId"
        placeholder="请选择版本"
        style="width: 100%"
        filterable
      >
        <el-option
          v-for="v in outputCandidates"
          :key="v.id"
          :label="outputOptionLabel(v)"
          :value="v.id"
        />
      </el-select>
      <template #footer>
        <el-button @click="outputVisible = false">取消</el-button>
        <el-button type="primary" :loading="outputSubmitting" @click="submitOutput">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="cloneVisible"
      title="克隆版本"
      width="440px"
      align-center
      destroy-on-close
      append-to-body
      class="agent-version-dialog"
      @closed="cloneSourceRow = null; cloneVersionName = ''"
    >
      <p class="agent-version-clone-hint">
        从「<strong>{{ cloneSourceRow?.name || '—' }}</strong>」复制工作流画布与节点配置；新版本状态为<strong>编排中</strong>，可继续修改与发布。
      </p>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="新版本名称" required>
          <el-input
            v-model="cloneVersionName"
            maxlength="64"
            show-word-limit
            placeholder="例如 v2.1-副本"
            clearable
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cloneVisible = false">取消</el-button>
        <el-button type="primary" :loading="cloneSubmitting" @click="submitClone">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="apiDebugVisible"
      title="API 调试"
      width="820px"
      align-center
      append-to-body
      class="agent-version-dialog agent-version-api-dialog"
      @closed="resetApiDebugResult"
    >
      <div class="agent-api-debug">
        <div class="agent-api-debug__meta">
          <div>
            <span class="agent-api-debug__label">接口</span>
            <code>/api/external/agent-chat/sse</code>
          </div>
          <div>
            <span class="agent-api-debug__label">App ID</span>
            <code>{{ props.appId }}</code>
          </div>
          <div>
            <span class="agent-api-debug__label">版本</span>
            <code>{{ apiDebugVersionLabel }}</code>
          </div>
          <div>
            <span class="agent-api-debug__label">Token</span>
            <el-tag :type="app?.api_token_configured ? 'success' : 'warning'" size="small">
              {{ app?.api_token_configured ? '已配置' : '未配置' }}
            </el-tag>
          </div>
        </div>

        <el-form label-position="top" @submit.prevent>
          <el-form-item label="请求内容" required>
            <el-input
              v-model="apiDebugMessage"
              type="textarea"
              :rows="4"
              maxlength="2000"
              show-word-limit
              placeholder="输入要发送给工作流的问题"
            />
          </el-form-item>
          <el-form-item label="流式输出">
            <el-checkbox v-model="apiDebugStream">
              启用流式输出
            </el-checkbox>
          </el-form-item>
        </el-form>

        <div class="agent-api-debug__request">
          <div class="agent-api-debug__section-title">请求体</div>
          <pre>{{ apiDebugRequestPreview }}</pre>
        </div>

        <div class="agent-api-debug__result">
          <div class="agent-api-debug__panel">
            <div class="agent-api-debug__section-title">流式事件</div>
            <div class="agent-api-debug__events">
              <div v-if="!apiDebugEvents.length" class="agent-api-debug__empty">暂无事件</div>
              <div
                v-for="(event, index) in apiDebugEvents"
                :key="`${event.time}-${index}`"
                class="agent-api-debug__event"
                :class="`is-${event.kind}`"
              >
                <span class="agent-api-debug__event-time">{{ event.time }}</span>
                <span class="agent-api-debug__event-text">{{ event.text }}</span>
              </div>
            </div>
          </div>
          <div class="agent-api-debug__panel">
            <div class="agent-api-debug__section-title">工作流回复</div>
            <div class="agent-api-debug__answer">
              {{ apiDebugAnswer || '暂无回复' }}
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button :disabled="!apiDebugRunning" @click="abortApiDebug">停止</el-button>
        <el-button @click="apiDebugVisible = false">关闭</el-button>
        <el-button type="primary" :loading="apiDebugRunning" @click="runApiDebug">发送调试</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, CircleClose, DeleteFilled, Promotion, Upload } from '@element-plus/icons-vue'
import agentAppApi from '@/api/agentApp'
import { parseImportPayload, suggestImportVersionName } from '@/utils/agentAppExport'

const props = defineProps({
  appId: { type: String, required: true }
})

const router = useRouter()

const app = ref(null)

const breadcrumbs = computed(() => [
  { label: '工作流', to: '/agent-platform/agents' },
  { label: app.value ? `${app.value.name} 配置详情` : '加载中...' }
])
const loading = ref(false)
const filterName = ref('')
const filterStatus = ref('')
const actionId = ref(null)
const deleteId = ref(null)
const currentPage = ref(1)
const pageSize = 10

const newVersionVisible = ref(false)
const newVersionName = ref('')
const newVersionSubmitting = ref(false)

const importInputRef = ref(null)
const importVisible = ref(false)
const importReading = ref(false)
const importSubmitting = ref(false)
const importPayload = ref(null)
const importFileName = ref('')
const importVersionName = ref('')

const outputVisible = ref(false)
const outputVersionId = ref(null)
const outputSubmitting = ref(false)

const cloneVisible = ref(false)
const cloneSourceRow = ref(null)
const cloneVersionName = ref('')
const cloneSubmitting = ref(false)

const apiDebugVisible = ref(false)
const apiDebugVersion = ref(null)
const apiDebugMessage = ref('你好，请简单介绍一下你能做什么。')
const apiDebugStream = ref(true)  // 流式输出默认开启
const apiDebugRunning = ref(false)
const apiDebugEvents = ref([])
const apiDebugAnswer = ref('')
let apiDebugController = null

const filteredVersions = computed(() => {
  const a = app.value
  if (!a?.versions?.length) return []
  return a.versions.filter((v) => {
    if (filterName.value && !v.name.includes(filterName.value.trim())) return false
    if (filterStatus.value && v.status !== filterStatus.value) return false
    return true
  })
})

const filteredTotal = computed(() => filteredVersions.value.length)

const pagedVersions = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredVersions.value.slice(start, start + pageSize)
})

const pageStart = computed(() => {
  if (!filteredTotal.value) return 0
  return (currentPage.value - 1) * pageSize + 1
})

const pageEnd = computed(() => {
  if (!filteredTotal.value) return 0
  return Math.min(currentPage.value * pageSize, filteredTotal.value)
})

/** 当前版本下拉：仅已发布、已上线 */
const outputCandidates = computed(() => {
  const a = app.value
  if (!a?.versions?.length) return []
  return a.versions.filter((v) => v.status === 'published' || v.status === 'online')
})

const apiDebugVersionLabel = computed(() => {
  const v = apiDebugVersion.value
  if (!v) return '未选择'
  return `${v.name || v.id} / ${v.id}`
})

const apiDebugRequestBody = computed(() => ({
  app_id: Number(props.appId),
  version_id: apiDebugVersion.value?.id ?? null,
  message: apiDebugMessage.value,
  caller: 'agent-platform-debug',
  stream: apiDebugStream.value,
  inputs: {
    input: apiDebugMessage.value
  }
}))

const apiDebugRequestPreview = computed(() => JSON.stringify(apiDebugRequestBody.value, null, 2))

function statusLabel(s) {
  if (s === 'published') return '已发布'
  if (s === 'online') return '已上线'
  return s
}

function statusClass(status) {
  if (status === 'published') return 'is-published'
  if (status === 'online') return 'is-online'
  return 'is-designing'
}

function formatVersionMode(row) {
  const owner = app.value?.owner_display_name?.trim() || '创建人'
  const modeText = String(row?.mode || '').toLowerCase()
  const isAiMode = modeText.includes('ai') || modeText.includes('生成')
  if (modeText === '导入') return `导入 - ${owner}`
  return isAiMode ? `AI生成 - ${owner}` : owner
}

/** 已上线、当前版本均不可删除 */
function canDeleteVersion(row) {
  return row.status !== 'online' && !row.is_output
}

/** 当前版本下拉展示：名称 + 状态；若已是当前版本则追加备注 */
function outputOptionLabel(v) {
  const base = `${v.name}（${statusLabel(v.status)}）`
  return v.is_output ? `${base}（当前版本）` : base
}

function formatDt(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

async function load() {
  const id = Number(props.appId)
  if (Number.isNaN(id)) {
    ElMessage.warning('无效的应用 ID')
    router.replace('/agent-platform/agents')
    return
  }
  loading.value = true
  try {
    const data = await agentAppApi.getAgentApp(id)
    app.value = data
    document.title = `${data.name} - 配置详情 - AI4BI`
  } catch (e) {
    ElMessage.error(e.message || '加载失败')
    router.replace('/agent-platform/agents')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filterName.value = ''
  filterStatus.value = ''
}

function noopSearch() {}

function triggerVersionImport() {
  if (importReading.value || importSubmitting.value) return
  importInputRef.value?.click?.()
}

async function onImportFile(event) {
  const input = event.target
  const file = input?.files?.[0]
  if (input) input.value = ''
  if (!file || importReading.value || importSubmitting.value) return
  const appId = props.appId
  importReading.value = true
  try {
    const payload = parseImportPayload(await file.text())
    if (props.appId !== appId) return
    importPayload.value = payload
    importFileName.value = file.name
    importVersionName.value = suggestImportVersionName(payload, app.value?.versions || [])
    importVisible.value = true
  } catch (error) {
    ElMessage.error(error instanceof SyntaxError ? '文件不是合法的 JSON，请检查格式' : error.message || '文件校验失败')
  } finally {
    importReading.value = false
  }
}

function onImportClosed() {
  importPayload.value = null
  importFileName.value = ''
  importVersionName.value = ''
}

async function submitImportVersion() {
  if (importReading.value || importSubmitting.value || !importPayload.value) return
  const name = importVersionName.value.trim()
  if (!name) {
    ElMessage.warning('请输入新版本名称')
    return
  }
  if (app.value?.versions?.some(version => version.name === name)) {
    ElMessage.warning('该版本名称已存在，请使用新的版本名称')
    return
  }
  const appId = props.appId
  importSubmitting.value = true
  try {
    const payload = importPayload.value
    const data = await agentAppApi.createVersion(Number(appId), {
      name,
      workflow: payload.workflow,
      ...(payload.undo_stack ? { undo_stack: payload.undo_stack } : {})
    })
    if (props.appId !== appId) return
    app.value = data
    resetFilters()
    currentPage.value = 1
    importVisible.value = false
    ElMessage.success(`已导入为新版本「${name}」`)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || '导入失败')
  } finally {
    importSubmitting.value = false
  }
}

/** 仅「编排中」可改画布；已发布/已上线同「详情」只读 */
function goWorkflowCanvas(row) {
  const readonly = row.status !== 'designing'
  router.push({
    name: 'AgentWorkflowDesign',
    params: { appId: props.appId, versionId: String(row.id) },
    query: readonly ? { readonly: '1' } : {}
  })
}

function openClone(row) {
  cloneSourceRow.value = row
  cloneVersionName.value = row?.name ? `${row.name}-副本` : ''
  cloneVisible.value = true
}

async function submitClone() {
  const name = cloneVersionName.value.trim()
  if (!name) {
    ElMessage.warning('请输入新版本名称')
    return
  }
  const srcId = cloneSourceRow.value?.id
  if (srcId == null) {
    ElMessage.warning('未选择源版本')
    return
  }
  const aid = Number(props.appId)
  cloneSubmitting.value = true
  try {
    const data = await agentAppApi.createVersion(aid, {
      name,
      clone_from_version_id: srcId
    })
    app.value = data
    ElMessage.success('已克隆为新版本')
    cloneVisible.value = false
  } catch (e) {
    ElMessage.error(e.message || '克隆失败')
  } finally {
    cloneSubmitting.value = false
  }
}

function nowText() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function pushApiDebugEvent(kind, text) {
  apiDebugEvents.value.push({ kind, text, time: nowText() })
}

function resetApiDebugResult() {
  if (apiDebugRunning.value) abortApiDebug()
  apiDebugEvents.value = []
  apiDebugAnswer.value = ''
}

function openApiDebug(row) {
  const versions = app.value?.versions || []
  const target = row || versions.find((v) => v.is_output) || versions.find((v) => v.status === 'online') || versions[0]
  if (!target) {
    ElMessage.warning('暂无可调试版本')
    return
  }
  apiDebugVersion.value = target
  apiDebugEvents.value = []
  apiDebugAnswer.value = ''
  apiDebugVisible.value = true
}

function normalizeApiDebugEvent(ev) {
  if (ev?.type === 'parse_error') return { kind: 'error', text: `SSE 解析失败：${ev.raw}` }
  const msg = ev?.message || {}
  if (msg.type === 'progress') {
    const progress = msg.features?.progress || msg.content || '工作流处理中'
    return { kind: 'progress', text: progress }
  }
  if (msg.type === 'text') {
    return { kind: 'text', text: msg.content || '' }
  }
  if (msg.type === 'error' || ev?.status_code === 'FAILED') {
    return { kind: 'error', text: msg.content || ev?.message || '调用失败' }
  }
  if (ev?.finish) {
    return { kind: 'finish', text: '调用完成' }
  }
  return { kind: 'raw', text: JSON.stringify(ev) }
}

async function runApiDebug() {
  if (!apiDebugVersion.value?.id) {
    ElMessage.warning('请选择版本')
    return
  }
  const message = apiDebugMessage.value.trim()
  if (!message) {
    ElMessage.warning('请输入请求内容')
    return
  }

  // 清空两个窗口
  apiDebugEvents.value = []
  apiDebugAnswer.value = ''
  apiDebugRunning.value = true
  apiDebugController = new AbortController()

  try {
    const requestBody = {
      ...apiDebugRequestBody.value,
      message,
      stream: apiDebugStream.value
    }

    if (apiDebugStream.value) {
      // ===== 流式：结果只在"流式事件"窗口 =====
      apiDebugAnswer.value = ''  // 清空工作流回复窗口
      await agentAppApi.streamExternalAgentChat(
        requestBody,
        {
          signal: apiDebugController.signal,
          onEvent(ev) {
            const normalized = normalizeApiDebugEvent(ev)
            pushApiDebugEvent(normalized.kind, normalized.text)
          }
        }
      )
      pushApiDebugEvent('finish', '流读取结束')
    } else {
      // ===== 非流式：结果只在"工作流回复"窗口 =====
      apiDebugEvents.value = []  // 清空流式事件窗口
      const result = await agentAppApi.runExternalAgentChat(requestBody)
      apiDebugAnswer.value = result?.answer || result?.content || JSON.stringify(result)
      // 注意：非流式不调用 pushApiDebugEvent，流式事件窗口保持为空
    }
  } catch (e) {
    if (apiDebugStream.value) {
      // 流式模式：错误显示在流式事件窗口
      if (e?.name === 'AbortError') {
        pushApiDebugEvent('finish', '已停止')
      } else {
        pushApiDebugEvent('error', e?.message || '调用失败')
      }
    } else {
      // 非流式模式：错误显示在工作流回复窗口
      if (e?.name === 'AbortError') {
        apiDebugAnswer.value = '已停止'
      } else {
        apiDebugAnswer.value = `错误: ${e?.message || '调用失败'}`
      }
      // 确保流式事件窗口为空
      apiDebugEvents.value = []
    }
    ElMessage.error(e?.message || '调用失败')
  } finally {
    apiDebugRunning.value = false
    apiDebugController = null
  }
}

function abortApiDebug() {
  apiDebugController?.abort()
}

function openNewVersionDialog() {
  newVersionName.value = ''
  newVersionVisible.value = true
}

async function submitNewVersion() {
  const name = newVersionName.value.trim()
  if (!name) {
    ElMessage.warning('请输入版本名称')
    return
  }
  const aid = Number(props.appId)
  newVersionSubmitting.value = true
  try {
    const data = await agentAppApi.createVersion(aid, { name })
    app.value = data
    ElMessage.success('已创建版本')
    newVersionVisible.value = false
  } catch (e) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    newVersionSubmitting.value = false
  }
}

async function doPublish(row) {
  const aid = Number(props.appId)
  actionId.value = row.id
  try {
    const data = await agentAppApi.publishVersion(aid, row.id)
    app.value = data
    ElMessage.success('已发布')
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    actionId.value = null
  }
}

async function doOnline(row) {
  const aid = Number(props.appId)
  actionId.value = row.id
  try {
    const data = await agentAppApi.onlineVersion(aid, row.id)
    app.value = data
    ElMessage.success('已上线')
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    actionId.value = null
  }
}

async function doDelete(row) {
  if (!canDeleteVersion(row)) return
  try {
    await ElMessageBox.confirm(
      `确定删除版本「${row.name}」吗？删除后不可恢复。`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消'
      }
    )
  } catch {
    return
  }
  const aid = Number(props.appId)
  deleteId.value = row.id
  try {
    const data = await agentAppApi.deleteVersion(aid, row.id)
    app.value = data
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  } finally {
    deleteId.value = null
  }
}

async function doOffline(row) {
  try {
    await ElMessageBox.confirm(
      `确定将版本「${row.name}」下线吗？下线后将变为「已发布」状态。`,
      '下线确认',
      {
        type: 'warning',
        confirmButtonText: '确定下线',
        cancelButtonText: '取消'
      }
    )
  } catch {
    return
  }
  const aid = Number(props.appId)
  actionId.value = row.id
  try {
    const data = await agentAppApi.offlineVersion(aid, row.id)
    app.value = data
    ElMessage.success('已下线')
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    actionId.value = null
  }
}

function openOutputDialog() {
  const cur = outputCandidates.value.find((v) => v.is_output)
  outputVersionId.value = cur ? cur.id : null
  outputVisible.value = true
}

async function submitOutput() {
  if (outputVersionId.value == null) {
    ElMessage.warning('请选择版本')
    return
  }
  const aid = Number(props.appId)
  outputSubmitting.value = true
  try {
    const data = await agentAppApi.setOutputVersion(aid, outputVersionId.value)
    app.value = data
    ElMessage.success('已设为当前版本并已上线')
    outputVisible.value = false
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    outputSubmitting.value = false
  }
}

onMounted(load)
watch(() => props.appId, load)
watch([filterName, filterStatus], () => {
  currentPage.value = 1
})
watch(filteredTotal, (total) => {
  const maxPage = Math.max(1, Math.ceil(total / pageSize))
  if (currentPage.value > maxPage) currentPage.value = maxPage
})
</script>

<style scoped>
.agent-version-page {
  max-width: 1180px;
}

.agent-version-import-input {
  display: none;
}

.agent-version-import-hint {
  margin: 0 0 14px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.agent-version-import-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.agent-version-import-file span {
  overflow-wrap: anywhere;
}

.agent-version-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #e4eeeb;
  border-radius: 12px;
  background: linear-gradient(180deg, #fcfefd 0%, #f8fcfa 100%);
}

.agent-version-filters__field {
  width: 220px;
  max-width: 100%;
}

.agent-version-filters__actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.agent-version-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.agent-version-table {
  border-radius: 8px;
  overflow: hidden;
}

.agent-version-surface :deep(.el-table tr:hover > td.el-table__cell) {
  background: #f8fbfa;
}

.agent-version-surface :deep(.el-input__wrapper),
.agent-version-surface :deep(.el-select__wrapper) {
  border-radius: 10px;
  box-shadow:
    0 0 0 1px #d8e7e2 inset,
    0 1px 2px rgba(15, 23, 42, 0.03);
  background: #fbfefd;
  transition: box-shadow 0.2s ease, background 0.2s ease;
}

.agent-version-surface :deep(.el-input__wrapper:hover),
.agent-version-surface :deep(.el-select__wrapper:hover) {
  box-shadow:
    0 0 0 1px #bdd6ce inset,
    0 2px 8px rgba(61, 141, 130, 0.08);
}

.agent-version-surface :deep(.el-input__wrapper.is-focus),
.agent-version-surface :deep(.el-select__wrapper.is-focused) {
  box-shadow:
    0 0 0 1px rgba(61, 141, 130, 0.5) inset,
    0 0 0 3px rgba(61, 141, 130, 0.12);
  background: #fff;
}

.agent-version-surface :deep(.el-button) {
  border-radius: 8px;
  font-weight: 600;
}

.agent-version-actions :deep(.el-button--primary),
.agent-version-filters__actions :deep(.el-button--primary) {
  border: none;
  background: #2f8f82;
  box-shadow: 0 3px 10px rgba(47, 143, 130, 0.25);
}

.agent-version-actions :deep(.el-button--primary:hover),
.agent-version-filters__actions :deep(.el-button--primary:hover) {
  background: #277a70;
}

.agent-version-actions :deep(.el-button--default),
.agent-version-filters__actions :deep(.el-button--default) {
  border-color: #d8e4e0;
  color: #475569;
  background: #fff;
}

.agent-version-actions :deep(.el-button--default:hover),
.agent-version-filters__actions :deep(.el-button--default:hover) {
  border-color: #bcd3cc;
  color: #334155;
  background: #f8fcfa;
}

.agent-version-surface :deep(.el-table th.el-table__cell) {
  background: #fbfcfc;
  color: #64748b;
  font-weight: 600;
}

.agent-version-surface :deep(.el-table td.el-table__cell),
.agent-version-surface :deep(.el-table th.el-table__cell) {
  border-color: #edf2f0;
}

.agent-version-output-tag {
  margin-left: 8px;
  vertical-align: middle;
}

.agent-version-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  line-height: 1;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-weight: 600;
}

.agent-version-status.is-designing {
  color: #4b6a7d;
  background: #f5f9fd;
  border-color: #d8e8f6;
}

.agent-version-status.is-published {
  color: #8a6a2a;
  background: #fdf9f1;
  border-color: #f2e3c4;
}

.agent-version-status.is-online {
  color: #2c7560;
  background: #f3fbf7;
  border-color: #d4ecdf;
}

.agent-version-status__icon {
  font-size: 14px;
}

.agent-version-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #6d8fa6;
  flex-shrink: 0;
}

.agent-version-status.is-published .agent-version-status__icon {
  color: #c1912f;
}

.agent-version-status.is-online .agent-version-status__icon {
  color: #44a082;
}

.agent-version-mode {
  color: #475569;
  font-weight: 500;
}

.agent-version-ops {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 4px;
}

.agent-version-op {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.agent-version-ops :deep(.el-button.is-link) {
  color: #2f6f65;
  font-weight: 600;
}

.agent-version-ops :deep(.el-button.is-link:hover) {
  color: #245a52;
}

.agent-version-op .el-icon {
  font-size: 15px;
}

.agent-version-op--online .el-icon {
  color: #2b8a75;
}

.agent-version-op--offline .el-icon {
  color: #5f6f84;
}

.agent-version-op--online {
  color: #2b8a75 !important;
}

.agent-version-op--online:hover {
  color: #1f6c5a !important;
}

.agent-version-op--offline {
  color: #5f6f84 !important;
}

.agent-version-op--offline:hover {
  color: #475569 !important;
}

.agent-version-op--offline:hover .el-icon {
  color: #475569;
}

.agent-version-op--delete:not(.is-disabled) .el-icon {
  color: #d35c69;
}

.agent-version-op--delete:not(.is-disabled) {
  color: #d35c69 !important;
}

.agent-version-op--delete:not(.is-disabled):hover {
  color: #b84754 !important;
}

.agent-version-op--delete.is-disabled,
.agent-version-op--delete:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.agent-version-pagination {
  margin-top: 14px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.agent-version-pagination__info {
  font-size: 12px;
  color: #64748b;
}

.agent-version-output-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
  line-height: 1.5;
}

.agent-version-clone-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
  line-height: 1.55;
}

.agent-api-debug {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.agent-api-debug__meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 10px;
  border: 1px solid #e0ebe8;
  border-radius: 8px;
  background: #fff;
}

.agent-api-debug__label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.agent-api-debug code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: #0f172a;
  word-break: break-all;
}

.agent-api-debug__request pre {
  margin: 0;
  max-height: 130px;
  overflow: auto;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid #e0ebe8;
  background: #fff;
  color: #334155;
  font-size: 12px;
  line-height: 1.55;
}

.agent-api-debug__section-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.agent-api-debug__result {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.agent-api-debug__panel {
  min-width: 0;
}

.agent-api-debug__events,
.agent-api-debug__answer {
  height: 180px;
  overflow: auto;
  padding: 10px;
  border: 1px solid #e0ebe8;
  border-radius: 8px;
  background: #fff;
  line-height: 1.6;
  white-space: pre-wrap;
}

.agent-api-debug__empty {
  color: var(--el-text-color-placeholder);
}

.agent-api-debug__event {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}

.agent-api-debug__event-time {
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.agent-api-debug__event-text {
  min-width: 0;
  word-break: break-word;
}

.agent-api-debug__event.is-error {
  color: var(--el-color-danger);
}

.agent-api-debug__event.is-finish {
  color: var(--el-color-success);
}

.agent-api-debug__event.is-text {
  color: var(--el-color-primary);
}

@media (max-width: 760px) {
  .agent-version-pagination {
    justify-content: center;
    flex-wrap: wrap;
  }

  .agent-version-pagination :deep(.el-pagination) {
    justify-content: center;
  }

  .agent-api-debug__meta,
  .agent-api-debug__result {
    grid-template-columns: 1fr;
  }
}
</style>
