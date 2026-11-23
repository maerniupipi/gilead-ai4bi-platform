<template>
  <div class="xq-bubble" :class="[`role-${message.role}`, message.status === 'failed' && 'is-failed']">
    <div v-if="message.role === 'user'" class="xq-bubble-user">
      <div class="xq-bubble-avatar user-avatar">{{ lang === 'en' ? 'Me' : '我' }}</div>
      <div class="xq-bubble-body">
        <div class="xq-bubble-content">{{ message.content }}</div>
      </div>
    </div>

    <div v-else class="xq-bubble-assistant">
      <div class="xq-bubble-avatar assistant-avatar">
        <el-icon><MagicStick /></el-icon>
      </div>
      <div class="xq-bubble-body">
        <div v-if="selectable" class="xq-bubble-select">
          <el-checkbox
            :model-value="selected"
            @change="(v) => $emit('toggle-select', message.id, v)"
          >
            {{ t('bubble.addPpt') }}
          </el-checkbox>
        </div>

        <!-- 流式进度 chip：在有阶段事件且还没完成时显示 -->
        <div
          v-if="streaming && stageChipText"
          class="xq-stage-chip"
          :class="stageChipClass"
        >
          <span class="xq-stage-spinner" />
          <span class="xq-stage-text">{{ stageChipText }}</span>
          <span v-if="stageDots" class="xq-stage-dots">{{ stageDots }}</span>
        </div>
        <!-- plan summary -->
        <div v-if="extras.plan_summary" class="stage-card plan-card">
          <div class="stage-head">
            <span class="stage-dot" :class="{ 'is-active': streaming && !extras.summary_markdown }" />
            <span class="stage-title">{{ t('bubble.plan') }}</span>
          </div>
          <div class="stage-body">{{ extras.plan_summary }}</div>
        </div>

        <!-- subquestions -->
        <div v-if="extras.subquestions?.length" class="subq-list">
          <div
            v-for="(sq, idx) in extras.subquestions"
            :key="sq.id || idx"
            class="subq-item"
            :class="[`sq-${sq.sql_status || 'pending'}`]"
          >
            <div class="subq-head" @click="toggle(sq.id)">
              <span class="subq-idx">{{ idx + 1 }}</span>
              <span class="subq-q">{{ sq.question }}</span>
              <span class="subq-status">
                <el-icon v-if="sq.sql_status === 'running' || sq.sql_status === 'pending'" class="is-loading">
                  <Loading />
                </el-icon>
                <el-icon v-else-if="sq.sql_status === 'ok'" style="color:#10b981">
                  <CircleCheckFilled />
                </el-icon>
                <el-icon v-else-if="sq.sql_status === 'error'" style="color:#ef4444">
                  <CircleCloseFilled />
                </el-icon>
              </span>
              <el-icon class="subq-expand" :class="{ 'is-open': expanded[sq.id] }">
                <ArrowDownBold />
              </el-icon>
            </div>

            <div v-if="sq.purpose" class="subq-purpose">{{ sq.purpose }}</div>

            <div v-show="expanded[sq.id]" class="subq-body">
              <div v-if="showSql && sq.sql" class="subq-sql">
                <div class="subq-sql-head">
                  <span>{{ t('bubble.sql') }}</span>
                  <el-button link size="small" @click="copySql(sq.sql)">{{ t('bubble.copySql') }}</el-button>
                </div>
                <pre><code>{{ sq.sql }}</code></pre>
              </div>
              <div v-if="sq.sql_status === 'error'" class="subq-error">
                <el-icon><WarningFilled /></el-icon>
                {{ t('bubble.sqlError') }}
              </div>
              <div v-if="sq.sql_status === 'ok' && sq.columns?.length" class="subq-result">
                <el-table :data="tableData(sq)" size="small" border stripe style="width: 100%">
                  <el-table-column
                    v-for="col in sq.columns"
                    :key="col"
                    :prop="col"
                    :label="col"
                    show-overflow-tooltip
                    min-width="120"
                  />
                </el-table>
                <div class="subq-result-meta">
                  {{ t('bubble.totalRows', { n: sq.total_rows }) }}{{ sq.truncated ? t('bubble.truncated', { n: sq.rows?.length || 0 }) : '' }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- charts：主图（大）+ 辅图（小卡片并列） -->
        <template v-if="primaryChart || secondaryCharts.length">
          <div v-if="primaryChart" class="xq-chart-primary">
            <XlsxQaChart :chart="primaryChart" size="large" />
          </div>
          <div v-if="secondaryCharts.length" class="xq-chart-secondary-grid">
            <div v-for="c in secondaryCharts" :key="c.subquestion_id" class="xq-chart-secondary-item">
              <XlsxQaChart :chart="c" size="small" />
            </div>
          </div>
        </template>

        <!-- 骨架屏：streaming 且 summary 还未到达 -->
        <div v-if="streaming && !extras.summary_markdown" class="summary-skeleton">
          <div class="sk-head">
            <div class="sk-dot" />
            <div class="sk-title-bar" />
          </div>
          <div class="sk-line sk-line--90" />
          <div class="sk-line sk-line--75" />
          <div class="sk-line sk-line--85" />
          <div class="sk-line sk-line--60" />
          <div class="sk-line sk-line--80" />
          <div class="sk-line sk-line--50" />
        </div>

        <!-- summary：有内容直接渲染 markdown，不再走流式打字机 -->
        <div v-if="extras.summary_markdown" class="stage-card summary-card">
          <div class="stage-head">
            <span class="stage-dot success" />
            <span class="stage-title">{{ t('bubble.summary') }}</span>
          </div>
          <div class="stage-body markdown-body" v-html="renderedSummary" />
        </div>

        <!-- follow-ups -->
        <div v-if="extras.follow_up_questions?.length" class="follow-ups">
          <div class="follow-ups-title">{{ t('bubble.followups') }}</div>
          <div class="follow-ups-list">
            <el-button
              v-for="q in extras.follow_up_questions"
              :key="q"
              size="small"
              round
              plain
              @click="$emit('follow-up', q)"
            >
              {{ q }}
            </el-button>
          </div>
        </div>

        <div v-if="message.status === 'failed'" class="failure-note">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ message.content || t('bubble.failNote') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  MagicStick,
  Loading,
  CircleCheckFilled,
  CircleCloseFilled,
  ArrowDownBold,
  WarningFilled
} from '@element-plus/icons-vue'
import XlsxQaChart from './XlsxQaChart.vue'
import { useXqI18n } from '../../utils/xlsxQaI18n'

const { t, lang } = useXqI18n()

const props = defineProps({
  message: { type: Object, required: true },
  streaming: { type: Boolean, default: false },
  selectable: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  showSql: { type: Boolean, default: false }
})
defineEmits(['follow-up', 'toggle-select'])

const extras = computed(() => props.message.extras || {})

// ------------------- 流式阶段 chip -------------------
// 父组件通过 props.message._stage 把最近一次 stage_start 事件塞进来
// （stage / message 两个字段）；本组件仅负责展示。
const STAGE_CLASS = {
  resolve_llm: 'chip-think',
  plan: 'chip-think',
  text_to_sql: 'chip-parse',
  run_sql: 'chip-parse',
  chart: 'chip-chart',
  summarize: 'chip-summary'
}

const stageChipText = computed(() => {
  const s = props.message._stage
  if (!s) {
    return props.streaming ? t('stage.thinking') : ''
  }
  // 英文 UI 下忽略后端返回的中文 message，直接用前端 i18n 映射，保证全英体验
  if (lang.value === 'en' && s.stage) {
    const k = `stage.${s.stage}`
    const en = t(k)
    if (en && en !== k) return en
  }
  // 中文或未知 stage：优先后端 message，否则回退到前端中文默认
  return s.message || t(`stage.${s.stage}`) || t('stage.thinking')
})
const stageChipClass = computed(() => {
  const s = props.message._stage
  return s ? STAGE_CLASS[s.stage] || 'chip-think' : 'chip-think'
})

// 轻量"……"动效，避免只靠 spinner 看着静止
const stageDots = ref('')
let dotsTimer = null
watch(
  () => props.streaming && !!stageChipText.value,
  (alive) => {
    clearInterval(dotsTimer)
    if (!alive) {
      stageDots.value = ''
      return
    }
    let n = 0
    dotsTimer = setInterval(() => {
      n = (n + 1) % 4
      stageDots.value = '.'.repeat(n)
    }, 420)
  },
  { immediate: true }
)
onBeforeUnmount(() => clearInterval(dotsTimer))

const expanded = reactive({})
// 初始默认：最新一条流中消息全展开；完成的消息折叠，让读者先看总结
watch(
  () => extras.value.subquestions,
  (list) => {
    if (!Array.isArray(list)) return
    for (const sq of list) {
      if (!(sq.id in expanded)) {
        expanded[sq.id] = props.streaming
      }
    }
  },
  { immediate: true, deep: true }
)

function toggle(id) {
  if (!id) return
  expanded[id] = !expanded[id]
}

function tableData(sq) {
  const cols = sq.columns || []
  return (sq.rows || []).map((r) => {
    const o = {}
    cols.forEach((c, i) => {
      const v = r[i]
      o[c] = v === null || v === undefined ? '' : v
    })
    return o
  })
}

async function copySql(sql) {
  try {
    await navigator.clipboard.writeText(sql)
    ElMessage.success(t('bubble.copiedSql'))
  } catch {
    ElMessage.warning(t('bubble.copyFail'))
  }
}

const renderedSummary = computed(() => toSafeHtml(extras.value.summary_markdown || ''))

const allCharts = computed(() => {
  const list = extras.value.charts
  if (Array.isArray(list) && list.length) return list
  if (extras.value.chart) return [extras.value.chart]
  return []
})
const primaryChart = computed(() => {
  if (!allCharts.value.length) return null
  const pid = extras.value.primary_chart_id
  return (
    allCharts.value.find((c) => c.subquestion_id === pid) ||
    allCharts.value.find((c) => c.role === 'primary') ||
    allCharts.value[0] ||
    null
  )
})
const secondaryCharts = computed(() => {
  const pid = primaryChart.value?.subquestion_id
  return allCharts.value.filter((c) => c.subquestion_id !== pid)
})

/**
 * 极简 Markdown 渲染（标题/列表/加粗/代码/表格/段落）；避免引入额外依赖。
 * 若未来需要完整支持，可接入 marked。
 */
function toSafeHtml(md) {
  if (!md) return ''
  let text = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  // 代码块 ```
  text = text.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code}</code></pre>`)
  // inline code
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  // markdown 表格：先处理，避免被 paragraph 逻辑干扰
  text = text.replace(/((?:^|\n)(\|[^\n]+\|)(\n\|[-: |]+\|)(\n\|[^\n]+\|)*)/g, (block) => {
    const lines = block.trim().split('\n').filter((l) => l.trim().startsWith('|'))
    if (lines.length < 2) return block
    const sepIdx = lines.findIndex((l) => /^\|[\s\-:| ]+\|$/.test(l.trim()))
    if (sepIdx < 0) return block
    const headers = lines[0].split('|').slice(1, -1).map((h) => h.trim())
    const dataLines = lines.slice(sepIdx + 1)
    const thead = `<thead><tr>${headers.map((h) => `<th>${h}</th>`).join('')}</tr></thead>`
    const tbody = `<tbody>${dataLines.map((l) => {
      const cells = l.split('|').slice(1, -1).map((c) => c.trim())
      return `<tr>${cells.map((c) => `<td>${c}</td>`).join('')}</tr>`
    }).join('')}</tbody>`
    return `\n<div class="md-table-wrap"><table>${thead}${tbody}</table></div>`
  })
  // headings
  text = text.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>')
  text = text.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>')
  text = text.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>')
  text = text.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>')
  text = text.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>')
  text = text.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>')
  // bold / italics
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  // lists (- / *)
  text = text.replace(/(?:^|\n)((?:\s*[-*]\s+.+\n?)+)/g, (block) => {
    const items = block
      .trim()
      .split('\n')
      .map((line) => line.replace(/^\s*[-*]\s+/, '').trim())
      .filter(Boolean)
      .map((x) => `<li>${x}</li>`)
      .join('')
    return `\n<ul>${items}</ul>`
  })
  // paragraphs
  text = text
    .split(/\n{2,}/)
    .map((chunk) => {
      if (/^<(h\d|ul|ol|pre|blockquote|div)/i.test(chunk.trim())) return chunk
      return `<p>${chunk.replace(/\n/g, '<br/>')}</p>`
    })
    .join('\n')
  return text
}
</script>

<style scoped>
.xq-bubble {
  margin-bottom: 20px;
}
.xq-bubble-user,
.xq-bubble-assistant {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.xq-bubble-user {
  flex-direction: row-reverse;
}
.xq-bubble-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 13px;
  color: #fff;
  margin-top: 2px;
}
.user-avatar {
  background: #2563eb;
}
.assistant-avatar {
  background: linear-gradient(135deg, #059669, #10b981);
}
.xq-bubble-body {
  flex: 1;
  min-width: 0;
  max-width: min(920px, 100%);
}
.xq-bubble-user .xq-bubble-body {
  display: flex;
  justify-content: flex-end;
}
.xq-bubble-content {
  background: #2563eb;
  color: #fff;
  padding: 10px 14px;
  border-radius: 12px 2px 12px 12px;
  max-width: 80%;
  word-break: break-word;
  white-space: pre-wrap;
  line-height: 1.55;
}

.stage-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.plan-card {
  background: #f0fdf4;
  border-color: #bbf7d0;
}
.summary-card {
  background: #fff;
  border-color: #d1d5db;
}
.stage-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 6px;
}
.stage-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #9ca3af;
}
.stage-dot.is-active {
  background: #10b981;
  animation: pulse 1.2s ease-in-out infinite;
}
.stage-dot.success {
  background: #10b981;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.45; transform: scale(0.85); }
}
.stage-body {
  font-size: 13.5px;
  color: #374151;
  line-height: 1.6;
}

.subq-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}
.subq-item {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 10px 12px;
  transition: border-color 0.15s ease;
}
.subq-item.sq-ok { border-left: 3px solid #10b981; }
.subq-item.sq-error { border-left: 3px solid #ef4444; background: #fef2f2; }
.subq-item.sq-running,
.subq-item.sq-pending { border-left: 3px solid #f59e0b; }
.subq-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.subq-idx {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #eef2ff;
  color: #4f46e5;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.subq-q {
  flex: 1;
  font-size: 13.5px;
  color: #111827;
  font-weight: 500;
}
.subq-status {
  display: inline-flex;
  align-items: center;
  color: #6b7280;
}
.subq-status .is-loading {
  animation: spin 1s linear infinite;
}
@keyframes spin { from {transform: rotate(0)} to {transform: rotate(360deg)} }
.subq-expand {
  color: #9ca3af;
  transition: transform 0.15s ease;
}
.subq-expand.is-open {
  transform: rotate(180deg);
}
.subq-purpose {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
  padding-left: 28px;
}
.subq-body {
  margin-top: 10px;
  padding-left: 28px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.subq-sql {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 8px 10px;
}
.subq-sql-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 4px;
}
.subq-sql pre {
  margin: 0;
  max-height: 200px;
  overflow: auto;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}
.subq-error {
  background: #fef2f2;
  color: #991b1b;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12.5px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.subq-result-meta {
  font-size: 11.5px;
  color: #94a3b8;
  margin-top: 4px;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 12px 0 6px;
  font-weight: 600;
  color: #111827;
}
.markdown-body :deep(h2) { font-size: 15px; }
.markdown-body :deep(h3) { font-size: 14px; }
.markdown-body :deep(p) { margin: 6px 0; }
.markdown-body :deep(ul) {
  margin: 6px 0 6px 18px;
  padding: 0;
}
.markdown-body :deep(li) { margin: 2px 0; }
.markdown-body :deep(code) {
  background: #f3f4f6;
  padding: 1px 4px;
  border-radius: 4px;
  font-size: 12.5px;
  color: #0f172a;
}
.markdown-body :deep(pre) {
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 8px 10px;
  overflow: auto;
}
.markdown-body :deep(strong) { color: #0f172a; }
.markdown-body :deep(.md-table-wrap) {
  overflow-x: auto;
  margin: 8px 0;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.markdown-body :deep(th) {
  background: #f3f4f6;
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  color: #374151;
  border-bottom: 1px solid #e5e7eb;
  white-space: nowrap;
}
.markdown-body :deep(td) {
  padding: 7px 12px;
  border-bottom: 1px solid #f3f4f6;
  color: #4b5563;
}
.markdown-body :deep(tr:last-child td) {
  border-bottom: none;
}
.markdown-body :deep(tr:nth-child(even) td) {
  background: #f9fafb;
}

.follow-ups {
  margin-top: 4px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 10px;
}
.follow-ups-title {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
}
.follow-ups-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.xq-bubble-select {
  margin-bottom: 6px;
  text-align: right;
}

.xq-stage-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px 6px 10px;
  border-radius: 999px;
  font-size: 12.5px;
  line-height: 1.2;
  color: #065f46;
  background: linear-gradient(90deg, #ecfdf5, #d1fae5);
  border: 1px solid #a7f3d0;
  box-shadow: 0 1px 2px rgba(16, 185, 129, 0.08);
  margin-bottom: 10px;
  animation: chip-pop 0.25s ease;
}
.xq-stage-chip.chip-parse {
  color: #1e3a8a;
  background: linear-gradient(90deg, #eff6ff, #dbeafe);
  border-color: #bfdbfe;
}
.xq-stage-chip.chip-chart {
  color: #92400e;
  background: linear-gradient(90deg, #fffbeb, #fef3c7);
  border-color: #fde68a;
}
.xq-stage-chip.chip-summary {
  color: #5b21b6;
  background: linear-gradient(90deg, #f5f3ff, #ede9fe);
  border-color: #ddd6fe;
}
.xq-stage-spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-top-color: transparent;
  animation: chip-spin 0.9s linear infinite;
  flex-shrink: 0;
}
.xq-stage-text {
  font-weight: 500;
}
.xq-stage-dots {
  display: inline-block;
  width: 18px;
  text-align: left;
  opacity: 0.7;
}
@keyframes chip-spin { to { transform: rotate(360deg); } }
@keyframes chip-pop {
  from { opacity: 0; transform: translateY(-2px); }
  to { opacity: 1; transform: translateY(0); }
}
.xq-bubble-select :deep(.el-checkbox__label) {
  font-size: 12px;
  color: #64748b;
}

.xq-chart-primary {
  margin-bottom: 10px;
}
.xq-chart-secondary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.xq-chart-secondary-item { min-width: 0; }

/* 骨架屏：图表后、summary 前 */
.summary-skeleton {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 14px 16px 18px;
  margin-bottom: 12px;
}
.sk-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.sk-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e5e7eb;
  flex-shrink: 0;
}
.sk-title-bar {
  height: 14px;
  width: 110px;
  border-radius: 6px;
  background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 50%, #f3f4f6 75%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
.sk-line {
  height: 11px;
  border-radius: 4px;
  margin-bottom: 9px;
  background: linear-gradient(90deg, #f3f4f6 25%, #e9ebee 50%, #f3f4f6 75%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s ease-in-out infinite;
}
.sk-line--90 { width: 90%; }
.sk-line--85 { width: 85%; }
.sk-line--80 { width: 80%; }
.sk-line--75 { width: 75%; }
.sk-line--60 { width: 60%; animation-delay: 0.1s; }
.sk-line--50 { width: 50%; animation-delay: 0.2s; }
@keyframes sk-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* 流式 summary 打字机效果 */
.summary-streaming {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
  font-size: 13.5px;
  color: #374151;
}
.summary-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: #10b981;
  margin-left: 1px;
  vertical-align: text-bottom;
  animation: cursor-blink 0.8s step-end infinite;
}
@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.failure-note {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #991b1b;
  font-size: 13px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 8px 12px;
}
</style>
