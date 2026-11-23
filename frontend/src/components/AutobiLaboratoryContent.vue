<template>
  <div class="lab-page" :class="{ 'is-embedded-dialog': embeddedInDialog }">
    <!-- 左：对话记录 -->
    <aside class="lab-sidebar">
      <el-button type="primary" class="lab-new-chat" :icon="Plus" @click="createConversation">
        新建对话
      </el-button>
      <div class="lab-session-list">
        <button
          v-for="c in conversations"
          :key="c.id"
          type="button"
          class="lab-session-item"
          :class="{ active: c.id === activeConversationId }"
          @click="selectConversation(c.id)"
        >
          <span class="lab-session-title">{{ c.title }}</span>
          <span class="lab-session-time">{{ formatShortTime(c.updatedAt) }}</span>
        </button>
      </div>
      <div class="lab-sidebar-foot">
        <el-button text type="primary" @click="handleExit">
          {{ embeddedInDialog ? '关闭窗口' : '← 返回实验中心列表' }}
        </el-button>
      </div>
    </aside>

    <!-- 中：聊天（仅展示 bi-data-summary） -->
    <main class="lab-center">
      <header class="lab-center-head">
        <h1 class="lab-project-title">{{ projectName || '加载中…' }}</h1>
        <div class="lab-center-head-actions">
          <el-badge :is-dot="gatewayFeaturesConfigured" class="lab-features-badge">
            <el-button type="primary" plain size="small" @click="openRequestBodyDialog">
              请求体设置
            </el-button>
          </el-badge>
        </div>
      </header>

      <div ref="scrollRef" class="lab-messages">
        <div v-if="!activeTurns.length" class="lab-empty-hint">
          发送后与对外接口相同：请求 <code>POST /api/autobi/gateway/v2/lab</code>（SSE），流水线在后端执行并写入
          Redis；中间区展示总结流式结果、SQL 与表格（从追踪解析）；右侧调试信息通过轮询 Redis 拉取完整步骤。
        </div>
        <template v-else>
          <div v-for="(turn, idx) in activeTurns" :key="idx" class="lab-turn">
            <div class="lab-bubble lab-bubble-user">
              <span class="lab-bubble-label">我</span>
              <div class="lab-bubble-body">{{ turn.userMessage }}</div>
            </div>
            <div v-if="turn.traceId" class="lab-trace-strip">
              <span class="lab-trace-label">追踪 ID</span>
              <code class="lab-trace-code">{{ turn.traceId }}</code>
              <el-button
                link
                type="primary"
                size="small"
                native-type="button"
                @click.stop.prevent="copyTraceId(turn.traceId)"
              >
                复制
              </el-button>
              <router-link
                class="lab-trace-link"
                target="_blank"
                rel="noopener noreferrer"
                :to="{ name: 'AutobiLabTraceView', params: { traceId: turn.traceId } }"
              >
                日志页
              </router-link>
            </div>
            <div v-if="turn.rewrittenQuery" class="lab-rewrite-block">
              <div class="lab-rewrite-header">
                <span class="lab-rewrite-label">改写后的问题</span>
                <el-button
                  link
                  type="primary"
                  size="small"
                  native-type="button"
                  @click.stop.prevent="copySql(turn.rewrittenQuery)"
                >
                  复制
                </el-button>
              </div>
              <div class="lab-rewrite-body">{{ turn.rewrittenQuery }}</div>
            </div>
            <div v-if="turn.generatedSql" class="lab-sql-block">
              <div class="lab-sql-header">
                <span class="lab-sql-label">生成的 SQL</span>
                <el-button
                  link
                  type="primary"
                  size="small"
                  native-type="button"
                  @click.stop.prevent="copySql(turn.generatedSql)"
                >
                  复制
                </el-button>
              </div>
              <pre class="lab-sql-code">{{ turn.generatedSql }}</pre>
            </div>
            <div v-if="turn.sqlData && !turn.sqlData.skipped && turn.sqlData.rows?.length" class="lab-sql-result-block">
              <div class="lab-sql-result-header">
                <span class="lab-sql-result-label">SQL 查询结果</span>
                <span class="lab-sql-result-count">共 {{ turn.sqlData.row_count || turn.sqlData.rows.length }} 条记录</span>
              </div>
              <div class="lab-sql-result-table-wrap">
                <el-table
                  :data="turn.sqlData.rows"
                  size="small"
                  border
                  stripe
                  max-height="300"
                >
                  <el-table-column
                    v-for="col in turn.sqlData.columns"
                    :key="col"
                    :prop="col"
                    :label="col"
                    min-width="120"
                    show-overflow-tooltip
                  />
                </el-table>
              </div>
            </div>
            <div v-else-if="turn.sqlData && turn.sqlData.skipped" class="lab-sql-result-block lab-sql-result-skipped">
              <span class="lab-sql-result-label">SQL 查询结果</span>
              <span class="lab-sql-result-skip-reason">{{ turn.sqlData.reason || '已跳过' }}</span>
            </div>
            <AutobiLabChartPanel
              v-if="turn.chartSpec && turn.sqlData && !turn.sqlData.skipped && turn.sqlData.rows?.length"
              :spec="turn.chartSpec"
              :sql-data="turn.sqlData"
            />
            <div v-if="turn.labResult" class="lab-bubble lab-bubble-assistant">
              <template v-if="turn.labResult.kind === 'sql'">
                <span class="lab-bubble-label">SQL</span><pre class="ddi-sql">{{ turn.labResult.sql }}</pre>
              </template>
              <template v-else-if="turn.labResult.kind === 'recall'">
                <span class="lab-bubble-label">召回依据</span>
                <ol><li v-for="(item, i) in turn.labResult.items" :key="i"><strong>{{ item.text || item.field }}</strong> {{ item.content || item.table }}</li></ol>
              </template>
              <p v-else>{{ turn.labResult.message }}</p>
            </div>
            <div v-else-if="turn.biSummary || turn.streamingSummary" class="lab-bubble lab-bubble-assistant">
              <span class="lab-bubble-label">数据总结</span>
              <div class="lab-bubble-body markdown-like">{{ turn.streamingSummary || turn.biSummary }}</div>
              <span v-if="turn.streamingSummary && !turn.biSummary" class="lab-streaming-cursor">▊</span>
            </div>
            <div v-else-if="turn.loading" class="lab-bubble lab-bubble-assistant is-loading">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>正在执行流水线…</span>
            </div>
          </div>
        </template>
      </div>

      <footer class="lab-input-footer">
        <div class="lab-input-bar">
          <div class="lab-input-icon" aria-hidden="true">
            <span class="lab-bot-face" />
          </div>
          <el-input
            v-model="inputText"
            class="lab-input-field"
            placeholder="请输入"
            :disabled="pipelineRunning"
            @keydown.enter.exact.prevent="handleSend"
          />
          <el-button
            type="primary"
            class="lab-send-btn"
            :loading="pipelineRunning"
            @click="handleSend"
          >
            发送
          </el-button>
        </div>
        <p class="lab-disclaimer">
          发送即调用网关 SSE（与对外接口一致）；对话记录在服务端，步骤详情由 Redis 按 trace_id 提供。
        </p>
      </footer>

      <button type="button" class="lab-debug-tab" @click="debugOpen = !debugOpen">
        <span class="lab-debug-tab-icon">◆</span>
        <span class="lab-debug-tab-text">{{ debugOpen ? '关闭调试' : '开启调试' }}</span>
      </button>
    </main>

    <el-dialog
      v-model="requestBodyDialogVisible"
      title="请求体设置 · features"
      width="520px"
      :append-to-body="false"
      class="lab-request-body-dialog"
      @closed="onRequestBodyDialogClosed"
    >
      <p class="lab-body-dialog-hint">
        以下为网关 <code>POST …/gateway/v2/lab</code> 请求体中的 <code>features</code>（须为 JSON 对象）。保存后，每次「发送」都会带上；后端会用占位符里
        <strong>点号前的第一段</strong>作为键做替换（整段占位符替换为该键的值）。例如占位符
        <code v-pre>{{max_year}}</code> 对应 <code v-pre>{"max_year":2023}</code>；若为
        <code v-pre>{{features.max_year}}</code>，则需顶层键 <code>features</code>，且其值会整体替换该占位符（常见可填年份数字）。
      </p>
      <el-input
        v-model="featuresJsonDraft"
        type="textarea"
        :rows="12"
        class="lab-features-json-input"
        spellcheck="false"
        placeholder='默认含 max_year、max_month；可改为例如 { "max_year": 2025, "max_month": "12" }'
      />
      <template #footer>
        <el-button @click="requestBodyDialogVisible = false">取消</el-button>
        <el-button type="danger" plain @click="clearRequestBodyDraft">清空</el-button>
        <el-button type="primary" @click="saveRequestBodySettings">保存</el-button>
      </template>
    </el-dialog>

    <aside class="lab-debug-panel" :class="{ 'is-open': debugOpen }">
      <div class="lab-debug-head">
        <span class="lab-debug-title">调试信息</span>
        <button type="button" class="lab-debug-close" @click="debugOpen = false">
          关闭调试信息
        </button>
      </div>

      <div v-if="!debugOpen" class="lab-debug-placeholder" />

      <div v-else class="lab-debug-body">
        <template v-if="debugLoadingHint">
          <section class="lab-debug-intro">
            <p class="lab-debug-loading-text">正在从 Redis 加载流水线步骤…</p>
          </section>
        </template>
        <template v-else-if="!panelSteps.length && !pipelineRunning">
          <section class="lab-debug-intro">
            <h4>什么是调试信息？</h4>
            <p>与「日志页」同源：从 Redis 读取当前追踪 ID 下的各步 request/response。</p>
            <h4>如何触发？</h4>
            <p>点击「发送」后，网关返回 <code>trace_id</code> 后轮询 Redis 刷新本侧栏。</p>
            <h4>时效性</h4>
            <p>展示当前对话最后一次提问对应的追踪（可点「日志页」全屏查看）。</p>
          </section>
        </template>

        <template v-else>
          <AutobiLabStepCards :rows="panelSteps" />
        </template>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Loading } from '@element-plus/icons-vue'
import defaultLabCfg from '../config/autobiLabDefaultConfig.json'
import { getAutobiProject } from '../api/autobi'
import { getAutobiLabChatState, putAutobiLabChatState } from '../api/autobiLabChat'
import { getAutobiLabTrace } from '../api/autobiLabTrace'
import { streamAutobiLabGateway } from '../api/autobiLabGateway'
import AutobiLabStepCards from './AutobiLabStepCards.vue'
import AutobiLabChartPanel from './AutobiLabChartPanel.vue'
import { mergeAutobiLabConfig } from '../utils/autobiLabMergeConfig.js'
import {
  normalizeTraceStepsToRows,
  extractTurnDisplayFromTrace,
  tracePipelineFinished
} from '../utils/autobiLabTraceNormalize.js'

const props = defineProps({
  /** 项目 ID（与路由 / 弹窗传入一致） */
  projectId: {
    type: [String, Number],
    required: true
  },
  /** 在列表全屏弹窗内使用时为 true，底部为「关闭窗口」并 emit close */
  embeddedInDialog: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const router = useRouter()

const resolvedProjectId = computed(() => String(props.projectId))

const projectName = ref('')
/** 网关 body.id：10 位 api_access_id */
const apiAccessId = ref('')
const knowledgeBaseId = ref(null)
/** 默认 autobiLabDefaultConfig.json 与项目 config_json 深度合并（先默认，避免首屏竞态） */
const labMergedConfig = ref(mergeAutobiLabConfig(defaultLabCfg, {}))

const conversations = ref([])
const activeConversationId = ref(null)
const inputText = ref('')
const scrollRef = ref(null)
const debugOpen = ref(false)
const pipelineRunning = ref(false)
/** 调试侧栏：与 Redis GET trace 一致的结构 */
const redisDebugRows = ref([])

/** 网关请求体 features：每次发送默认带上 */
const DEFAULT_GATEWAY_FEATURES = Object.freeze({ max_year: 2026, max_month: '03' })

function sortedFeaturesJson(obj) {
  const o = obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {}
  return JSON.stringify(o, Object.keys(o).sort())
}

const gatewayFeatures = shallowRef({ ...DEFAULT_GATEWAY_FEATURES })
const requestBodyDialogVisible = ref(false)
const featuresJsonDraft = ref('{}')

function parseFeaturesObject(text) {
  const trimmed = (text || '').trim()
  if (!trimmed) return {}
  let parsed
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    throw new Error('JSON 格式不正确，请检查括号与引号')
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('features 必须是 JSON 对象（键值对），不能是数组或纯字符串')
  }
  return parsed
}

const gatewayFeaturesConfigured = computed(() => {
  const v = { ...DEFAULT_GATEWAY_FEATURES, ...(gatewayFeatures.value || {}) }
  return sortedFeaturesJson(v) !== sortedFeaturesJson({ ...DEFAULT_GATEWAY_FEATURES })
})

function openRequestBodyDialog() {
  featuresJsonDraft.value = JSON.stringify(
    { ...DEFAULT_GATEWAY_FEATURES, ...(gatewayFeatures.value || {}) },
    null,
    2
  )
  requestBodyDialogVisible.value = true
}

function clearRequestBodyDraft() {
  featuresJsonDraft.value = '{}'
}

function saveRequestBodySettings() {
  try {
    const obj = parseFeaturesObject(featuresJsonDraft.value)
    const merged = { ...DEFAULT_GATEWAY_FEATURES, ...obj }
    gatewayFeatures.value = merged
    if (sortedFeaturesJson(merged) === sortedFeaturesJson({ ...DEFAULT_GATEWAY_FEATURES })) {
      ElMessage.success('已保存为默认：max_year=2026，max_month=03')
    } else {
      ElMessage.success('已保存，后续发送将默认携带 features')
    }
    requestBodyDialogVisible.value = false
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  }
}

function onRequestBodyDialogClosed() {
  featuresJsonDraft.value = '{}'
}

const activeConversation = computed(() =>
  conversations.value.find(c => c.id === activeConversationId.value)
)

const activeTurns = computed(() => activeConversation.value?.turns ?? [])

const panelSteps = computed(() => redisDebugRows.value)

const debugLoadingHint = computed(
  () => debugOpen.value && pipelineRunning.value && !redisDebugRows.value.length
)

function formatShortTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/**
 * Generate UUID with fallback for non-secure contexts (HTTP)
 * crypto.randomUUID() is only available in secure contexts (HTTPS) or localhost
 */
function uuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // Fallback: generate a UUID v4 format string
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}

/** 入库不存 steps；调试区始终走 Redis trace */
function normalizeTurnFromApi(t) {
  return {
    ...t,
    steps: []
  }
}

function normalizeConversationFromApi(c) {
  return {
    ...c,
    turns: (c.turns || []).map(normalizeTurnFromApi)
  }
}

function sanitizeConversationsForDb(list) {
  return list.map(c => ({
    id: c.id,
    title: c.title,
    updatedAt: c.updatedAt,
    turns: (c.turns || []).map(t => {
      const { steps: _steps, ...rest } = t
      return rest
    })
  }))
}

let persistTimer = null

async function flushPersistToApiForProject(projectId) {
  if (!projectId || !conversations.value.length) return
  try {
    await putAutobiLabChatState(projectId, {
      conversations: sanitizeConversationsForDb(conversations.value),
      active_conversation_id: activeConversationId.value
    })
  } catch (e) {
    console.warn('[autobi lab chat] 持久化失败', e)
  }
}

async function flushPersistToApi() {
  return flushPersistToApiForProject(resolvedProjectId.value)
}

function schedulePersist() {
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    persistTimer = null
    void flushPersistToApi()
  }, 600)
}

async function copyTextWithFallback(text, successMsg) {
  if (text == null || text === '') return
  const str = String(text)
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(str)
      ElMessage.success(successMsg)
      return
    }
  } catch {
    /* fallback below */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = str
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    ta.style.top = '0'
    document.body.appendChild(ta)
    ta.select()
    ta.setSelectionRange(0, str.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    if (ok) ElMessage.success(successMsg)
    else ElMessage.warning('复制失败，请手动选择复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}

function copyTraceId(id) {
  void copyTextWithFallback(id, '已复制追踪 ID')
}

function copySql(sql) {
  void copyTextWithFallback(sql, '已复制')
}

function handleExit() {
  if (props.embeddedInDialog) {
    emit('close')
  } else {
    router.push({ name: 'AutoBIList' })
  }
}

async function loadChatStateFromServer() {
  try {
    const data = await getAutobiLabChatState(resolvedProjectId.value)
    const list = data?.conversations
    if (Array.isArray(list) && list.length > 0) {
      conversations.value = list.map(normalizeConversationFromApi)
      const active = data.active_conversation_id
      activeConversationId.value =
        active && list.some(c => c.id === active) ? active : list[0].id
      return
    }
  } catch (e) {
    console.warn('[autobi lab chat] 读取对话状态失败', e)
  }
  createConversation()
}

watch([conversations, activeConversationId], () => schedulePersist(), { deep: true })

function createConversation() {
  const id = uid()
  const c = {
    id,
    title: '新对话',
    updatedAt: Date.now(),
    turns: []
  }
  conversations.value.unshift(c)
  activeConversationId.value = id
}

function selectConversation(id) {
  activeConversationId.value = id
}

async function scrollToBottom() {
  await nextTick()
  const el = scrollRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function loadProjectMeta() {
  try {
    const detail = await getAutobiProject(resolvedProjectId.value)
    projectName.value = detail.name || `项目 #${resolvedProjectId.value}`
    apiAccessId.value = (detail.api_access_id || '').trim()
    labMergedConfig.value = mergeAutobiLabConfig(defaultLabCfg, detail.config_json || {})
    knowledgeBaseId.value =
      detail.knowledge_base_id ??
      detail.config_json?.knowledge_base_id ??
      labMergedConfig.value?.knowledge_base_id ??
      null
  } catch {
    projectName.value = `项目 #${resolvedProjectId.value}`
    apiAccessId.value = ''
    labMergedConfig.value = mergeAutobiLabConfig(defaultLabCfg, {})
    knowledgeBaseId.value = labMergedConfig.value?.knowledge_base_id ?? null
    ElMessage.warning('加载项目信息失败，无法获取 API ID 时发送将不可用')
  }
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || pipelineRunning.value) return

  if (!apiAccessId.value?.trim()) {
    ElMessage.error('项目缺少 API 调用 ID（api_access_id），无法调用网关。请返回列表查看卡片上的 API ID 或刷新项目。')
    return
  }

  const conv = activeConversation.value
  if (!conv) {
    createConversation()
  }
  const c = activeConversation.value
  const traceStartedAt = Date.now()

  c.turns.push({
    traceId: null,
    traceStartedAt,
    userMessage: text,
    rewrittenQuery: '',
    biSummary: '',
    streamingSummary: '',
    generatedSql: '',
    sqlData: null,
    chartSpec: null,
    loading: true,
    steps: []
  })
  if (c.title === '新对话') {
    c.title = text.length > 18 ? `${text.slice(0, 18)}…` : text
  }
  c.updatedAt = Date.now()
  inputText.value = ''
  await scrollToBottom()

  pipelineRunning.value = true
  redisDebugRows.value = []

  const turn = c.turns[c.turns.length - 1]

  let pollTimer = null
  let backendTraceId = null

  const stopPoll = () => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  const refreshTrace = async () => {
    if (!backendTraceId) return
    try {
      const t = await getAutobiLabTrace(backendTraceId)
      redisDebugRows.value = normalizeTraceStepsToRows(t)
      const disp = extractTurnDisplayFromTrace(t)
      if (disp.rewrittenQuery) turn.rewrittenQuery = disp.rewrittenQuery
      if (disp.generatedSql) turn.generatedSql = disp.generatedSql
      if (disp.sqlData) turn.sqlData = disp.sqlData
      if (disp.chartSpec != null) turn.chartSpec = disp.chartSpec
      if (tracePipelineFinished(t)) {
        if (disp.biSummary && !turn.streamingSummary) turn.biSummary = disp.biSummary
      }
    } catch (e) {
      console.warn('[autobi lab] Redis trace 拉取失败', e)
    }
  }

  try {
    await streamAutobiLabGateway(
      {
        content: text,
        id: apiAccessId.value.trim(),
        features: { ...gatewayFeatures.value }
      },
      {
        onEvent: ev => {
          if (ev.type === 'trace_id' && ev.trace_id) {
            backendTraceId = ev.trace_id
            turn.traceId = backendTraceId
            void refreshTrace()
            if (!pollTimer) {
              pollTimer = setInterval(() => void refreshTrace(), 450)
            }
          }
          if (ev.type === 'lab_result') {
            turn.labResult = ev
            void scrollToBottom()
          }
          if (ev.type === 'summary' && ev.delta) {
            turn.streamingSummary = (turn.streamingSummary || '') + ev.delta
            void scrollToBottom()
          }
          if (ev.type === 'error') {
            const msg = ev.message || '网关错误'
            turn.biSummary = turn.biSummary || `错误：${msg}`
            ElMessage.error(msg)
          }
        }
      }
    )
  } catch (e) {
    if (e?.name !== 'AbortError') {
      const msg = e?.message || String(e)
      turn.biSummary = `执行失败：${msg}`
      ElMessage.error(msg)
    }
  } finally {
    stopPoll()
    if (turn.streamingSummary) {
      turn.biSummary = turn.streamingSummary
      turn.streamingSummary = ''
    }
    await refreshTrace()
    turn.loading = false
    pipelineRunning.value = false
    c.updatedAt = Date.now()
    await scrollToBottom()
    void flushPersistToApi()
  }
}

async function loadDebugTraceForActiveConversation() {
  if (!debugOpen.value || pipelineRunning.value) return
  const turns = activeConversation.value?.turns ?? []
  const last = turns[turns.length - 1]
  if (!last?.traceId) {
    redisDebugRows.value = []
    return
  }
  try {
    const t = await getAutobiLabTrace(last.traceId)
    redisDebugRows.value = normalizeTraceStepsToRows(t)
  } catch {
    redisDebugRows.value = []
  }
}

watch([debugOpen, activeConversationId], () => {
  void loadDebugTraceForActiveConversation()
})

async function bootstrap() {
  gatewayFeatures.value = { ...DEFAULT_GATEWAY_FEATURES }
  conversations.value = []
  activeConversationId.value = null
  await Promise.all([loadProjectMeta(), loadChatStateFromServer()])
}

watch(
  () => props.projectId,
  async (newId, oldId) => {
    if (oldId !== undefined && oldId !== null && String(oldId) !== String(newId)) {
      if (persistTimer) {
        clearTimeout(persistTimer)
        persistTimer = null
      }
      await flushPersistToApiForProject(String(oldId))
    }
    await bootstrap()
  }
)

onMounted(() => {
  void bootstrap()
})

onUnmounted(() => {
  if (persistTimer) clearTimeout(persistTimer)
  void flushPersistToApiForProject(resolvedProjectId.value)
})
</script>

<style scoped>
.ddi-sql { white-space: pre-wrap; overflow-wrap: anywhere; font: 13px/1.65 monospace; }
.lab-page {
  display: flex;
  height: calc(100vh - 100px);
  margin: -20px;
  min-height: 560px;
  background: linear-gradient(165deg, #daf0f4 0%, #eaf8fa 35%, #eff9fb 70%, #e2f3f5 100%);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.lab-page.is-embedded-dialog {
  height: 100%;
  min-height: 0;
  margin: 0;
}

.lab-sidebar {
  width: 240px;
  flex-shrink: 0;
  padding: 16px 12px;
  background: rgba(255, 255, 255, 0.45);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(255, 255, 255, 0.6);
  display: flex;
  flex-direction: column;
}

.lab-new-chat {
  width: 100%;
  margin-bottom: 12px;
  border-radius: 10px;
  font-weight: 500;
  --el-button-bg-color: #1fb8cc;
  --el-button-border-color: #1fb8cc;
}

.lab-session-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lab-session-item {
  text-align: left;
  padding: 10px 12px;
  border: none;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  transition: background 0.15s;
}

.lab-session-item:hover {
  background: rgba(255, 255, 255, 0.85);
}

.lab-session-item.active {
  background: rgba(31, 184, 204, 0.15);
  box-shadow: 0 0 0 1px rgba(31, 184, 204, 0.35);
}

.lab-session-title {
  display: block;
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lab-session-time {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
  display: block;
}

.lab-sidebar-foot {
  padding-top: 12px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.lab-center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  transition: flex-basis 0.28s ease;
}

.lab-center-head {
  position: relative;
  padding: 20px 24px 8px;
  text-align: center;
}

.lab-center-head-actions {
  position: absolute;
  right: 24px;
  top: 16px;
}

.lab-features-badge :deep(.el-badge__content.is-dot) {
  right: 6px;
  top: 6px;
}

.lab-body-dialog-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.55;
}

.lab-body-dialog-hint code {
  font-size: 12px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(31, 184, 204, 0.08);
}

.lab-features-json-input :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  font-size: 13px;
  line-height: 1.45;
}

.lab-project-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.lab-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px 8px;
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  min-height: 0;
}

.lab-empty-hint {
  text-align: center;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
  padding: 48px 16px;
}

.lab-turn {
  margin-bottom: 20px;
}

.lab-bubble {
  margin-bottom: 12px;
}

.lab-bubble-user .lab-bubble-body {
  margin-left: auto;
  max-width: 85%;
  background: rgba(31, 184, 204, 0.12);
  border: 1px solid rgba(31, 184, 204, 0.2);
}

.lab-bubble-assistant .lab-bubble-body {
  max-width: 95%;
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 4px 24px rgba(31, 184, 204, 0.08);
}

.lab-bubble-label {
  display: block;
  font-size: 11px;
  color: #909399;
  margin-bottom: 6px;
  padding-left: 4px;
}

.lab-bubble-user .lab-bubble-label {
  text-align: right;
  padding-right: 8px;
}

.lab-bubble-body {
  padding: 12px 14px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.65;
  color: #303133;
}

.lab-bubble-body.markdown-like {
  white-space: pre-wrap;
}

.lab-streaming-cursor {
  display: inline-block;
  margin-left: 2px;
  animation: blink 1s infinite;
  color: #1fb8cc;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.lab-bubble-assistant.is-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #606266;
  font-size: 13px;
}

.lab-trace-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  margin: 0 0 10px;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(31, 184, 204, 0.2);
  font-size: 12px;
}

.lab-trace-label {
  color: #909399;
  flex-shrink: 0;
}

.lab-rewrite-block {
  margin: 0 0 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(34, 139, 120, 0.22);
}

.lab-rewrite-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.lab-rewrite-label {
  font-size: 12px;
  font-weight: 500;
  color: #1d8a7a;
}

.lab-rewrite-body {
  font-size: 14px;
  line-height: 1.55;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}

.lab-sql-block {
  margin: 0 0 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(31, 184, 204, 0.15);
}

.lab-sql-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.lab-sql-label {
  font-size: 12px;
  font-weight: 500;
  color: #1fb8cc;
}

.lab-sql-code {
  margin: 0;
  padding: 10px 12px;
  background: #1e1e2e;
  border-radius: 8px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #cdd6f4;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.lab-sql-result-block {
  margin: 0 0 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(31, 184, 204, 0.15);
}

.lab-sql-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.lab-sql-result-label {
  font-size: 12px;
  font-weight: 500;
  color: #1fb8cc;
}

.lab-sql-result-count {
  font-size: 11px;
  color: #909399;
}

.lab-sql-result-table-wrap {
  margin-top: 8px;
}

.lab-sql-result-table-wrap .el-table {
  --el-table-border-color: #ebeef5;
}

.lab-sql-result-table-wrap .el-table th.el-table__cell {
  background-color: #f5f7fa;
  font-weight: 500;
  color: #303133;
}

.lab-sql-result-skipped {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lab-sql-result-skip-reason {
  font-size: 12px;
  color: #909399;
}

.lab-trace-code {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  word-break: break-all;
  color: #303133;
}

.lab-trace-link {
  color: #1fb8cc;
  text-decoration: none;
  font-weight: 500;
}

.lab-trace-link:hover {
  text-decoration: underline;
}

.lab-input-footer {
  padding: 12px 24px 20px;
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  flex-shrink: 0;
}

.lab-input-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(8px);
  border-radius: 20px;
  box-shadow: 0 8px 32px rgba(31, 184, 204, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.9);
}

.lab-input-icon {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #bceaf0, #d2f1f5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.lab-bot-face {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  background: linear-gradient(145deg, #1fb8cc, #17a0b3);
  opacity: 0.9;
}

.lab-input-field {
  flex: 1;
}

.lab-input-field :deep(.el-input__wrapper) {
  box-shadow: none;
  background: transparent;
}

.lab-send-btn {
  flex-shrink: 0;
  border-radius: 12px;
  padding: 10px 20px;
  --el-button-bg-color: #1fb8cc;
  --el-button-border-color: #1fb8cc;
}

.lab-disclaimer {
  margin: 8px 8px 0;
  font-size: 11px;
  color: #a0a4ae;
  line-height: 1.4;
}

.lab-debug-tab {
  position: absolute;
  top: 50%;
  right: 0;
  transform: translateY(-50%);
  z-index: 5;
  width: 36px;
  padding: 12px 0;
  border: none;
  border-radius: 10px 0 0 10px;
  background: rgba(31, 184, 204, 0.92);
  color: #fff;
  cursor: pointer;
  box-shadow: -2px 0 12px rgba(31, 184, 204, 0.25);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  transition: right 0.28s ease;
}

.lab-debug-tab-icon {
  font-size: 10px;
  opacity: 0.9;
}

.lab-debug-tab-text {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  font-size: 12px;
  letter-spacing: 2px;
}

.lab-debug-panel {
  width: 0;
  flex-shrink: 0;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  border-left: 1px solid rgba(0, 0, 0, 0.06);
  transition: width 0.28s ease;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.lab-debug-panel.is-open {
  width: 380px;
}

.lab-debug-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 10px;
  border-bottom: 1px solid #ebeef5;
}

.lab-debug-title {
  font-weight: 600;
  font-size: 15px;
  color: #303133;
}

.lab-debug-close {
  border: none;
  background: none;
  color: #1fb8cc;
  font-size: 13px;
  cursor: pointer;
}

.lab-debug-close:hover {
  text-decoration: underline;
}

.lab-debug-placeholder {
  flex: 1;
}

.lab-debug-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px 12px 20px;
  width: 380px;
  min-height: 0;
}

.lab-debug-intro h4 {
  margin: 12px 0 6px;
  font-size: 13px;
  color: #303133;
}

.lab-debug-intro p {
  margin: 0 0 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}
</style>
