<template>
  <div class="lab-share-page">
    <!-- 左：对话记录 -->
    <aside class="lab-sidebar">
      <el-button type="primary" class="lab-new-chat" :icon="Plus" @click="createConversation">
        新建对话
      </el-button>
      <div class="lab-session-list">
        <button
          v-for="c in displayConversations"
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
      <div v-if="conversations.length > MAX_DISPLAY_CONVERSATIONS" class="lab-session-hint">
        仅展示最近 {{ MAX_DISPLAY_CONVERSATIONS }} 条聊天记录
      </div>
    </aside>

    <!-- 中：聊天 -->
    <main class="lab-center">
      <header class="lab-center-head">
        <h1 class="lab-project-title">{{ projectName || '加载中…' }}</h1>
      </header>

      <div ref="scrollRef" class="lab-messages">
        <div v-if="!activeTurns.length" class="lab-empty-hint">
          在下方输入问题，即可体验 AutoBI 智能分析。
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
            </div>
            <div v-if="turn.rewrittenQuery" class="lab-rewrite-block">
              <div class="lab-rewrite-header">
                <span class="lab-rewrite-label">改写后的问题</span>
                <el-button
                  link
                  type="primary"
                  size="small"
                  native-type="button"
                  @click.stop.prevent="copyText(turn.rewrittenQuery)"
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
                  @click.stop.prevent="copyText(turn.generatedSql)"
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
            <div v-if="turn.biSummary || turn.streamingSummary" class="lab-bubble lab-bubble-assistant">
              <span class="lab-bubble-label">{{ turn.labKind === 'recall' ? '召回依据' : turn.labKind === 'clarification' ? '需要补充' : '数据总结' }}</span>
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
      </footer>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Loading } from '@element-plus/icons-vue'
import {
  createAutobiLabShareApi,
  streamAutobiLabShareGateway
} from '@/api/autobiLabShare'
import AutobiLabChartPanel from '@/components/AutobiLabChartPanel.vue'
import {
  normalizeTraceStepsToRows,
  extractTurnDisplayFromTrace,
  tracePipelineFinished
} from '@/utils/autobiLabTraceNormalize.js'

const props = defineProps({
  token: { type: String, required: true }
})

const shareApi = computed(() => createAutobiLabShareApi(props.token))

const projectName = ref('')
const apiAccessId = ref('')

const conversations = ref([])
const activeConversationId = ref(null)
const inputText = ref('')
const scrollRef = ref(null)
const pipelineRunning = ref(false)

const DEFAULT_GATEWAY_FEATURES = Object.freeze({ max_year: 2026, max_month: '03' })

const activeConversation = computed(() =>
  conversations.value.find(c => c.id === activeConversationId.value)
)
const activeTurns = computed(() => activeConversation.value?.turns ?? [])

const MAX_DISPLAY_CONVERSATIONS = 5
const displayConversations = computed(() => {
  const list = conversations.value
  if (list.length <= MAX_DISPLAY_CONVERSATIONS) return list
  const active = activeConversationId.value
  const top = list.slice(0, MAX_DISPLAY_CONVERSATIONS)
  if (active && !top.some(c => c.id === active)) {
    const found = list.find(c => c.id === active)
    if (found) {
      top[MAX_DISPLAY_CONVERSATIONS - 1] = found
    }
  }
  return top
})

function formatShortTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function uuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0
    const v = c === 'x' ? r : (r & 0x3 | 0x8)
    return v.toString(16)
  })
}

function normalizeTurnFromApi(t) {
  return { ...t, steps: [] }
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

async function flushPersistToApi() {
  if (!conversations.value.length) return
  try {
    await shareApi.value.saveChatState({
      conversations: sanitizeConversationsForDb(conversations.value),
      active_conversation_id: activeConversationId.value
    })
  } catch (e) {
    console.warn('[autobi lab share] 持久化失败', e)
  }
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
  } catch { /* fallback */ }
  try {
    const ta = document.createElement('textarea')
    ta.value = str
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    ta.setSelectionRange(0, str.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    if (ok) ElMessage.success(successMsg)
    else ElMessage.warning('复制失败')
  } catch {
    ElMessage.warning('复制失败')
  }
}

function copyTraceId(id) { void copyTextWithFallback(id, '已复制追踪 ID') }
function copyText(text) { void copyTextWithFallback(text, '已复制') }

async function loadChatStateFromServer() {
  try {
    const data = await shareApi.value.getChatState()
    const list = data?.conversations
    if (Array.isArray(list) && list.length > 0) {
      conversations.value = list.map(normalizeConversationFromApi)
      const active = data.active_conversation_id
      activeConversationId.value =
        active && list.some(c => c.id === active) ? active : list[0].id
      return
    }
  } catch (e) {
    console.warn('[autobi lab share] 读取对话状态失败', e)
  }
  createConversation()
}

watch([conversations, activeConversationId], () => schedulePersist(), { deep: true })

function createConversation() {
  const id = uid()
  const c = { id, title: '新对话', updatedAt: Date.now(), turns: [] }
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
    const detail = await shareApi.value.getProject()
    projectName.value = detail.name || 'AutoBI 实验室'
    apiAccessId.value = (detail.api_access_id || '').trim()
  } catch {
    projectName.value = 'AutoBI 实验室'
    apiAccessId.value = ''
    ElMessage.warning('加载项目信息失败')
  }
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || pipelineRunning.value) return

  if (!apiAccessId.value?.trim()) {
    ElMessage.error('项目缺少 API 调用 ID，无法调用网关。')
    return
  }

  const conv = activeConversation.value
  if (!conv) createConversation()
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
  const turn = c.turns[c.turns.length - 1]

  let pollTimer = null
  let backendTraceId = null

  const stopPoll = () => {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  const refreshTrace = async () => {
    if (!backendTraceId) return
    try {
      const t = await shareApi.value.getTrace(backendTraceId)
      const disp = extractTurnDisplayFromTrace(t)
      if (disp.rewrittenQuery) turn.rewrittenQuery = disp.rewrittenQuery
      if (disp.generatedSql) turn.generatedSql = disp.generatedSql
      if (disp.sqlData) turn.sqlData = disp.sqlData
      if (disp.chartSpec != null) turn.chartSpec = disp.chartSpec
      if (tracePipelineFinished(t)) {
        if (disp.biSummary && !turn.streamingSummary) turn.biSummary = disp.biSummary
      }
    } catch (e) {
      console.warn('[autobi lab share] trace 拉取失败', e)
    }
  }

  try {
    await streamAutobiLabShareGateway(
      props.token,
      {
        content: text,
        id: apiAccessId.value.trim(),
        features: { ...DEFAULT_GATEWAY_FEATURES }
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
            turn.labKind = ev.kind
            if (ev.kind === 'sql') turn.generatedSql = ev.sql
            else if (ev.kind === 'recall') turn.biSummary = (ev.items || []).map(item => [item.text, item.content || item.table].filter(Boolean).join(' — ')).join('\n\n')
            else turn.biSummary = ev.message || ''
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

async function bootstrap() {
  conversations.value = []
  activeConversationId.value = null
  await Promise.all([loadProjectMeta(), loadChatStateFromServer()])
}

watch(() => props.token, () => { void bootstrap() })

onMounted(() => { void bootstrap() })

onUnmounted(() => {
  if (persistTimer) clearTimeout(persistTimer)
  void flushPersistToApi()
})
</script>

<style scoped>
.lab-share-page {
  display: flex;
  height: 100vh;
  min-height: 560px;
  background: linear-gradient(165deg, #daf0f4 0%, #eaf8fa 35%, #eff9fb 70%, #e2f3f5 100%);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
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

.lab-session-hint {
  padding: 8px 12px 0;
  font-size: 11px;
  color: #b0b3b8;
  text-align: center;
  flex-shrink: 0;
}

.lab-center {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.lab-center-head {
  padding: 20px 24px 8px;
  text-align: center;
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

.lab-turn { margin-bottom: 20px; }
.lab-bubble { margin-bottom: 12px; }

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
  box-shadow: 0 4px 24px rgba(80, 100, 200, 0.08);
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

.lab-bubble-body.markdown-like { white-space: pre-wrap; }

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

.lab-trace-label { color: #909399; flex-shrink: 0; }

.lab-trace-code {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  word-break: break-all;
  color: #303133;
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

.lab-sql-result-table-wrap { margin-top: 8px; }

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
  box-shadow: 0 8px 32px rgba(60, 80, 180, 0.1);
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

.lab-input-field { flex: 1; }

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
</style>
