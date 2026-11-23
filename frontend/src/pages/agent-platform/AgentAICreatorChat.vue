<template>
  <div class="arc-shell agent-platform-page">
    <div class="arc-bg" aria-hidden="true">
      <div class="arc-bg__mesh" />
      <div class="arc-bg__grain" />
    </div>

    <header class="arc-header">
      <div class="arc-header__left">
        <button type="button" class="arc-back" @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          <span>返回</span>
        </button>
        <div class="arc-header__brand">
          <span class="arc-badge">Studio</span>
          <h1 class="arc-title">AI生成工作流</h1>
          <p class="arc-tagline">
            洞察需求 · 点选确认 · 工作流落盘
          </p>
        </div>
      </div>
      <div class="arc-header__controls">
        <div class="arc-model-group">
          <label class="arc-label">对话模型</label>
          <el-select
            v-model="selectedProviderId"
            class="arc-select arc-select--prov"
            placeholder="供应商"
            filterable
            size="default"
            @change="onProviderChange"
          >
            <el-option
              v-for="p in activeProviders"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
          <el-select
            v-model="selectedModelName"
            class="arc-select arc-select--model"
            placeholder="模型"
            filterable
            size="default"
          >
            <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
          </el-select>
        </div>
        <button type="button" class="arc-btn-ghost" @click="resetSession">重新开始</button>
      </div>
    </header>

    <div ref="listRef" class="arc-feed">
      <TransitionGroup name="arc-msg" tag="div" class="arc-feed__inner">
        <div
          v-for="block in renderBlocks"
          :key="block.key"
          class="arc-row"
          :class="`is-${block.role}`"
        >
          <template v-if="block.role === 'user'">
            <div class="arc-user">
              <span class="arc-user__meta">你</span>
              <div class="arc-user__bubble">{{ block.text }}</div>
            </div>
          </template>
          <template v-else>
            <div class="arc-assistant">
              <div class="arc-assistant__rail" aria-hidden="true" />
              <div class="arc-assistant__body">
                <div v-if="block.toolCalls?.length" class="arc-tools">
                  <div
                    v-for="(tc, idx) in block.toolCalls"
                    :key="idx"
                    class="arc-tool"
                    :class="`arc-tool--${tc.status}`"
                  >
                    <div class="arc-tool__glyph">
                      <el-icon v-if="tc.status === 'running'" class="arc-tool__spin"><Loading /></el-icon>
                      <el-icon v-else-if="tc.status === 'success'" class="arc-tool__ok"><CircleCheck /></el-icon>
                      <el-icon v-else class="arc-tool__warn"><WarningFilled /></el-icon>
                    </div>
                    <div class="arc-tool__main">
                      <div class="arc-tool__name">{{ toolLabel(tc.tool) }}</div>
                      <div class="arc-tool__sum">{{ tc.summary }}</div>
                      <el-collapse v-if="tc.result_preview?.length" class="arc-tool__collapse">
                        <el-collapse-item title="结果摘要" :name="`${block.key}-tc-${idx}`">
                          <ul class="arc-tool__list">
                            <li v-for="(row, j) in tc.result_preview" :key="j">
                              {{ formatPreviewRow(row) }}
                            </li>
                          </ul>
                        </el-collapse-item>
                      </el-collapse>
                    </div>
                  </div>
                </div>

                <div class="arc-card">
                  <details v-if="block.thinking" class="arc-cogito">
                    <summary>
                      <span class="arc-cogito__icon" aria-hidden="true" />
                      推理轨迹
                    </summary>
                    <pre class="arc-cogito__pre">{{ block.thinking }}</pre>
                  </details>
                  <div class="arc-prose">{{ block.content }}</div>

                  <div v-if="block.options?.length" class="arc-opts">
                    <p class="arc-opts__hint">选择一项或补充说明</p>
                    <el-radio-group v-model="optionPick[block.msgId]" class="arc-radio-group">
                      <el-radio
                        v-for="opt in block.options"
                        :key="opt.id"
                        :label="opt.id"
                        class="arc-radio"
                      >
                        <span class="arc-radio__title">{{ opt.label }}</span>
                        <span v-if="opt.description" class="arc-radio__desc">{{ opt.description }}</span>
                      </el-radio>
                    </el-radio-group>
                    <div v-if="showOtherFor(block.msgId)" class="arc-other">
                      <span class="arc-other__label">其他</span>
                      <el-input
                        v-model="optionOther[block.msgId]"
                        type="textarea"
                        :rows="2"
                        placeholder="补充你的想法…"
                        class="arc-field"
                      />
                    </div>
                    <button
                      type="button"
                      class="arc-btn-primary"
                      :disabled="sending"
                      @click="submitOption(block.msgId)"
                    >
                      确认选择
                    </button>
                  </div>

                  <div v-if="block.paramsSchema?.length" class="arc-form-block">
                    <el-form label-position="top" class="arc-form">
                      <el-form-item
                        v-for="ps in block.paramsSchema"
                        :key="ps.key"
                        :label="ps.label + (ps.required ? ' *' : '')"
                      >
                        <template v-if="ps.description">
                          <div class="arc-form__hint">{{ ps.description }}</div>
                        </template>
                        <el-input
                          v-model="paramDraft[ps.key]"
                          :placeholder="ps.placeholder || ''"
                          class="arc-field"
                        />
                      </el-form-item>
                    </el-form>
                    <button
                      type="button"
                      class="arc-btn-primary"
                      :disabled="sending"
                      @click="submitParams(block)"
                    >
                      提交参数
                    </button>
                  </div>

                  <div v-if="block.replyType === 'confirm'" class="arc-confirm">
                    <button type="button" class="arc-btn-primary arc-btn-primary--lg" :disabled="creating" @click="confirmCreate(block)">
                      <span v-if="creating" class="arc-btn__loading" />
                      确认并创建应用
                    </button>
                    <button type="button" class="arc-btn-secondary" :disabled="creating" @click="sendText('我想再调整一下方案。')">
                      再改一版
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <!-- 模型响应中：思考动效卡片 -->
        <div v-if="sending" key="thinking-placeholder" class="arc-row is-thinking" aria-live="polite">
          <div class="arc-thinking">
            <div class="arc-thinking__orbit" aria-hidden="true">
              <span class="arc-thinking__ring arc-thinking__ring--a" />
              <span class="arc-thinking__ring arc-thinking__ring--b" />
              <span class="arc-thinking__core" />
            </div>
            <div class="arc-thinking__copy">
              <span class="arc-thinking__label">模型工作中</span>
              <p :key="thinkingCueIndex" class="arc-thinking__cue">{{ thinkingCueText }}</p>
              <div class="arc-thinking__bars" aria-hidden="true">
                <span v-for="n in 4" :key="n" class="arc-thinking__bar" :style="{ animationDelay: `${n * 0.12}s` }" />
              </div>
            </div>
          </div>
        </div>
      </TransitionGroup>
    </div>

    <div v-if="creationSteps.length" class="arc-progress">
      <h3 class="arc-progress__title">创建流水线</h3>
      <el-steps direction="vertical" :active="creationActive" class="arc-steps">
        <el-step
          v-for="(st, i) in creationSteps"
          :key="i"
          :title="st.title"
          :description="st.detail"
          :status="st.status"
        />
      </el-steps>
    </div>

    <footer class="arc-compose">
      <el-input
        v-model="inputText"
        type="textarea"
        :rows="2"
        placeholder="描述目标、约束或追问…（Enter 发送）"
        :disabled="sending"
        class="arc-compose__input"
        @keydown.enter.exact.prevent="sendText()"
      />
      <button
        type="button"
        class="arc-btn-send"
        :disabled="!inputText.trim() || sending"
        @click="sendText()"
      >
        <span v-if="sending" class="arc-btn-send__pulse" />
        {{ sending ? '等待中' : '发送' }}
      </button>
    </footer>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, CircleCheck, Loading, WarningFilled } from '@element-plus/icons-vue'
import agentAppApi from '@/api/agentApp'
import { getModelProviders } from '@/api/modelProvider'
import { getOwnerDisplayNameForCreate } from '@/utils/auth'

const router = useRouter()
const listRef = ref(null)
const sending = ref(false)
const creating = ref(false)
const inputText = ref('')

const THINKING_CUES = [
  '正在对齐当前阶段目标与已收集信息…',
  '必要时将调用工具：工作流列表、实验室项目、数据表结构…',
  '正在把推理压缩为可点击的选项或结构化方案…',
  '复杂工作流可能需十余秒，请稍候…',
  '若首次较慢，多为供应商冷启动或长上下文…'
]

const thinkingCueIndex = ref(0)
let thinkingTimer = null

const thinkingCueText = computed(() => THINKING_CUES[thinkingCueIndex.value % THINKING_CUES.length])

function startThinkingAnimation() {
  thinkingCueIndex.value = 0
  stopThinkingAnimation()
  thinkingTimer = window.setInterval(() => {
    thinkingCueIndex.value += 1
  }, 2800)
}

function stopThinkingAnimation() {
  if (thinkingTimer != null) {
    clearInterval(thinkingTimer)
    thinkingTimer = null
  }
}

watch(sending, (v) => {
  if (v) startThinkingAnimation()
  else stopThinkingAnimation()
})

onUnmounted(() => stopThinkingAnimation())

const sessionId = ref(
  typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `s-${Date.now()}`
)
const phase = ref('WELCOME')
const collectedInfo = ref({})
const filledParams = ref({})
const workflowDesign = ref(null)

const messages = ref([])
const optionPick = reactive({})
const optionOther = reactive({})
const paramDraft = reactive({})

const modelProviders = ref([])
const selectedProviderId = ref(null)
const selectedModelName = ref('')

const creationSteps = ref([])
const creationActive = ref(0)

const TOOL_LABELS = {
  list_agent_apps: '工作流应用',
  list_lab_projects: '实验室项目',
  get_data_tables: '数据表结构',
  get_model_providers: '模型列表'
}

function toolLabel(name) {
  return TOOL_LABELS[name] || name
}

function parseProviderModels(modelsStr) {
  if (!modelsStr) return []
  try {
    const a = JSON.parse(modelsStr)
    return Array.isArray(a) ? a : []
  } catch {
    return []
  }
}

function normalizeModelName(entry) {
  if (entry == null) return ''
  if (typeof entry === 'string') return entry
  if (typeof entry === 'object') return String(entry.name || entry.id || entry.model || '')
  return String(entry)
}

const activeProviders = computed(() =>
  (modelProviders.value || []).filter((p) => p.is_active !== false)
)

const modelOptions = computed(() => {
  const p = modelProviders.value.find((x) => x.id === selectedProviderId.value)
  if (!p) return []
  return parseProviderModels(p.models).map(normalizeModelName).filter(Boolean)
})

function onProviderChange() {
  const opts = modelOptions.value
  selectedModelName.value = opts[0] || ''
}

watch(modelOptions, (opts) => {
  if (opts.length && !opts.includes(selectedModelName.value)) {
    selectedModelName.value = opts[0]
  }
})

async function loadProviders() {
  try {
    const list = await getModelProviders({ limit: 100 })
    modelProviders.value = Array.isArray(list) ? list : []
    const first = activeProviders.value[0]
    if (first) {
      selectedProviderId.value = first.id
      const names = parseProviderModels(first.models).map(normalizeModelName).filter(Boolean)
      selectedModelName.value = names[0] || ''
    }
  } catch {
    modelProviders.value = []
  }
}

function goBack() {
  router.push({ name: 'AgentPlatformAgents' })
}

function resetSession() {
  sessionId.value =
    typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `s-${Date.now()}`
  phase.value = 'WELCOME'
  collectedInfo.value = {}
  filledParams.value = {}
  workflowDesign.value = null
  messages.value = []
  Object.keys(optionPick).forEach((k) => delete optionPick[k])
  Object.keys(optionOther).forEach((k) => delete optionOther[k])
  Object.keys(paramDraft).forEach((k) => delete paramDraft[k])
  creationSteps.value = []
  creationActive.value = 0
  kickoff()
}

function assistantToContent(payload) {
  return JSON.stringify({
    phase: payload.phase,
    thinking: payload.thinking,
    reply_type: payload.reply_type,
    content: payload.content,
    options: payload.options,
    workflow_design: payload.workflow_design,
    params_schema: payload.params_schema
  })
}

function buildApiMessages() {
  const out = []
  for (const m of messages.value) {
    if (m.role === 'user') {
      out.push({ role: 'user', content: m.text })
    } else {
      out.push({ role: 'assistant', content: assistantToContent(m.payload) })
    }
  }
  return out
}

async function scrollToBottom() {
  await nextTick()
  await new Promise((r) => requestAnimationFrame(r))
  const el = listRef.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(
  () => [messages.value.length, sending.value, creationSteps.value.length],
  () => {
    scrollToBottom()
  }
)

async function callChat(userVisibleText) {
  if (!selectedProviderId.value || !selectedModelName.value) {
    ElMessage.warning('请先配置并选择模型供应商与模型')
    return null
  }
  sending.value = true
  try {
    const data = await agentAppApi.aiCreatorChat({
      session_id: sessionId.value,
      phase: phase.value,
      messages: buildApiMessages(),
      collected_info: collectedInfo.value,
      creator_model: {
        provider_id: selectedProviderId.value,
        model_name: selectedModelName.value
      },
      workflow_design: workflowDesign.value,
      filled_params: filledParams.value,
      tool_cache: {}
    })
    return data
  } catch (e) {
    ElMessage.error(e.message || '对话请求失败')
    return null
  } finally {
    sending.value = false
  }
}

const renderBlocks = computed(() => {
  const blocks = []
  let i = 0
  for (const m of messages.value) {
    if (m.role === 'user') {
      blocks.push({ key: `u-${i}`, role: 'user', text: m.text })
    } else {
      const p = m.payload || {}
      blocks.push({
        key: `a-${i}`,
        role: 'assistant',
        msgId: m.id || `a-${i}`,
        thinking: p.thinking,
        content: p.content,
        options: p.options,
        paramsSchema: p.params_schema,
        replyType: p.reply_type,
        toolCalls: p.tool_calls || []
      })
    }
    i += 1
  }
  return blocks
})

function showOtherFor(msgId) {
  const id = optionPick[msgId]
  const last = messages.value.find((m) => m.id === msgId)
  const opts = last?.payload?.options || []
  const picked = opts.find((o) => o.id === id)
  return picked?.is_other
}

async function sendText(text) {
  const raw = text != null && text !== '' ? String(text) : inputText.value
  const t = raw.trim()
  if (!t) return
  if (text == null || text === '') inputText.value = ''
  messages.value.push({ role: 'user', text: t })
  await scrollToBottom()
  const data = await callChat(t)
  if (!data) return
  pushAssistant(data)
}

function pushAssistant(data) {
  const id = `m-${Date.now()}`
  const pschema = data.params_schema || []
  for (const ps of pschema) {
    if (ps.default != null && paramDraft[ps.key] === undefined) {
      paramDraft[ps.key] = String(ps.default)
    }
  }
  messages.value.push({
    id,
    role: 'assistant',
    payload: {
      thinking: data.thinking,
      content: data.content,
      reply_type: data.reply_type,
      options: data.options || [],
      params_schema: pschema,
      workflow_design: data.workflow_design,
      tool_calls: data.tool_calls || []
    }
  })
  if (data.next_phase) {
    phase.value = data.next_phase
  } else if (data.phase) {
    phase.value = data.phase
  }
  if (data.workflow_design) {
    workflowDesign.value = data.workflow_design
  }
  if (data.collected_info_update && typeof data.collected_info_update === 'object') {
    collectedInfo.value = { ...collectedInfo.value, ...data.collected_info_update }
  }
  scrollToBottom()
}

async function submitOption(msgId) {
  const last = messages.value.find((m) => m.id === msgId)
  const opts = last?.payload?.options || []
  const oid = optionPick[msgId]
  if (!oid) {
    ElMessage.warning('请选择一个选项')
    return
  }
  const picked = opts.find((o) => o.id === oid)
  let text = picked ? `${picked.label}` : oid
  if (picked?.is_other && (optionOther[msgId] || '').trim()) {
    text += `：${optionOther[msgId].trim()}`
  }
  await sendText(text)
}

async function submitParams(block) {
  const schema = block.paramsSchema || []
  for (const ps of schema) {
    if (ps.required && !(paramDraft[ps.key] || '').toString().trim()) {
      ElMessage.warning(`请填写：${ps.label}`)
      return
    }
  }
  const parts = []
  for (const ps of schema) {
    const v = (paramDraft[ps.key] ?? '').toString().trim()
    if (v) {
      filledParams.value = { ...filledParams.value, [ps.key]: v }
      parts.push(`${ps.label}=${v}`)
    }
  }
  await sendText(`参数已填写：${parts.join('；')}`)
}

function formatPreviewRow(row) {
  if (row.name != null && row.id != null) return `${row.name}（id=${row.id}）`
  if (row.table_name != null) return `${row.table_name} · ${row.knowledge_base_name || ''}`
  return JSON.stringify(row)
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

async function withRetry(fn, title, max = 3) {
  let lastErr = null
  for (let attempt = 1; attempt <= max; attempt += 1) {
    creationSteps.value.push({
      title,
      detail: attempt > 1 ? `重试 ${attempt}/${max}` : '执行中…',
      status: 'process'
    })
    const idx = creationSteps.value.length - 1
    creationActive.value = idx
    try {
      const res = await fn()
      creationSteps.value[idx] = { title, detail: '成功', status: 'finish' }
      return res
    } catch (e) {
      lastErr = e
      creationSteps.value[idx] = {
        title,
        detail: `失败：${e.message || e}`,
        status: 'error'
      }
      if (attempt < max) {
        await sleep(400 * 2 ** (attempt - 1))
        creationSteps.value.push({
          title: `${title}（重试）`,
          detail: '等待后重试…',
          status: 'wait'
        })
      }
    }
  }
  throw lastErr || new Error('未知错误')
}

async function confirmCreate(block) {
  const wd = workflowDesign.value || block.payload?.workflow_design
  if (!wd || !wd.nodes?.length) {
    ElMessage.error('缺少工作流设计，请回到设计阶段')
    return
  }
  creating.value = true
  creationSteps.value = []
  creationActive.value = 0
  try {
    const { workflow } = await withRetry(
      () => agentAppApi.aiCreatorBuildWorkflow({ workflow_design: wd, filled_params: filledParams.value }),
      '生成画布 JSON',
      3
    )
    const appName = (wd.app_name || 'AI 创建应用').toString().slice(0, 128)
    const desc = (wd.description || '').toString().slice(0, 500)
    const owner = getOwnerDisplayNameForCreate()
    const detail = await withRetry(
      () =>
        agentAppApi.createAgentApp({
          name: appName,
          icon: '✨',
          description: desc || null,
          ...(owner ? { owner_display_name: owner } : {})
        }),
      '创建应用',
      3
    )
    const versions = detail.versions || []
    const v =
      versions.find((x) => x.name === 'v1.0') ||
      versions.sort((a, b) => (b.id || 0) - (a.id || 0))[0]
    if (!v) throw new Error('未找到新建版本')
    const getWf = await withRetry(
      () => agentAppApi.getWorkflow(detail.id, v.id),
      '读取工作流版本',
      3
    )
    await withRetry(
      () =>
        agentAppApi.putWorkflow(detail.id, v.id, {
          nodes: workflow.nodes,
          edges: workflow.edges,
          expected_rev: getWf.workflow_rev ?? 0
        }),
      '写入工作流',
      3
    )
    ElMessage.success('创建成功，正在打开画布…')
    router.push({
      name: 'AgentWorkflowDesign',
      params: { appId: String(detail.id), versionId: String(v.id) }
    })
  } catch (e) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    creating.value = false
  }
}

async function kickoff() {
  await loadProviders()
  if (!selectedProviderId.value || !selectedModelName.value) {
    ElMessage.warning('请先在「模型中心」配置可用的模型供应商与模型列表')
    return
  }
  await sendText('你好，我想创建一个工作流，请从产品角度引导我，必要时查询我现有的工作流、实验室项目或数据表。')
}

onMounted(() => {
  kickoff()
})
</script>

<style scoped>
/* 纸本光感工作室：与工作流平台薄荷基调协调的浅色界面 */
.arc-shell {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  width: 100%;
  max-width: none;
  margin: 0;
  padding: 16px 24px 0;
  box-sizing: border-box;
  border-radius: 0;
  border: none;
  background: transparent;
  box-shadow: none;
  color: var(--arc-ink);
  font-family: var(--arc-font-body);

  --arc-paper: #faf9f6;
  --arc-wash: #f3f6f4;
  --arc-surface: #ffffff;
  --arc-ink: #1e2d28;
  --arc-muted: #5c6b65;
  --arc-line: #dfe8e4;
  --arc-line-soft: #e8f0ec;
  --arc-teal: #0f766e;
  --arc-teal-soft: #ccfbf1;
  --arc-teal-mid: #14b8a6;
  --arc-honey: #b45309;
  --arc-honey-soft: #fff7ed;
  --arc-danger: #ea580c;
  --arc-font-display: 'Syne', 'Plus Jakarta Sans', system-ui, sans-serif;
  --arc-font-body: 'Literata', 'Georgia', serif;
}

/* 覆盖全局 .agent-platform-page 的居中宽度与（若有）最小高度，避免与主区 flex 双滚动 */
.arc-shell.agent-platform-page {
  max-width: none;
  margin: 0;
  min-height: 0;
}

.arc-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  border-radius: 0;
  background: linear-gradient(165deg, #fbfcfa 0%, #f5f8f6 42%, #f0f4f1 100%);
}

.arc-bg__mesh {
  position: absolute;
  inset: 0;
  border-radius: 0;
  background:
    radial-gradient(ellipse 70% 55% at 12% 0%, rgba(20, 184, 166, 0.09), transparent 52%),
    radial-gradient(ellipse 55% 45% at 92% 8%, rgba(180, 83, 9, 0.06), transparent 48%),
    radial-gradient(ellipse 50% 70% at 50% 100%, rgba(224, 235, 228, 0.65), transparent 55%);
}

.arc-bg__grain {
  position: absolute;
  inset: 0;
  border-radius: 0;
  opacity: 0.035;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

.arc-shell > :not(.arc-bg) {
  position: relative;
  z-index: 1;
}

/* Header */
.arc-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--arc-line-soft);
}

.arc-header__left {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  min-width: 0;
}

.arc-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  margin: 0;
  border: 1px solid var(--arc-line);
  border-radius: 12px;
  background: var(--arc-surface);
  color: var(--arc-muted);
  font-family: var(--arc-font-display);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(30, 45, 40, 0.04);
  transition: color 0.2s ease, border-color 0.2s ease, transform 0.15s ease;
}

.arc-back:hover {
  color: var(--arc-teal);
  border-color: rgba(20, 184, 166, 0.45);
  transform: translateX(-2px);
}

.arc-header__brand {
  min-width: 0;
}

.arc-badge {
  display: inline-block;
  font-family: var(--arc-font-display);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--arc-honey);
  margin-bottom: 6px;
}

.arc-title {
  margin: 0;
  font-family: var(--arc-font-display);
  font-size: clamp(1.42rem, 2.8vw, 1.78rem);
  font-weight: 800;
  letter-spacing: -0.035em;
  line-height: 1.12;
  color: var(--arc-ink);
}

.arc-tagline {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--arc-muted);
  letter-spacing: 0.01em;
  line-height: 1.45;
}

.arc-header__controls {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}

.arc-model-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.arc-label {
  font-family: var(--arc-font-display);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--arc-muted);
  width: 100%;
  margin-bottom: -2px;
  opacity: 0.9;
}

@media (min-width: 640px) {
  .arc-label {
    width: auto;
    margin-bottom: 0;
  }
}

.arc-btn-ghost {
  padding: 9px 16px;
  border-radius: 12px;
  border: 1px solid var(--arc-line);
  background: var(--arc-surface);
  color: var(--arc-muted);
  font-family: var(--arc-font-display);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s, box-shadow 0.2s;
  box-shadow: 0 1px 4px rgba(30, 45, 40, 0.04);
}

.arc-btn-ghost:hover {
  color: var(--arc-teal);
  border-color: rgba(20, 184, 166, 0.4);
  box-shadow: 0 4px 14px rgba(20, 184, 166, 0.1);
}

/* Feed：占据标题与输入区之间的剩余高度并单独滚动 */
.arc-feed {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 6px;
  margin-bottom: 0;
  scrollbar-width: thin;
  scrollbar-color: rgba(15, 118, 110, 0.35) transparent;
}

.arc-feed__inner {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.arc-row.is-user {
  display: flex;
  justify-content: flex-end;
}

.arc-user {
  max-width: 88%;
  text-align: right;
}

.arc-user__meta {
  display: block;
  font-family: var(--arc-font-display);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--arc-muted);
  margin-bottom: 6px;
  opacity: 0.85;
}

.arc-user__bubble {
  display: inline-block;
  text-align: left;
  padding: 14px 18px;
  border-radius: 20px 20px 6px 20px;
  background: linear-gradient(145deg, #0d9488 0%, #0f766e 100%);
  color: #f8fffe;
  font-size: 15px;
  line-height: 1.55;
  white-space: pre-wrap;
  box-shadow: 0 10px 28px rgba(15, 118, 110, 0.22);
}

.arc-assistant {
  display: flex;
  gap: 14px;
  align-items: stretch;
}

.arc-assistant__rail {
  width: 4px;
  border-radius: 4px;
  background: linear-gradient(180deg, #2dd4bf 0%, #0d9488 55%, rgba(13, 148, 136, 0.15) 100%);
  flex-shrink: 0;
  opacity: 0.9;
}

.arc-assistant__body {
  flex: 1;
  min-width: 0;
}

.arc-tools {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.arc-tool {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--arc-line);
  background: var(--arc-surface);
  box-shadow: 0 4px 16px rgba(30, 45, 40, 0.04);
  transition: border-color 0.25s ease, box-shadow 0.25s ease;
}

.arc-tool--running {
  border-color: rgba(45, 212, 191, 0.55);
  box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.12), 0 8px 24px rgba(20, 184, 166, 0.12);
  animation: arc-tool-breathe 2.4s ease-in-out infinite;
}

.arc-tool--success {
  border-color: rgba(45, 212, 191, 0.35);
  background: linear-gradient(135deg, #ffffff 0%, #f0fdfa 100%);
}

.arc-tool--failed {
  border-color: rgba(234, 88, 12, 0.35);
  background: var(--arc-honey-soft);
}

@keyframes arc-tool-breathe {
  0%, 100% { box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.1), 0 6px 20px rgba(20, 184, 166, 0.08); }
  50% { box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.2), 0 10px 28px rgba(20, 184, 166, 0.14); }
}

.arc-tool__glyph {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--arc-wash);
  border: 1px solid var(--arc-line-soft);
}

.arc-tool__spin {
  font-size: 18px;
  color: var(--arc-teal);
  animation: arc-spin 0.85s linear infinite;
}

.arc-tool__ok {
  font-size: 18px;
  color: #059669;
}

.arc-tool__warn {
  font-size: 18px;
  color: var(--arc-danger);
}

@keyframes arc-spin {
  to { transform: rotate(360deg); }
}

.arc-tool__name {
  font-family: var(--arc-font-display);
  font-weight: 700;
  font-size: 13px;
  color: var(--arc-ink);
}

.arc-tool__sum {
  font-size: 13px;
  color: var(--arc-muted);
  margin-top: 4px;
}

.arc-tool__collapse {
  margin-top: 8px;
  --el-collapse-border-color: transparent;
}

.arc-tool__list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--arc-muted);
}

.arc-card {
  padding: 8px 0 0;
  border-radius: 0;
  background: transparent;
  border: none;
  box-shadow: none;
}

.arc-cogito {
  margin-bottom: 14px;
  font-family: var(--arc-font-display);
  font-size: 13px;
}

.arc-cogito summary {
  cursor: pointer;
  list-style: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--arc-teal);
  font-weight: 700;
}

.arc-cogito summary::-webkit-details-marker {
  display: none;
}

.arc-cogito__icon {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--arc-teal-mid);
  box-shadow: 0 0 0 3px var(--arc-teal-soft);
  animation: arc-dot-pulse 1.5s ease-in-out infinite;
}

@keyframes arc-dot-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.65; transform: scale(0.88); }
}

.arc-cogito__pre {
  margin: 12px 0 0;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--arc-wash);
  border: 1px solid var(--arc-line-soft);
  color: #3d4f48;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-x: auto;
}

.arc-prose {
  font-size: 15px;
  line-height: 1.68;
  color: #2c3d36;
  white-space: pre-wrap;
}

.arc-opts__hint {
  margin: 0 0 10px;
  font-family: var(--arc-font-display);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--arc-muted);
}

.arc-radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  align-items: stretch;
}

.arc-radio {
  height: auto !important;
  margin: 0 !important;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--arc-line) !important;
  background: var(--arc-paper) !important;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.arc-radio:hover {
  border-color: rgba(20, 184, 166, 0.35) !important;
}

.arc-radio.is-checked {
  border-color: var(--arc-teal) !important;
  background: #f0fdfa !important;
  box-shadow: 0 0 0 1px rgba(13, 148, 136, 0.12);
}

.arc-radio__title {
  display: block;
  font-family: var(--arc-font-display);
  font-weight: 600;
  font-size: 14px;
  color: var(--arc-ink);
}

.arc-radio__desc {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--arc-muted);
  line-height: 1.45;
}

.arc-other {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.arc-other__label {
  font-size: 12px;
  color: var(--arc-muted);
  font-weight: 600;
}

.arc-opts,
.arc-form-block {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--arc-line-soft);
}

.arc-form__hint {
  font-size: 12px;
  color: var(--arc-muted);
  margin-bottom: 6px;
}

.arc-confirm {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.arc-btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 22px;
  border: none;
  border-radius: 12px;
  font-family: var(--arc-font-display);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: 0.02em;
  cursor: pointer;
  color: #fff;
  background: linear-gradient(135deg, #14b8a6 0%, #0d9488 48%, #0f766e 100%);
  box-shadow: 0 8px 24px rgba(13, 148, 136, 0.28);
  transition: transform 0.15s ease, box-shadow 0.2s ease, opacity 0.2s ease;
}

.arc-btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 12px 32px rgba(13, 148, 136, 0.32);
}

.arc-btn-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.arc-btn-primary--lg {
  padding: 12px 26px;
  font-size: 14px;
}

.arc-btn__loading {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: arc-spin 0.7s linear infinite;
}

.arc-btn-secondary {
  padding: 10px 18px;
  border-radius: 12px;
  border: 1px solid var(--arc-line);
  background: var(--arc-surface);
  color: var(--arc-muted);
  font-family: var(--arc-font-display);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}

.arc-btn-secondary:hover:not(:disabled) {
  color: var(--arc-teal);
  border-color: rgba(20, 184, 166, 0.45);
}

/* 思考卡片（浅色） */
.arc-thinking {
  display: flex;
  gap: 22px;
  align-items: center;
  padding: 20px 22px;
  border-radius: 18px;
  background: linear-gradient(135deg, #ffffff 0%, #f3faf8 100%);
  border: 1px solid rgba(45, 212, 191, 0.35);
  box-shadow: 0 8px 32px rgba(20, 184, 166, 0.1);
  animation: arc-thinking-enter 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes arc-thinking-enter {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.arc-thinking__orbit {
  position: relative;
  width: 72px;
  height: 72px;
  flex-shrink: 0;
}

.arc-thinking__ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid transparent;
}

.arc-thinking__ring--a {
  border-top-color: #14b8a6;
  border-right-color: rgba(20, 184, 166, 0.2);
  animation: arc-orbit 1.85s linear infinite;
}

.arc-thinking__ring--b {
  inset: 9px;
  border-bottom-color: #b45309;
  border-left-color: rgba(180, 83, 9, 0.2);
  animation: arc-orbit 2.35s linear infinite reverse;
}

@keyframes arc-orbit {
  to { transform: rotate(360deg); }
}

.arc-thinking__core {
  position: absolute;
  inset: 22px;
  border-radius: 50%;
  background: radial-gradient(circle at 32% 28%, #5eead4, #0d9488 72%);
  box-shadow: 0 4px 20px rgba(13, 148, 136, 0.35);
  animation: arc-core-pulse 1.7s ease-in-out infinite;
}

@keyframes arc-core-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.94); opacity: 0.92; }
}

.arc-thinking__copy {
  flex: 1;
  min-width: 0;
}

.arc-thinking__label {
  font-family: var(--arc-font-display);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--arc-teal);
}

.arc-thinking__cue {
  margin: 8px 0 14px;
  font-size: 14px;
  line-height: 1.55;
  color: var(--arc-ink);
  animation: arc-cue-fade 0.45s ease both;
}

@keyframes arc-cue-fade {
  from { opacity: 0; transform: translateX(-5px); }
  to { opacity: 1; transform: translateX(0); }
}

.arc-thinking__bars {
  display: flex;
  gap: 6px;
  height: 4px;
}

.arc-thinking__bar {
  flex: 1;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--arc-line), #5eead4, var(--arc-line));
  background-size: 200% 100%;
  animation: arc-bar-shimmer 1.15s ease-in-out infinite;
}

@keyframes arc-bar-shimmer {
  0% { background-position: 100% 0; opacity: 0.4; }
  50% { opacity: 1; }
  100% { background-position: -100% 0; opacity: 0.4; }
}

.arc-progress {
  padding: 16px 18px;
  border-radius: 16px;
  background: var(--arc-surface);
  border: 1px solid var(--arc-line);
  margin-bottom: 14px;
  box-shadow: 0 6px 20px rgba(30, 45, 40, 0.04);
}

.arc-progress__title {
  margin: 0 0 12px;
  font-family: var(--arc-font-display);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--arc-honey);
}

.arc-compose {
  flex-shrink: 0;
  display: flex;
  gap: 12px;
  align-items: flex-end;
  margin-top: auto;
  padding: 14px 0 16px;
  border-top: 1px solid var(--arc-line-soft);
  background: linear-gradient(180deg, rgba(251, 252, 250, 0) 0%, rgba(251, 252, 250, 0.92) 18%, #fbfcfa 100%);
}

.arc-btn-send {
  flex-shrink: 0;
  position: relative;
  padding: 12px 24px;
  border: none;
  border-radius: 14px;
  font-family: var(--arc-font-display);
  font-size: 13px;
  font-weight: 800;
  color: #fff;
  background: linear-gradient(135deg, #2dd4bf 0%, #14b8a6 50%, #0d9488 100%);
  cursor: pointer;
  overflow: hidden;
  box-shadow: 0 8px 22px rgba(13, 148, 136, 0.25);
  transition: opacity 0.2s, transform 0.15s;
}

.arc-btn-send:hover:not(:disabled) {
  transform: translateY(-1px);
}

.arc-btn-send:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

.arc-btn-send__pulse {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.45), transparent);
  animation: arc-send-sheen 1.15s ease-in-out infinite;
}

@keyframes arc-send-sheen {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.arc-msg-move,
.arc-msg-enter-active,
.arc-msg-leave-active {
  transition: all 0.35s cubic-bezier(0.22, 1, 0.36, 1);
}

.arc-msg-enter-from {
  opacity: 0;
  transform: translateY(14px);
}

.arc-msg-leave-to {
  opacity: 0;
}

/* Element Plus 浅色 */
:deep(.arc-select .el-input__wrapper) {
  background: var(--arc-surface) !important;
  border-radius: 12px !important;
  box-shadow: 0 1px 4px rgba(30, 45, 40, 0.05) !important;
  border: 1px solid var(--arc-line) !important;
}

:deep(.arc-select .el-input__inner) {
  color: var(--arc-ink) !important;
  font-family: var(--arc-font-display);
  font-size: 13px;
  font-weight: 600;
}

:deep(.arc-select--prov) { width: 140px; }
:deep(.arc-select--model) { width: 168px; }

:deep(.arc-compose__input .el-textarea__inner) {
  background: var(--arc-surface) !important;
  border: 1px solid var(--arc-line) !important;
  border-radius: 16px !important;
  color: var(--arc-ink) !important;
  font-family: var(--arc-font-body);
  font-size: 15px;
  line-height: 1.55;
  padding: 14px 16px;
  box-shadow: 0 2px 12px rgba(30, 45, 40, 0.04) !important;
}

:deep(.arc-compose__input .el-textarea__inner::placeholder) {
  color: var(--arc-muted);
}

:deep(.arc-field .el-textarea__inner),
:deep(.arc-field .el-input__wrapper) {
  background: var(--arc-paper) !important;
  border-radius: 12px !important;
  box-shadow: none !important;
  border: 1px solid var(--arc-line) !important;
}

:deep(.arc-field .el-input__inner),
:deep(.arc-field .el-textarea__inner) {
  color: var(--arc-ink) !important;
}

:deep(.arc-form .el-form-item__label) {
  color: var(--arc-muted) !important;
  font-family: var(--arc-font-display);
  font-weight: 700;
  font-size: 12px;
}

:deep(.arc-radio .el-radio__label) {
  width: 100%;
  padding-left: 10px;
}

:deep(.arc-radio .el-radio__input.is-checked .el-radio__inner) {
  background: var(--arc-teal) !important;
  border-color: var(--arc-teal) !important;
}

:deep(.arc-radio .el-radio__inner) {
  border-color: #94a3a8;
  background: var(--arc-surface);
}

:deep(.arc-tool__collapse .el-collapse-item__header) {
  background: transparent !important;
  color: var(--arc-teal) !important;
  font-family: var(--arc-font-display);
  font-size: 12px;
  font-weight: 700;
  border: none !important;
}

:deep(.arc-tool__collapse .el-collapse-item__wrap) {
  background: transparent !important;
  border: none !important;
}

:deep(.arc-steps.el-steps--vertical) {
  --el-text-color-primary: var(--arc-ink);
  --el-text-color-regular: var(--arc-muted);
}

:deep(.arc-steps .el-step__title) {
  font-family: var(--arc-font-display);
  font-size: 13px;
  font-weight: 700;
}

:deep(.arc-steps .el-step__description) {
  font-size: 12px;
  color: var(--arc-muted) !important;
}
</style>
