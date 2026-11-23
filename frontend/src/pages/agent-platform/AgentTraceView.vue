<template>
  <div class="trace-view-page">
    <!-- Header -->
    <header class="trace-view-head">
      <div class="trace-view-head-row">
        <div class="trace-view-head-left">
          <el-button text type="primary" @click="router.push({ name: 'AgentTraceLookup' })">
            <el-icon><ArrowLeft /></el-icon>
            返回列表
          </el-button>
          <h1 class="trace-view-title">运行日志详情</h1>
        </div>
      </div>
      <div v-if="trace" class="trace-meta">
        <div class="trace-meta-line">
          <span class="label">Trace ID</span>
          <code class="trace-id">{{ trace.trace_id }}</code>
          <el-button size="small" @click="copyId">复制</el-button>
        </div>
        <div class="trace-meta-row">
          <div class="trace-meta-line">
            <span class="label">类型</span>
            <el-tag :type="trace.type === 'lab' ? '' : 'primary'" size="small">
              {{ trace.type === 'lab' ? '实验室' : '工作流' }}
            </el-tag>
          </div>
          <div class="trace-meta-line">
            <span class="label">应用</span>
            <span>{{ trace.app_name || trace.project_name || '-' }}</span>
          </div>
          <div class="trace-meta-line">
            <span class="label">状态</span>
            <el-tag :type="statusTag(trace.status)" size="small">{{ statusText(trace.status) }}</el-tag>
          </div>
          <div class="trace-meta-line">
            <span class="label">耗时</span>
            <span>{{ trace.elapsed_ms != null ? trace.elapsed_ms + 'ms' : '-' }}</span>
          </div>
          <div class="trace-meta-line muted">
            <span class="label">时间</span>
            <span>{{ formatTime(trace.created_at || trace.updated_at) }}</span>
          </div>
        </div>
        <div v-if="trace.error" class="trace-meta-error">
          <span class="label">错误</span>
          <span class="error-text">{{ trace.error }}</span>
        </div>
      </div>
      <div v-else-if="!loading && errorMsg" class="trace-error">{{ errorMsg }}</div>
    </header>

    <el-skeleton v-if="loading" :rows="8" animated class="trace-skeleton" />

    <!-- Body: 三栏/两栏布局 -->
    <div v-else-if="trace" class="trace-view-body" :style="gridStyle">
      <!-- 左栏：调用链（仅嵌套工作流时显示） -->
      <aside v-if="showCallChain" class="trace-col trace-col--chain">
        <div class="trace-col-head">调用链</div>
        <div class="trace-chain-tree">
          <div
            v-for="item in callChainItems"
            :key="item.trace_id"
            class="trace-chain-node"
            :class="{ 'is-active': item.trace_id === currentTraceId }"
            @click="switchTrace(item.trace_id)"
          >
            <span class="trace-chain-status" :class="`is-${item.status}`" />
            <span class="trace-chain-name">{{ item.app_name || item.trace_id }}</span>
          </div>
        </div>
      </aside>

      <!-- 中栏：节点卡片 -->
      <section class="trace-col trace-col--cards">
        <div class="trace-col-head">
          {{ trace.type === 'lab' ? '流水线步骤' : '节点执行' }}
        </div>
        <div class="trace-cards-scroll">
          <!-- Lab 类型：复用 AutobiLabStepCards -->
          <AutobiLabStepCards
            v-if="trace.type === 'lab'"
            :rows="labSteps"
            show-step-uuid
          />

          <!-- Workflow 类型：节点执行卡片 -->
          <div v-else class="trace-node-chain">
            <div v-if="!waveGroups.length" class="trace-empty">暂无节点执行记录</div>
            <template v-for="(wave, wi) in waveGroups" :key="`wave-${wi}`">
              <div class="trace-wave-head">
                <span>第 {{ wi + 1 }} 波</span>
                <span v-if="wave.length > 1" class="trace-wave-parallel">
                  并行 {{ wave.length }} 节点
                </span>
              </div>
              <div class="trace-wave-nodes">
                <article
                  v-for="step in wave"
                  :key="step.node_id"
                  class="trace-node-card"
                  :class="`is-${step.status}`"
                >
                  <div class="trace-node-card-head">
                    <span class="trace-node-status" :class="`is-${stepDotClass(step.status)}`" />
                    <span class="trace-node-title">{{ step.label || step.var_name || step.node_id }}</span>
                    <el-tag size="small" :type="kindTagType(step.kind)" class="trace-node-kind">
                      {{ kindLabel(step.kind) }}
                    </el-tag>
                    <span v-if="step.elapsed_ms != null" class="trace-node-elapsed">{{ step.elapsed_ms }}ms</span>
                  </div>
                  <el-collapse v-if="step.status !== 'running'" class="trace-node-collapse">
                    <el-collapse-item title="入参快照" name="input">
                      <pre class="trace-pre">{{ pretty(step.input_snapshot) }}</pre>
                    </el-collapse-item>
                    <el-collapse-item title="出参快照" name="output">
                      <pre class="trace-pre">{{ pretty(step.output_snapshot) }}</pre>
                    </el-collapse-item>
                    <el-collapse-item v-if="step.error" title="错误信息" name="error">
                      <pre class="trace-pre trace-pre--error">{{ step.error }}</pre>
                    </el-collapse-item>
                  </el-collapse>
                  <div v-if="step.child_trace_ids && step.child_trace_ids.length" class="trace-node-children">
                    <el-button
                      v-for="cid in step.child_trace_ids"
                      :key="cid"
                      text
                      size="small"
                      type="primary"
                      @click="switchTrace(cid)"
                    >
                      查看子工作流
                    </el-button>
                  </div>
                </article>
              </div>
            </template>
          </div>
        </div>
      </section>

      <!-- 右栏：日志 -->
      <section class="trace-col trace-col--log">
        <div class="trace-col-head">日志</div>
        <div class="trace-log-body">
          <div class="trace-log-overview">
            <div class="trace-log-stat">
              <span class="trace-log-stat-val">{{ trace.elapsed_ms || 0 }}ms</span>
              <span class="trace-log-stat-label">总耗时</span>
            </div>
            <div class="trace-log-stat">
              <span class="trace-log-stat-val">{{ stepCount }}</span>
              <span class="trace-log-stat-label">步骤数</span>
            </div>
            <div class="trace-log-stat">
              <span class="trace-log-stat-val">{{ errorCount }}</span>
              <span class="trace-log-stat-label">错误数</span>
            </div>
          </div>
          <div v-if="!logLines.length" class="trace-empty">暂无日志</div>
          <div
            v-for="(line, i) in logLines"
            :key="i"
            class="trace-log-line"
            :class="`is-${line.level}`"
          >
            <span class="trace-log-time">{{ line.t }}</span>
            <span class="trace-log-tag">{{ line.level }}</span>
            <span class="trace-log-text">{{ line.text }}</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getTrace } from '../../api/workflowTrace'
import AutobiLabStepCards from '../../components/AutobiLabStepCards.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const errorMsg = ref('')
const trace = ref(null)
const currentTraceId = ref('')

const KIND_LABELS = {
  start: '开始',
  userInput: '用户输入',
  llm: 'LLM',
  script: '脚本',
  selector: '选择器',
  agent: '智能体',
  lab: '实验室',
  atomic: '原子能力',
  externalApi: '外部API',
  output: '输出'
}

function kindLabel(k) {
  return KIND_LABELS[k] || k || '未知'
}

function kindTagType(k) {
  if (k === 'llm') return 'primary'
  if (k === 'agent') return 'success'
  if (k === 'script') return 'warning'
  if (k === 'atomic') return 'danger'
  if (k === 'lab') return ''
  if (k === 'externalApi') return 'info'
  return 'info'
}

function statusTag(s) {
  if (s === 'done') return 'success'
  if (s === 'error') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}

function statusText(s) {
  if (s === 'done') return '已完成'
  if (s === 'error') return '失败'
  if (s === 'running') return '运行中'
  return s || '-'
}

function formatTime(ms) {
  if (ms == null) return ''
  return new Date(ms).toLocaleString()
}

function pretty(v) {
  if (v === null || v === undefined) return '-'
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function stepDotClass(status) {
  if (status === 'done') return 'done'
  if (status === 'error') return 'error'
  if (status === 'running') return 'run'
  return 'idle'
}

// Lab steps normalization
const labSteps = computed(() => {
  const steps = trace.value?.steps
  if (!Array.isArray(steps)) return []
  return steps.map(s => ({
    stepUuid: s.step_uuid,
    meta: {
      stepId: s.step_id,
      title: s.title,
      apiKey: s.api_key,
      color: s.color
    },
    status: s.status,
    request: s.request,
    response: s.response,
    error: s.error,
    durationMs: s.duration_ms
  }))
})

// Wave grouping for workflow steps
const waveGroups = computed(() => {
  const steps = trace.value?.steps
  if (!Array.isArray(steps) || !steps.length) return []

  // Group steps by topological wave using nodes/edges
  const nodes = trace.value?.nodes
  const edges = trace.value?.edges
  if (!nodes || !edges) {
    // Fallback: all steps in one wave
    return [steps]
  }

  // Compute topological levels for nodes that have steps
  const stepNodeIds = new Set(steps.map(s => s.node_id).filter(Boolean))
  const nodeIds = new Set(nodes.map(n => n.id).filter(id => stepNodeIds.has(id)))

  const indeg = {}
  const adj = {}
  for (const id of nodeIds) {
    indeg[id] = 0
    adj[id] = []
  }
  for (const e of edges) {
    const s = e.source
    const t = e.target
    if (!nodeIds.has(s) || !nodeIds.has(t)) continue
    adj[s].push(t)
    indeg[t] = (indeg[t] || 0) + 1
  }

  const levels = []
  let q = [...nodeIds].filter(id => indeg[id] === 0)
  while (q.length) {
    const lv = [...q]
    levels.push(lv)
    const next = []
    for (const u of q) {
      for (const v of adj[u] || []) {
        indeg[v] -= 1
        if (indeg[v] === 0) next.push(v)
      }
    }
    q = next
  }

  // Map steps to levels
  const stepByNode = {}
  for (const s of steps) {
    stepByNode[s.node_id] = s
  }

  const groups = []
  for (const lv of levels) {
    const ws = lv.map(id => stepByNode[id]).filter(Boolean)
    if (ws.length) groups.push(ws)
  }

  // Add any steps not in levels
  const groupedIds = new Set(groups.flat().map(s => s.node_id))
  const remaining = steps.filter(s => !groupedIds.has(s.node_id))
  if (remaining.length) groups.push(remaining)

  return groups
})

// Call chain
const showCallChain = computed(() => {
  return !!(trace.value?.parent_trace_id || trace.value?.parent_trace || (trace.value?.child_traces && trace.value.child_traces.length))
})

// Grid layout: equal center/right; 3-col when call chain visible, 2-col otherwise
const gridStyle = computed(() => {
  if (showCallChain.value) {
    return { gridTemplateColumns: 'minmax(160px, 1fr) 1fr 1fr' }
  }
  return { gridTemplateColumns: '1fr 1fr' }
})

const callChainItems = computed(() => {
  const items = []
  // Add parent if exists
  if (trace.value?.parent_trace) {
    items.push({
      trace_id: trace.value.parent_trace.trace_id,
      app_name: trace.value.parent_trace.app_name || '父工作流',
      status: trace.value.parent_trace.status || 'done'
    })
  } else if (trace.value?.parent_trace_id) {
    items.push({
      trace_id: trace.value.parent_trace_id,
      app_name: '父工作流',
      status: 'done'
    })
  }
  // Current
  items.push({
    trace_id: trace.value?.trace_id,
    app_name: trace.value?.app_name || trace.value?.project_name || '当前',
    status: trace.value?.status || 'done'
  })
  // Children
  for (const c of trace.value?.child_traces || []) {
    items.push({
      trace_id: c.trace_id,
      app_name: c.app_name || c.trace_id,
      status: c.status || 'done'
    })
  }
  return items
})

// Log lines from steps
const logLines = computed(() => {
  const steps = trace.value?.steps
  if (!Array.isArray(steps)) return []

  if (trace.value?.type === 'lab') {
    return steps
      .filter(s => s.status !== 'pending')
      .map((s, i) => ({
        t: `#${i + 1}`,
        level: s.status === 'error' ? 'error' : 'info',
        text: `${s.title || s.meta?.title || s.step_id}: ${s.status || 'unknown'}`
      }))
  }

  return steps.map(s => ({
    t: s.started_at ? new Date(s.started_at).toLocaleTimeString() : '',
    level: s.status === 'error' ? 'error' : 'info',
    text: `${s.label || s.var_name || s.node_id} [${kindLabel(s.kind)}]: ${s.status === 'error' ? s.error || '失败' : s.status === 'done' ? '完成' : s.status || '未知'}`
  }))
})

const stepCount = computed(() => {
  return trace.value?.steps?.length || 0
})

const errorCount = computed(() => {
  return (trace.value?.steps || []).filter(s => s.status === 'error').length
})

function copyId() {
  const id = trace.value?.trace_id
  if (!id) return
  navigator.clipboard.writeText(id).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.warning('复制失败')
  )
}

async function loadTrace(traceId) {
  if (!traceId) {
    errorMsg.value = '缺少 trace_id'
    trace.value = null
    loading.value = false
    return
  }
  loading.value = true
  errorMsg.value = ''
  trace.value = null
  currentTraceId.value = String(traceId)
  try {
    trace.value = await getTrace(String(traceId))
  } catch (e) {
    errorMsg.value = e.message || '加载失败'
    ElMessage.error(errorMsg.value)
  } finally {
    loading.value = false
  }
}

function switchTrace(traceId) {
  if (traceId === currentTraceId.value) return
  router.push({ name: 'AgentTraceView', params: { traceId } })
}

watch(
  () => route.params.traceId,
  (id) => loadTrace(id),
  { immediate: true }
)
</script>

<style scoped>
.trace-view-page {
  flex: 1;
  min-height: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  background: #f8faf9;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  overflow: hidden;
}

.trace-view-head {
  flex-shrink: 0;
  padding: 16px 24px 12px;
  background: linear-gradient(180deg, #fff 0%, #fafcfb 100%);
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.trace-view-head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.trace-view-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trace-view-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #101828;
}

.trace-meta {
  padding: 12px 16px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.trace-meta-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-right: 20px;
  font-size: 13px;
  color: #303133;
}

.trace-meta-line .label {
  color: #909399;
  font-size: 12px;
}

.trace-meta-line.muted {
  color: #909399;
  font-size: 12px;
}

.trace-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}

.trace-id {
  font-size: 12px;
  word-break: break-all;
}

.trace-meta-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  color: #f56c6c;
}

.trace-meta-error .label {
  flex-shrink: 0;
  color: #909399;
}

.error-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.trace-error {
  color: #f56c6c;
  font-size: 14px;
  padding: 8px 0;
}

.trace-skeleton {
  padding: 24px;
}

/* Body: dynamic grid (2 or 3 columns via :style) */
.trace-view-body {
  flex: 1;
  min-height: 0;
  display: grid;
  gap: 0;
}

/* Left column: call chain */
.trace-col--chain {
  border-right: 1px solid rgba(15, 23, 42, 0.06);
  background: #fff;
}

.trace-chain-tree {
  padding: 8px 12px;
}

.trace-chain-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: #303133;
  transition: background 0.15s;
}

.trace-chain-node:hover {
  background: rgba(61, 141, 130, 0.06);
}

.trace-chain-node.is-active {
  background: rgba(61, 141, 130, 0.1);
  font-weight: 600;
}

.trace-chain-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #d0d5dd;
}

.trace-chain-status.is-done {
  background: #16a34a;
}

.trace-chain-status.is-error {
  background: #b42318;
}

.trace-chain-status.is-running {
  background: #2e90fa;
  box-shadow: 0 0 0 3px rgba(46, 144, 250, 0.25);
}

.trace-chain-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Center column: cards */
.trace-col--cards {
  border-right: 1px solid rgba(15, 23, 42, 0.06);
  background: #fff;
}

.trace-cards-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}

/* Right column: log */
.trace-col--log {
  background: #fff;
}

/* Column head */
.trace-col-head {
  flex-shrink: 0;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 700;
  color: #101828;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.trace-col {
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.trace-empty {
  font-size: 13px;
  color: #98a2b3;
  padding: 16px;
  text-align: center;
}

/* Wave groups */
.trace-node-chain {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trace-wave-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #667085;
  font-weight: 600;
  padding: 4px 0;
}

.trace-wave-parallel {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(46, 144, 250, 0.1);
  color: #175cd3;
}

.trace-wave-nodes {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* Node cards */
.trace-node-card {
  width: 248px;
  min-width: 248px;
  flex: 0 0 auto;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: #fff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  padding: 12px 14px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.trace-node-card.is-running {
  border-color: rgba(46, 144, 250, 0.45);
  box-shadow: 0 0 0 1px rgba(46, 144, 250, 0.12);
}

.trace-node-card.is-done {
  border-color: rgba(22, 163, 74, 0.35);
}

.trace-node-card.is-error {
  border-color: rgba(180, 35, 24, 0.45);
  box-shadow: 0 0 0 1px rgba(180, 35, 24, 0.08);
}

.trace-node-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.trace-node-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #d0d5dd;
}

.trace-node-status.is-idle { background: #d0d5dd; }
.trace-node-status.is-run {
  background: #2e90fa;
  box-shadow: 0 0 0 3px rgba(46, 144, 250, 0.25);
  animation: trace-pulse 1.2s ease-in-out infinite;
}
.trace-node-status.is-done { background: #16a34a; }
.trace-node-status.is-error { background: #b42318; }

@keyframes trace-pulse {
  50% { opacity: 0.65; }
}

.trace-node-title {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 14px;
  font-weight: 700;
  color: #101828;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-node-kind {
  flex-shrink: 0;
}

.trace-node-elapsed {
  font-size: 11px;
  color: #909399;
  flex-shrink: 0;
}

.trace-node-collapse {
  margin-top: 4px;
}

.trace-node-collapse :deep(.el-collapse-item__header) {
  font-size: 12px;
  color: #667085;
  height: 32px;
  line-height: 32px;
}

.trace-pre {
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: #1d2939;
  max-height: 240px;
  overflow-y: auto;
  margin: 0;
}

.trace-pre--error {
  color: #b42318;
}

.trace-node-children {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
}

/* Log column */
.trace-log-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px;
}

.trace-log-overview {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
}

.trace-log-stat {
  text-align: center;
  flex: 1;
}

.trace-log-stat-val {
  display: block;
  font-size: 18px;
  font-weight: 700;
  color: #101828;
}

.trace-log-stat-label {
  font-size: 11px;
  color: #909399;
}

.trace-log-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  line-height: 1.5;
}

.trace-log-time {
  flex-shrink: 0;
  color: #98a2b3;
  font-family: monospace;
}

.trace-log-tag {
  flex-shrink: 0;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
}

.trace-log-line.is-info .trace-log-tag {
  background: rgba(46, 144, 250, 0.1);
  color: #175cd3;
}

.trace-log-line.is-error .trace-log-tag {
  background: rgba(180, 35, 24, 0.1);
  color: #b42318;
}

.trace-log-text {
  flex: 1;
  color: #303133;
  word-break: break-word;
}
</style>
