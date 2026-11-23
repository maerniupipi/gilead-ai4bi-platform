<template>
  <div v-loading="loading" class="agent-workflow-debug">
    <header class="agent-workflow-debug__top">
      <div class="agent-workflow-debug__top-left">
        <el-button text type="primary" class="agent-workflow-debug__back" @click="goDesign">
          <el-icon><ArrowLeft /></el-icon>
          返回设计
        </el-button>
        <div class="agent-workflow-debug__title-block">
          <h1 class="agent-workflow-debug__title">{{ app?.name || '工作流' }}</h1>
          <span class="agent-workflow-debug__sub">{{ version?.name || '版本' }}</span>
        </div>
      </div>
      <div class="agent-workflow-debug__tabs" role="tablist" aria-label="工作流与调试">
        <router-link
          class="agent-workflow-debug__tab"
          :to="{ name: 'AgentWorkflowDesign', params: { appId, versionId }, query: route.query }"
        >
          {{ (route.query.readonly === '1' || route.query.readonly === 'true') ? '工作流详情' : '工作流编排' }}
        </router-link>
        <span class="agent-workflow-debug__tab is-active" aria-current="page">效果测试</span>
      </div>
      <div class="agent-workflow-debug__top-right" />
    </header>

    <div class="agent-workflow-debug__body">
      <!-- 左：对话 -->
      <section class="agent-workflow-debug__col agent-workflow-debug__col--chat" aria-label="对话调试">
        <div class="agent-workflow-debug__panel-head">
          <span class="agent-workflow-debug__panel-title">对话调试</span>
          <div class="agent-workflow-debug__panel-actions">
            <el-button text size="small" @click="clearChat">清空对话</el-button>
          </div>
        </div>
        <div ref="chatScrollRef" class="agent-workflow-debug__chat-messages">
          <div v-if="!messages.length" class="agent-workflow-debug__chat-empty">
            输入问题后发送，将按当前版本工作流执行；逐节点查看实际入参、返回结果和错误日志。多个输入字段请使用 JSON。
          </div>
          <div
            v-for="(m, i) in messages"
            :key="i"
            class="agent-workflow-debug__msg"
            :class="[
              `is-${m.role}`,
              { 'is-clickable': !!m.runKey, 'is-active': m.runKey && m.runKey === selectedRunKey }
            ]"
            @click="selectConversationRun(m.runKey)"
          >
            <span class="agent-workflow-debug__msg-label">{{ m.role === 'user' ? '用户' : '工作流' }}</span>
            <div class="agent-workflow-debug__msg-bubble" :class="{ 'is-error': m.error, 'is-streaming': m.streaming }">
              {{ m.content }}
            </div>
          </div>
        </div>
        <div class="agent-workflow-debug__composer">
          <div class="agent-workflow-debug__options">
            <el-checkbox v-model="jsonInputMode" size="small">
              切换为 JSON 输入
            </el-checkbox>
            <el-checkbox v-model="streamMode" size="small">
              流式输出
            </el-checkbox>
          </div>
          <el-input
            v-if="!jsonInputMode"
            v-model="draftText"
            type="textarea"
            :rows="3"
            :placeholder="textInputPlaceholder"
            resize="none"
            @keydown.ctrl.enter.prevent="send"
            @keydown.meta.enter.prevent="send"
          />
          <el-input
            v-else
            v-model="draftJson"
            type="textarea"
            :rows="5"
            class="agent-workflow-debug__json-input"
            :placeholder="jsonInputPlaceholder"
            resize="none"
          />
          <el-button
            type="primary"
            class="agent-workflow-debug__send"
            :loading="runLoading"
            :disabled="loading || !workflowNodes.length"
            @click="send"
          >
            {{ runLoading ? '执行中' : '发送（⌘ / Ctrl + Enter）' }}
          </el-button>
        </div>
      </section>

      <!-- 中：节点执行 -->
      <section class="agent-workflow-debug__col agent-workflow-debug__col--flow" aria-label="节点执行">
        <div class="agent-workflow-debug__panel-head agent-workflow-debug__panel-head--split">
          <span class="agent-workflow-debug__panel-title">工作流任务规划</span>
          <el-radio-group v-model="executionMode" size="small">
            <el-radio-button label="debug">Debug 模式</el-radio-button>
            <el-radio-button label="run">Run 模式</el-radio-button>
          </el-radio-group>
        </div>
        <div class="agent-workflow-debug__flow-scroll">
          <div v-if="!nodeLevels.length" class="agent-workflow-debug__placeholder">暂无工作流节点</div>
          <div v-else class="agent-workflow-debug__node-chain">
            <template v-for="(level, levelIdx) in nodeLevels" :key="`lv-${levelIdx}`">
              <div class="agent-workflow-debug__level-head">
                <span>第 {{ levelIdx + 1 }} 层</span>
                <span v-if="level.length > 1" class="agent-workflow-debug__level-parallel">
                  并行 {{ level.length }} 节点
                </span>
              </div>
              <div class="agent-workflow-debug__node-level">
                <article
                  v-for="node in level"
                  :key="node.id"
                  class="agent-workflow-debug__node-card"
                  :class="nodeCardClass(node.id)"
                >
                <div class="agent-workflow-debug__node-card-head">
                  <span class="agent-workflow-debug__node-status" :class="statusDotClass(node.id)" />
                  <span class="agent-workflow-debug__node-title">{{ nodeLabel(node) }}</span>
                  <span class="agent-workflow-debug__node-phase">{{ nodePhaseLabel(node.id) }}</span>
                  <span class="agent-workflow-debug__node-kind">{{ kindLabel(node.data?.kind) }}</span>
                </div>
                <template v-if="executionMode === 'debug'">
                  <el-collapse class="agent-workflow-debug__node-collapse">
                    <el-collapse-item title="入参 / 请求参数" name="in">
                      <pre class="agent-workflow-debug__pre">{{ formatStepField(node.id, 'in') }}</pre>
                    </el-collapse-item>
                    <el-collapse-item title="出参 / 返回结果" name="out">
                      <pre class="agent-workflow-debug__pre">{{ formatStepField(node.id, 'out') }}</pre>
                    </el-collapse-item>
                    <el-collapse-item
                      v-if="node.data?.kind === 'llm'"
                      title="Prompt 快照"
                      name="prompt"
                    >
                      <pre class="agent-workflow-debug__pre">{{ formatLlmPrompt(node.id) }}</pre>
                    </el-collapse-item>
                  </el-collapse>
                </template>
                <template v-else>
                  <p class="agent-workflow-debug__muted">Run 模式仅显示节点状态；切换到 Debug 模式可查看入参/出参。</p>
                </template>
              </article>
              </div>
              <div
                v-if="levelIdx < nodeLevels.length - 1"
                class="agent-workflow-debug__node-connector"
                :class="[connectorClass(level, nodeLevels[levelIdx + 1]), { 'is-merge': isMergeConnector(level, nodeLevels[levelIdx + 1]) }]"
                aria-hidden="true"
              >
                <span class="agent-workflow-debug__node-connector-line" />
                <div
                  v-if="levelNodeLinks(level, nodeLevels[levelIdx + 1]).length"
                  class="agent-workflow-debug__node-link-list"
                >
                  <span
                    v-for="lk in levelNodeLinks(level, nodeLevels[levelIdx + 1])"
                    :key="`${lk.source}->${lk.target}`"
                    class="agent-workflow-debug__node-link-chip"
                  >
                    {{ lk.sourceLabel }} → {{ lk.targetLabel }}
                  </span>
                </div>
                <span
                  v-if="isMergeConnector(level, nodeLevels[levelIdx + 1])"
                  class="agent-workflow-debug__node-merge-label"
                >
                  {{ mergeLabel(level, nodeLevels[levelIdx + 1]) }}
                </span>
              </div>
            </template>
          </div>
        </div>
      </section>

      <!-- 右：日志 -->
      <section class="agent-workflow-debug__col agent-workflow-debug__col--log" aria-label="日志">
        <el-tabs v-model="rightTab" class="agent-workflow-debug__right-tabs">
          <el-tab-pane label="日志" name="log">
            <div class="agent-workflow-debug__log-body">
              <div v-if="!logLines.length" class="agent-workflow-debug__placeholder">
                运行后在此查看按时间顺序的执行日志。
              </div>
              <div
                v-for="(line, i) in logLines"
                :key="i"
                class="agent-workflow-debug__log-line"
                :class="`is-${line.level}`"
              >
                <span class="agent-workflow-debug__log-time">{{ line.t }}</span>
                <span class="agent-workflow-debug__log-tag">{{ line.level }}</span>
                <span class="agent-workflow-debug__log-text">{{ line.text }}</span>
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane label="模型思考过程" name="think">
            <div class="agent-workflow-debug__placeholder">
              后续可接入 LLM 推理链、工具调用等中间输出；当前为空。
            </div>
          </el-tab-pane>
        </el-tabs>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onActivated, onDeactivated, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import agentAppApi from '@/api/agentApp'
import { buildDebugInputs, workflowOutputText } from './workflowContracts.js'

const props = defineProps({
  appId: { type: String, required: true },
  versionId: { type: String, required: true }
})

const route = useRoute()
const router = useRouter()

const KIND_LABEL = {
  start: '开始',
  userInput: '用户输入',
  llm: 'LLM',
  script: '脚本',
  selector: '选择器',
  agent: '工作流',
  lab: '实验室',
  atomic: '原子能力',
  externalApi: '外部 API',
  output: '输出'
}

const loading = ref(false)
const app = ref(null)
const workflowNodes = ref([])
const workflowEdges = ref([])

const messages = ref([])
const draftText = ref('')
const draftJson = ref('')
const jsonInputMode = ref(false)
const runLoading = ref(false)
const streamMode = ref(false)
const streamingText = ref('')
const selectedRunKey = ref('')
const traceStore = ref({})
const logStore = ref({})

const tracePayload = ref(null)
const logLines = ref([])

const executionMode = ref('debug')

const rightTab = ref('log')
const chatScrollRef = ref(null)

/** 递增以取消上一次轮询（新发送或离开页面） */
const runSession = ref(0)
let activeStreamController = null
let disposed = false
let loadSequence = 0
let activatedOnce = false
let needsWorkflowRefresh = false
onBeforeUnmount(() => {
  disposed = true
  loadSequence += 1
  runSession.value += 1
  activeStreamController?.abort()
})
onDeactivated(() => {
  needsWorkflowRefresh = true
})
onActivated(() => {
  // Keep the graph associated with an ongoing run until it finishes; the next
  // send reloads the newly saved design before resolving input fields.
  if (activatedOnce && !runLoading.value) load()
  activatedOnce = true
  if (app.value && version.value) document.title = `${app.value.name} · ${version.value.name} · 效果测试 - AI4BI`
  nextTick(() => {
    const el = chatScrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
})

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

const version = computed(() => {
  const vid = Number(props.versionId)
  if (!app.value?.versions?.length || Number.isNaN(vid)) return null
  return app.value.versions.find((v) => v.id === vid) || null
})

function reachableFrom(startId, edges) {
  const adj = {}
  for (const e of edges || []) {
    const s = e.source
    const t = e.target
    if (!s || !t) continue
    if (!adj[s]) adj[s] = []
    adj[s].push(t)
  }
  const seen = new Set()
  const stack = [startId]
  while (stack.length) {
    const u = stack.pop()
    if (seen.has(u)) continue
    seen.add(u)
    for (const v of adj[u] || []) stack.push(v)
  }
  return seen
}

function topologicalIds(nodeIds, edges) {
  const ids = new Set(nodeIds)
  const indeg = {}
  const adj = {}
  for (const id of ids) {
    indeg[id] = 0
    adj[id] = []
  }
  for (const e of edges || []) {
    const s = e.source
    const t = e.target
    if (!ids.has(s) || !ids.has(t)) continue
    adj[s].push(t)
    indeg[t] += 1
  }
  const q = [...ids].filter((id) => indeg[id] === 0)
  const out = []
  while (q.length) {
    const u = q.shift()
    out.push(u)
    for (const v of adj[u] || []) {
      indeg[v] -= 1
      if (indeg[v] === 0) q.push(v)
    }
  }
  return out.length === ids.size ? out : [...ids]
}

function topologicalLevels(nodeIds, edges) {
  const ids = new Set(nodeIds)
  const indeg = {}
  const adj = {}
  for (const id of ids) {
    indeg[id] = 0
    adj[id] = []
  }
  for (const e of edges || []) {
    const s = e.source
    const t = e.target
    if (!ids.has(s) || !ids.has(t)) continue
    adj[s].push(t)
    indeg[t] += 1
  }
  const q = [...ids].filter((id) => indeg[id] === 0)
  const levels = []
  let seen = 0
  while (q.length) {
    const size = q.length
    const lv = []
    for (let i = 0; i < size; i += 1) {
      const u = q.shift()
      lv.push(u)
      seen += 1
      for (const v of adj[u] || []) {
        indeg[v] -= 1
        if (indeg[v] === 0) q.push(v)
      }
    }
    levels.push(lv)
  }
  if (seen !== ids.size) return [topologicalIds([...ids], edges)]
  return levels
}

const nodeLevels = computed(() => {
  const nodes = workflowNodes.value || []
  const edges = workflowEdges.value || []
  const start = nodes.find((n) => n.data?.kind === 'start')
  if (!start) return nodes.length ? [nodes] : []
  const reach = reachableFrom(start.id, edges)
  const filtered = nodes.filter((n) => reach.has(n.id))
  const levels = topologicalLevels(
    filtered.map((n) => n.id),
    edges
  )
  const byId = Object.fromEntries(filtered.map((n) => [n.id, n]))
  return levels.map((lv) => lv.map((id) => byId[id]).filter(Boolean)).filter((lv) => lv.length)
})

const stepsByNodeId = computed(() => {
  const m = {}
  for (const s of tracePayload.value?.steps || []) {
    if (s && s.node_id) m[s.node_id] = s
  }
  return m
})

function kindLabel(k) {
  return KIND_LABEL[k] || k || '—'
}

function nodeLabel(node) {
  return node.data?.label || node.data?.var_name || node.id
}

function stepFor(nodeId) {
  return stepsByNodeId.value[nodeId] || null
}

/** 结合拓扑顺序与执行记录，区分等待 / 运行中 / 已完成 / 失败 / 未执行 */
function nodePhase(nodeId) {
  const trace = tracePayload.value
  const st = stepFor(nodeId)
  if (st) {
    if (st.status === 'running') return 'running'
    if (st.status === 'done') return 'done'
    if (st.status === 'error') return 'error'
  }
  if (!trace) return 'idle'
  if (trace.status === 'running') {
    return 'pending'
  }
  if (trace.status === 'error') {
    return st ? 'error' : 'skipped'
  }
  if (trace.status === 'done') {
    return st ? 'done' : 'skipped'
  }
  return 'idle'
}

function nodePhaseLabel(nodeId) {
  const m = {
    idle: '未开始',
    pending: '等待执行',
    running: '执行中',
    done: '已完成',
    error: '失败',
    skipped: '未执行'
  }
  return m[nodePhase(nodeId)] || '—'
}

function runStatusText(status) {
  const m = {
    running: '执行中',
    done: '已完成',
    error: '失败',
    pending: '等待执行',
    skipped: '未执行'
  }
  return m[status] || status || '—'
}

function statusDotClass(nodeId) {
  const ph = nodePhase(nodeId)
  if (ph === 'done') return 'is-done'
  if (ph === 'error') return 'is-error'
  if (ph === 'running') return 'is-run'
  if (ph === 'pending') return 'is-pending'
  if (ph === 'skipped') return 'is-skipped'
  return 'is-idle'
}

function nodeCardClass(nodeId) {
  const ph = nodePhase(nodeId)
  if (ph === 'error') return 'is-error'
  if (ph === 'done') return 'is-done'
  if (ph === 'running') return 'is-running'
  if (ph === 'pending') return 'is-pending'
  if (ph === 'skipped') return 'is-skipped'
  return ''
}

function connectorClass(fromLevel, toLevel) {
  const fromDone = (fromLevel || []).some((n) => nodePhase(n.id) === 'done')
  const toActive = (toLevel || []).some((n) => {
    const ph = nodePhase(n.id)
    return ph === 'running' || ph === 'pending' || ph === 'done'
  })
  if (fromDone && toActive) return 'is-active'
  return ''
}

function isMergeConnector(fromLevel, toLevel) {
  return (fromLevel?.length || 0) > 1 && (toLevel?.length || 0) === 1
}

function mergeLabel(fromLevel, toLevel) {
  return `汇聚 ${fromLevel.length} → ${toLevel.length}`
}

function levelNodeLinks(fromLevel, toLevel) {
  const fromIds = new Set((fromLevel || []).map((n) => n.id))
  const toIds = new Set((toLevel || []).map((n) => n.id))
  const nodeMap = Object.fromEntries((workflowNodes.value || []).map((n) => [n.id, n]))
  return (workflowEdges.value || [])
    .filter((e) => fromIds.has(e.source) && toIds.has(e.target))
    .map((e) => ({
      source: e.source,
      target: e.target,
      sourceLabel: nodeLabel(nodeMap[e.source] || { id: e.source, data: {} }),
      targetLabel: nodeLabel(nodeMap[e.target] || { id: e.target, data: {} })
    }))
}

function formatStepField(nodeId, which) {
  const ph = nodePhase(nodeId)
  if (ph === 'idle' || ph === 'pending') {
    return which === 'in' ? '（等待执行，尚无入参快照）' : '（等待执行）'
  }
  if (ph === 'skipped') return tracePayload.value?.status === 'done' ? '（本次执行未选中此分支或节点不可达）' : '（上游失败或已中止，本节点未执行）'
  const s = stepFor(nodeId)
  if (!s) return '（无步骤记录）'
  if (which === 'in') {
    if (s.input_snapshot != null) return JSON.stringify(s.input_snapshot, null, 2)
    return '（无入参快照）'
  }
  if (s.output_snapshot != null) return JSON.stringify(s.output_snapshot, null, 2)
  if (s.error) return s.error
  if (ph === 'running') return '（执行中…）'
  return '（无输出快照）'
}

function rebuildLogFromTrace(trace) {
  if (!trace) return []
  const lines = []
  const headT = new Date().toISOString().slice(11, 23)
  lines.push({
    t: headT,
    level: 'info',
    text: `执行记录 · ${runStatusText(trace.status)}`
  })
  for (const st of trace.steps || []) {
    const tag = st.status === 'error' ? 'error' : 'info'
    const name = st.label || st.var_name || st.node_id
    const ms = st.elapsed_ms != null ? ` · ${st.elapsed_ms}ms` : ''
    const err = st.error ? ` · ${st.error}` : ''
    lines.push({ t: '—', level: tag, text: `${name} [${runStatusText(st.status)}]${ms}${err}` })
  }
  if (trace.status === 'error' && trace.error) {
    lines.push({ t: '—', level: 'error', text: trace.error })
  }
  return lines
}

function updateRunTrace(runKey, trace) {
  if (!runKey) return
  traceStore.value = {
    ...traceStore.value,
    [runKey]: trace
  }
  if (selectedRunKey.value === runKey) {
    tracePayload.value = trace
  }
}

function updateRunLogs(runKey, lines) {
  if (!runKey) return
  logStore.value = {
    ...logStore.value,
    [runKey]: lines || []
  }
  if (selectedRunKey.value === runKey) {
    logLines.value = lines || []
  }
}

function selectConversationRun(runKey) {
  if (!runKey || !traceStore.value[runKey]) return
  selectedRunKey.value = runKey
  tracePayload.value = traceStore.value[runKey] || null
  logLines.value = logStore.value[runKey] || []
}

const inputFields = computed(() => workflowNodes.value.find(n => n.data?.kind === 'userInput')?.data?.fields || [{ variable: 'input', required: true }])
const textInputPlaceholder = computed(() => {
  const field = inputFields.value.find(f => !f.hidden) || inputFields.value[0]
  return `输入「${field?.display || field?.variable || 'input'}」；Enter 换行，⌘ / Ctrl + Enter 发送`
})
const jsonInputPlaceholder = computed(() => JSON.stringify(Object.fromEntries(inputFields.value.filter(f => !f.hidden).map(f => [f.variable, f.default ?? ''])), null, 2))

function buildInputsFromDraft() {
  return buildDebugInputs({ nodes: workflowNodes.value, text: draftText.value ?? '', json: draftJson.value, jsonMode: jsonInputMode.value })
}

function formatLlmPrompt(nodeId) {
  const snapshot = stepFor(nodeId)?.input_snapshot
  if (!snapshot) return '（执行后显示解析后的 Prompt）'
  return JSON.stringify({ system_prompt: snapshot.system_prompt, user_prompt: snapshot.user_prompt, input_values: snapshot.input_values }, null, 2)
}

async function send() {
  if (runLoading.value || loading.value) return
  if (needsWorkflowRefresh && !await load()) return
  const id = Number(props.appId)
  const vid = Number(props.versionId)
  if (Number.isNaN(id) || Number.isNaN(vid)) return

  let inputs
  try {
    inputs = buildInputsFromDraft()
  } catch (e) {
    ElMessage.warning(e.message || '输入无效')
    return
  }

  const runKey = `${Date.now()}-${runSession.value + 1}`
  if (!jsonInputMode.value) {
    messages.value.push({ role: 'user', content: draftText.value, runKey })
    draftText.value = ''
  } else {
    messages.value.push({ role: 'user', content: draftJson.value, runKey })
    draftJson.value = ''
  }

  const sid = (runSession.value += 1)
  selectedRunKey.value = runKey
  runLoading.value = true

  if (streamMode.value) {
    await runStreamMode(id, vid, inputs, sid, runKey)
    return
  }

  const pendingTrace = {
    run_id: '',
    status: 'running',
    steps: [],
    output: null,
    error: null
  }
  const pendingLogs = [
    {
      t: new Date().toISOString().slice(11, 23),
      level: 'info',
      text: '已提交执行，正在获取节点执行状态…'
    }
  ]
  updateRunTrace(runKey, pendingTrace)
  updateRunLogs(runKey, pendingLogs)
  try {
    const res = await agentAppApi.runWorkflow(id, vid, { inputs })
    if (sid !== runSession.value) return

    if (!res.run_id) {
      throw new Error('未返回 run_id')
    }

    let trace = await agentAppApi.getRunTrace(id, res.run_id)
    while (
      sid === runSession.value &&
      trace &&
      trace.status === 'running'
    ) {
      updateRunTrace(runKey, trace)
      updateRunLogs(runKey, rebuildLogFromTrace(trace))
      await sleep(400)
      trace = await agentAppApi.getRunTrace(id, res.run_id)
    }

    if (sid !== runSession.value) return

    updateRunTrace(runKey, trace)
    updateRunLogs(runKey, rebuildLogFromTrace(trace))

    let outputText = ''
    if (trace.status === 'error') {
      outputText = trace.error || '执行失败'
      messages.value.push({
        role: 'assistant',
        content: outputText,
        runKey,
        error: true
      })
    } else {
      outputText = workflowOutputText(trace.output)
      if (!outputText) {
        outputText = '（无文本输出）'
      }
      messages.value.push({
        role: 'assistant',
        content: outputText,
        runKey
      })
    }
  } catch (e) {
    if (sid !== runSession.value) return
    const msg = e?.message || e?.msg || '请求失败'
    updateRunTrace(runKey, { ...(traceStore.value[runKey] || pendingTrace), status: 'error', error: msg })
    const oldLogs = logStore.value[runKey] || []
    updateRunLogs(runKey, [
      ...oldLogs,
      { t: new Date().toISOString().slice(11, 23), level: 'error', text: msg }
    ])
    messages.value.push({ role: 'assistant', content: msg, error: true, runKey })
    ElMessage.error(msg)
  } finally {
    if (sid === runSession.value) {
      runLoading.value = false
      await nextTick()
      const el = chatScrollRef.value
      if (el) el.scrollTop = el.scrollHeight
    }
  }
}

function clearChat() {
  runSession.value += 1
  activeStreamController?.abort()
  activeStreamController = null
  runLoading.value = false
  messages.value = []
  logLines.value = []
  tracePayload.value = null
  selectedRunKey.value = ''
  traceStore.value = {}
  logStore.value = {}
  streamingText.value = ''
}

async function runStreamMode(id, vid, inputs, sid, runKey) {
  const pendingTrace = { run_id: 'stream', status: 'running', steps: [], output: null, error: null }
  updateRunTrace(runKey, pendingTrace)
  updateRunLogs(runKey, rebuildLogFromTrace(pendingTrace))
  messages.value.push({ role: 'assistant', content: '', streaming: true, runKey })
  const reply = messages.value[messages.value.length - 1]
  const controller = new AbortController()
  activeStreamController = controller
  try {
    const result = await agentAppApi.runWorkflowStream(id, vid, { inputs }, text => {
      if (sid === runSession.value) reply.content = text
    }, progress => {
      if (sid !== runSession.value || !progress?.node_id) return
      const node = workflowNodes.value.find(n => n.id === progress.node_id)
      const existing = pendingTrace.steps.find(step => step.node_id === progress.node_id)
      const step = {
        ...(existing || {}), ...progress,
        node_id: progress.node_id,
        kind: progress.kind || node?.data?.kind || '',
        label: progress.label || nodeLabel(node || { id: progress.node_id }),
        input_snapshot: progress.input_snapshot ?? existing?.input_snapshot ?? null,
        output_snapshot: progress.output_snapshot ?? progress.output ?? existing?.output_snapshot ?? null
      }
      if (existing) Object.assign(existing, step)
      else pendingTrace.steps.push(step)
      const nextTrace = { ...pendingTrace, steps: [...pendingTrace.steps] }
      updateRunTrace(runKey, nextTrace)
      updateRunLogs(runKey, rebuildLogFromTrace(nextTrace))
    }, controller.signal)
    if (sid !== runSession.value) return
    const trace = { ...pendingTrace, ...result, status: 'done', steps: result.steps || [...pendingTrace.steps] }
    updateRunTrace(runKey, trace)
    updateRunLogs(runKey, rebuildLogFromTrace(trace))
    reply.content = workflowOutputText(result.output) || '（无文本输出）'
  } catch (e) {
    if (sid !== runSession.value) return
    const msg = e?.message || '流式输出失败'
    reply.error = true
    reply.content = msg
    const trace = { ...pendingTrace, status: 'error', error: msg, steps: [...pendingTrace.steps] }
    updateRunTrace(runKey, trace)
    updateRunLogs(runKey, rebuildLogFromTrace(trace))
    ElMessage.error(msg)
  } finally {
    reply.streaming = false
    if (activeStreamController === controller) activeStreamController = null
    if (sid === runSession.value) {
      runLoading.value = false
      await nextTick()
      const el = chatScrollRef.value
      if (el) el.scrollTop = el.scrollHeight
    }
  }
}

function goDesign() {
  router.push({
    name: 'AgentWorkflowDesign',
    params: { appId: props.appId, versionId: props.versionId },
    query: { ...route.query }
  })
}

async function load() {
  const sequence = ++loadSequence
  const id = Number(props.appId)
  const vid = Number(props.versionId)
  if (Number.isNaN(id) || Number.isNaN(vid)) {
    ElMessage.warning('无效的应用或版本')
    router.replace('/agent-platform/agents')
    return false
  }
  loading.value = true
  try {
    const [data, wf] = await Promise.all([
      agentAppApi.getAgentApp(id),
      agentAppApi.getWorkflow(id, vid)
    ])
    if (disposed || sequence !== loadSequence) return false
    app.value = data
    const v = data.versions?.find((x) => x.id === vid)
    if (!v) {
      ElMessage.warning('未找到该版本')
      router.replace({ name: 'AgentAppVersions', params: { appId: props.appId } })
      return false
    }
    const w = wf.workflow
    if (w?.nodes?.length) {
      workflowNodes.value = JSON.parse(JSON.stringify(w.nodes))
      workflowEdges.value = JSON.parse(JSON.stringify(w.edges || []))
    } else {
      workflowNodes.value = []
      workflowEdges.value = []
    }
    needsWorkflowRefresh = false
    document.title = `${data.name} · ${v.name} · 效果测试 - AI4BI`
    return true
  } catch (e) {
    if (disposed || sequence !== loadSequence) return false
    ElMessage.error(e.message || '加载失败')
    router.replace('/agent-platform/agents')
    return false
  } finally {
    if (!disposed && sequence === loadSequence) loading.value = false
  }
}

watch(
  () => [props.appId, props.versionId],
  () => { clearChat(); load() }
)

onMounted(() => {
  if (route.meta?.title) {
    document.title = `${route.meta.title} - AI4BI`
  }
  load()
})
</script>

<style scoped>
.agent-workflow-debug {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  min-width: 0;
  background: #f8faf9;
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}

.agent-workflow-debug__top {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 16px;
  padding: 0 20px;
  min-height: 56px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
  background: linear-gradient(180deg, #fff 0%, #fafcfb 100%);
}

.agent-workflow-debug__top-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.agent-workflow-debug__back {
  flex-shrink: 0;
}

.agent-workflow-debug__title-block {
  min-width: 0;
}

.agent-workflow-debug__title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #101828;
  line-height: 1.3;
  letter-spacing: -0.02em;
}

.agent-workflow-debug__sub {
  font-size: 12px;
  color: #667085;
}

.agent-workflow-debug__tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border-radius: 10px;
  background: rgba(61, 141, 130, 0.08);
  border: 1px solid rgba(61, 141, 130, 0.12);
}

.agent-workflow-debug__tab {
  padding: 8px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #475467;
  text-decoration: none;
  transition:
    background 0.15s ease,
    color 0.15s ease;
}

.agent-workflow-debug__tab:hover {
  color: var(--el-color-primary);
  background: rgba(255, 255, 255, 0.7);
}

.agent-workflow-debug__tab.is-active {
  background: #fff;
  color: var(--el-color-primary);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}

.agent-workflow-debug__body {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(320px, 1.15fr) minmax(240px, 0.95fr);
  gap: 0;
}

.agent-workflow-debug__col {
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-right: 1px solid rgba(15, 23, 42, 0.06);
}

.agent-workflow-debug__col--log {
  border-right: none;
}

.agent-workflow-debug__panel-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.agent-workflow-debug__panel-head--split {
  gap: 12px;
  flex-wrap: wrap;
}

.agent-workflow-debug__panel-title {
  font-size: 14px;
  font-weight: 700;
  color: #101828;
}

.agent-workflow-debug__panel-actions {
  display: flex;
  gap: 8px;
}

.agent-workflow-debug__chat-messages {
  flex: 1 1 auto;
  min-height: 120px;
  overflow-y: auto;
  padding: 16px;
  background: #fafcfb;
}

.agent-workflow-debug__chat-empty {
  font-size: 13px;
  color: #98a2b3;
  line-height: 1.55;
  padding: 8px 4px;
}

.agent-workflow-debug__msg {
  margin-bottom: 14px;
}

.agent-workflow-debug__msg.is-clickable {
  cursor: pointer;
}

.agent-workflow-debug__msg.is-active .agent-workflow-debug__msg-bubble {
  border-color: rgba(var(--el-color-primary-rgb), 0.45);
  box-shadow: 0 0 0 1px rgba(var(--el-color-primary-rgb), 0.18);
}

.agent-workflow-debug__msg-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #98a2b3;
  margin-bottom: 4px;
}

.agent-workflow-debug__msg-bubble {
  display: inline-block;
  max-width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  color: #1d2939;
  background: #fff;
  border: 1px solid rgba(15, 23, 42, 0.08);
  white-space: pre-wrap;
  word-break: break-word;
}

.agent-workflow-debug__msg.is-user .agent-workflow-debug__msg-bubble {
  background: rgba(var(--el-color-primary-rgb), 0.08);
  border-color: rgba(var(--el-color-primary-rgb), 0.2);
}

.agent-workflow-debug__msg-bubble.is-error {
  background: #fef3f2;
  border-color: #fecdca;
  color: #b42318;
}

.agent-workflow-debug__msg-bubble.is-streaming {
  background: #f5f7fa;
  border-color: #e4e7ed;
  min-height: 24px;
  position: relative;
  overflow: hidden;
}

.agent-workflow-debug__msg-bubble.is-streaming::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(200, 200, 200, 0.2),
    transparent
  );
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

.agent-workflow-debug__composer {
  flex-shrink: 0;
  padding: 12px 16px 16px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-workflow-debug__options {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.agent-workflow-debug__json-toggle {
  align-self: flex-start;
  margin-right: 16px;
}

.agent-workflow-debug__json-toggle:last-of-type {
  margin-right: 0;
}

.agent-workflow-debug__json-input :deep(.el-textarea__inner) {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

.agent-workflow-debug__send {
  align-self: flex-end;
  border-radius: 10px;
  font-weight: 600;
}

.agent-workflow-debug__flow-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  background: linear-gradient(180deg, #f8faf9 0%, #f3f6f4 100%);
}

.agent-workflow-debug__placeholder {
  font-size: 13px;
  color: #98a2b3;
  line-height: 1.55;
  padding: 12px 8px;
}

.agent-workflow-debug__node-chain {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  max-width: 780px;
  margin: 0 auto;
}

.agent-workflow-debug__node-level {
  display: flex;
  align-items: stretch;
  justify-content: center;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
}

.agent-workflow-debug__level-head {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #667085;
  font-weight: 600;
}

.agent-workflow-debug__level-parallel {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(46, 144, 250, 0.1);
  color: #175cd3;
}

.agent-workflow-debug__node-card {
  width: 248px;
  min-width: 248px;
  max-width: 248px;
  flex: 0 0 auto;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: #fff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  padding: 12px 14px;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.agent-workflow-debug__node-card.is-running {
  border-color: rgba(46, 144, 250, 0.45);
  box-shadow: 0 0 0 1px rgba(46, 144, 250, 0.12);
}

.agent-workflow-debug__node-card.is-done {
  border-color: rgba(22, 163, 74, 0.35);
}

.agent-workflow-debug__node-card.is-pending {
  border-style: dashed;
  border-color: rgba(152, 162, 179, 0.45);
  opacity: 0.92;
}

.agent-workflow-debug__node-card.is-skipped {
  border-style: dashed;
  opacity: 0.75;
}

.agent-workflow-debug__node-card.is-error {
  border-color: rgba(180, 35, 24, 0.45);
  box-shadow: 0 0 0 1px rgba(180, 35, 24, 0.08);
}

.agent-workflow-debug__node-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.agent-workflow-debug__node-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #d0d5dd;
}

.agent-workflow-debug__node-status.is-idle {
  background: #d0d5dd;
}
.agent-workflow-debug__node-status.is-pending {
  background: #98a2b3;
}
.agent-workflow-debug__node-status.is-run {
  background: #2e90fa;
  box-shadow: 0 0 0 3px rgba(46, 144, 250, 0.25);
  animation: agent-wf-pulse 1.2s ease-in-out infinite;
}
.agent-workflow-debug__node-status.is-done {
  background: #16a34a;
}
.agent-workflow-debug__node-status.is-error {
  background: #b42318;
}
.agent-workflow-debug__node-status.is-skipped {
  background: #e4e7ec;
}

@keyframes agent-wf-pulse {
  50% {
    opacity: 0.65;
  }
}

.agent-workflow-debug__node-title {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 14px;
  font-weight: 700;
  color: #101828;
}

.agent-workflow-debug__node-phase {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.06);
  color: #475467;
}

.agent-workflow-debug__node-card.is-running .agent-workflow-debug__node-phase {
  background: rgba(46, 144, 250, 0.15);
  color: #175cd3;
}

.agent-workflow-debug__node-card.is-done .agent-workflow-debug__node-phase {
  background: rgba(22, 163, 74, 0.12);
  color: #15803d;
}

.agent-workflow-debug__node-card.is-error .agent-workflow-debug__node-phase {
  background: rgba(180, 35, 24, 0.1);
  color: #b42318;
}

.agent-workflow-debug__node-card.is-pending .agent-workflow-debug__node-phase {
  background: rgba(152, 162, 179, 0.2);
  color: #667085;
}

.agent-workflow-debug__node-card.is-skipped .agent-workflow-debug__node-phase {
  background: rgba(15, 23, 42, 0.04);
  color: #98a2b3;
}

.agent-workflow-debug__node-kind {
  font-size: 11px;
  font-weight: 600;
  color: #667085;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.04);
}

.agent-workflow-debug__node-collapse {
  border: none;
  --el-collapse-header-height: 36px;
}

.agent-workflow-debug__node-collapse :deep(.el-collapse-item__header) {
  font-size: 12px;
  font-weight: 600;
  color: #475467;
  background: transparent;
}

.agent-workflow-debug__node-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
}

.agent-workflow-debug__pre {
  margin: 0;
  padding: 8px 10px;
  font-size: 11px;
  line-height: 1.45;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow: auto;
}

.agent-workflow-debug__muted {
  margin: 0;
  font-size: 12px;
  color: #98a2b3;
  line-height: 1.5;
}

.agent-workflow-debug__node-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 6px 0;
  width: 100%;
  gap: 6px;
}

.agent-workflow-debug__node-connector-line {
  width: 2px;
  height: 20px;
  border-radius: 1px;
  background: linear-gradient(180deg, rgba(152, 162, 179, 0.45), rgba(152, 162, 179, 0.15));
}

.agent-workflow-debug__node-connector.is-active .agent-workflow-debug__node-connector-line {
  background: linear-gradient(180deg, rgba(22, 163, 74, 0.55), rgba(61, 141, 130, 0.35));
}

.agent-workflow-debug__node-link-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  max-width: 100%;
  padding: 0 8px;
}

.agent-workflow-debug__node-link-chip {
  font-size: 11px;
  font-weight: 600;
  color: #475467;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.12);
  background: rgba(255, 255, 255, 0.75);
}

.agent-workflow-debug__node-connector.is-merge .agent-workflow-debug__node-connector-line {
  height: 24px;
}

.agent-workflow-debug__node-merge-label {
  font-size: 11px;
  font-weight: 700;
  color: #0f766e;
  padding: 2px 9px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.12);
  border: 1px solid rgba(15, 118, 110, 0.18);
}

.agent-workflow-debug__right-tabs {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.agent-workflow-debug__right-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 12px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.agent-workflow-debug__right-tabs :deep(.el-tabs__content) {
  flex: 1 1 auto;
  min-height: 0;
  padding: 0;
}

.agent-workflow-debug__right-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.agent-workflow-debug__log-body {
  height: 100%;
  min-height: 200px;
  overflow-y: auto;
  padding: 12px 14px;
  font-size: 12px;
}

.agent-workflow-debug__log-line {
  display: grid;
  grid-template-columns: 72px 48px 1fr;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.04);
  align-items: start;
}

.agent-workflow-debug__log-time {
  font-family: ui-monospace, monospace;
  color: #98a2b3;
}

.agent-workflow-debug__log-tag {
  font-weight: 700;
  text-transform: uppercase;
  font-size: 10px;
}

.agent-workflow-debug__log-line.is-info .agent-workflow-debug__log-tag {
  color: #16a34a;
}

.agent-workflow-debug__log-line.is-error .agent-workflow-debug__log-tag {
  color: #b42318;
}

.agent-workflow-debug__log-text {
  color: #344054;
  line-height: 1.45;
  word-break: break-word;
}

@media (max-width: 1100px) {
  .agent-workflow-debug__body {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(280px, auto) minmax(320px, 1fr) minmax(200px, auto);
  }

  .agent-workflow-debug__col {
    border-right: none;
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
  }

  .agent-workflow-debug__col--log {
    border-bottom: none;
  }
}
</style>
