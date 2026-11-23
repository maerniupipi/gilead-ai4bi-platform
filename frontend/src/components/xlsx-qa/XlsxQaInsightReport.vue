<template>
  <div class="xq-insight" :class="{ 'is-generating': streaming }">
    <div class="xq-insight-body">
      <el-alert v-if="errorBanner" type="error" :closable="false" show-icon class="xq-insight-alert">
        {{ errorBanner }}
      </el-alert>

      <!-- ====== Pipeline（生成期置顶显示；与报告分区隔离，报告单独滚动） ====== -->
      <Transition name="pipeline-fade">
      <div v-if="hasAttempted && !reportFullyLoaded" class="xq-pipeline-wrap">
        <div class="xq-pipeline-glass">
          <div class="xq-pipeline-bg-grid" aria-hidden="true" />
          <div class="xq-pipeline-toolbar">
            <el-button text type="primary" class="xq-pipeline-back" @click="onClose">
              <el-icon><ArrowLeft /></el-icon>
              {{ t('insight.backChat') }}
            </el-button>
            <span class="xq-pipeline-hint" :title="statusHint || ''">{{ statusHint || '\u00a0' }}</span>
            <div class="xq-pipeline-actions">
              <el-button size="small" :disabled="!streaming" @click="abortStream">
                {{ t('insight.stop') }}
              </el-button>
              <el-button size="small" type="primary" plain :loading="streaming" @click="retry">
                {{
                  streaming ? t('insight.working') : hasAttempted ? t('insight.regenerate') : t('insight.start')
                }}
              </el-button>
            </div>
          </div>
          <div class="xq-pipeline-flow">
            <template v-for="(p, idx) in displayPhaseList" :key="p.key">
              <div
                class="xq-pipe-node"
                :class="{
                  'is-done': p.visualDone,
                  'is-active': p.visualActive,
                  'is-pending': !p.visualDone && !p.visualActive
                }"
              >
                <div class="xq-pipe-node-row">
                  <div class="xq-pipe-node-main">
                    <div class="xq-pipe-ring">
                      <svg class="xq-pipe-ring-svg" viewBox="0 0 44 44">
                        <circle class="xq-pipe-ring-track" cx="22" cy="22" r="19" />
                        <circle
                          class="xq-pipe-ring-fill"
                          cx="22" cy="22" r="19"
                          :style="{ strokeDashoffset: p.visualDone ? 0 : p.visualActive ? 40 : 120 }"
                        />
                      </svg>
                      <span class="xq-pipe-icon">
                        <Transition name="ico-flip" mode="out-in">
                          <span v-if="p.visualDone" key="chk" class="xq-pipe-check">
                            <svg viewBox="0 0 16 16" fill="none"><path d="M3 8.5l3.5 3L13 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
                          </span>
                          <span v-else-if="p.visualActive" key="spin" class="xq-pipe-spinner" />
                          <span v-else key="num" class="xq-pipe-num">{{ idx + 1 }}</span>
                        </Transition>
                      </span>
                    </div>
                    <div class="xq-pipe-label">{{ p.label }}</div>
                  </div>
                  <div class="xq-pipe-subs">
                    <div
                      v-for="(sub, si) in p.subs"
                      :key="si"
                      class="xq-pipe-sub"
                      :class="{
                        'is-done': p.visualDone || (p.visualActive && si < p.activeSubIdx),
                        'is-active': p.visualActive && si === p.activeSubIdx
                      }"
                    >
                      <span class="xq-pipe-sub-dot" />
                      <span class="xq-pipe-sub-text">{{ sub }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div
                v-if="idx < displayPhaseList.length - 1"
                class="xq-pipe-connector"
                :class="{ 'is-done': p.visualDone }"
                aria-hidden="true"
              >
                <div class="xq-pipe-conn-line" />
                <div v-if="p.visualDone" class="xq-pipe-conn-particle" />
              </div>
            </template>
          </div>
        </div>
      </div>
      </Transition>

      <!-- 仅此区域纵向滚动；外层页面与工作台容器不再滚动 -->
      <div class="xq-insight-scroll">
        <div v-if="reportFullyLoaded" class="xq-post-chrome">
          <el-button text type="primary" class="xq-post-back" @click="onClose">
            <el-icon><ArrowLeft /></el-icon>
            {{ t('insight.backChat') }}
          </el-button>
          <div class="xq-post-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="streaming"
              @click="emit('export-ppt')"
            >
              导出 PPT
            </el-button>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="streaming"
              @click="emit('export-pdf')"
            >
              导出 PDF
            </el-button>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="streaming"
              :loading="streaming"
              @click="retry"
            >
              {{ streaming ? t('insight.working') : t('insight.regenerate') }}
            </el-button>
          </div>
        </div>
        <div v-if="showPerspectiveSkeleton" class="xq-pre-skeleton xq-pre-skeleton--perspectives">
          <div class="xq-pre-sk-head">
            <div class="xq-pre-sk-dot" />
            <div>
              <div class="xq-pre-sk-title">{{ t('insight.phase.profile') }}</div>
              <div class="xq-pre-sk-sub">{{ statusHint || t('insight.phase.profile.sub1') }}</div>
            </div>
          </div>
          <div class="xq-pre-sk-table" aria-hidden="true">
            <div class="xq-pre-sk-row xq-pre-sk-row--head">
              <span class="xq-pre-sk-cell w-24" />
              <span class="xq-pre-sk-cell w-32" />
              <span class="xq-pre-sk-cell w-22" />
              <span class="xq-pre-sk-cell w-18" />
            </div>
            <div v-for="i in 4" :key="`role-sk-${i}`" class="xq-pre-sk-row">
              <span class="xq-pre-sk-cell w-20" />
              <span class="xq-pre-sk-cell w-36" />
              <span class="xq-pre-sk-cell w-26" />
              <span class="xq-pre-sk-cell w-14" />
            </div>
          </div>
        </div>
        <div v-if="showPerspectivePanel" class="xq-role-perspective-panel">
          <div class="xq-role-perspective-head">
            <div class="xq-role-perspective-dot" />
            <div class="xq-role-perspective-head-text">
              <div class="xq-role-perspective-title">{{ t('insight.phase.roles') }}</div>
              <div class="xq-role-perspective-sub">{{ perspectivePanelSubtitle }}</div>
            </div>
          </div>
          <div class="xq-role-preview-grid">
            <article
              v-for="slot in perspectivePreviewSlots"
              :key="slot.role"
              class="xq-role-preview-card"
            >
              <div class="xq-role-preview-card-head">
                <span class="xq-role-preview-badge">{{ slot.badge }}</span>
                <span class="xq-role-preview-name" :title="slot.label">{{ slot.label }}</span>
                <span
                  v-if="slot.roleDone && !slot.errorText"
                  class="xq-role-preview-status is-done"
                  aria-hidden="true"
                >✓</span>
                <span
                  v-else-if="slot.errorText"
                  class="xq-role-preview-status is-err"
                  aria-hidden="true"
                >!</span>
                <span
                  v-else-if="streaming"
                  class="xq-role-preview-status is-wait"
                  aria-hidden="true"
                >…</span>
              </div>
              <div v-if="slot.chart" class="xq-role-preview-chart">
                <XlsxQaChart :chart="slot.chart" size="small" />
              </div>
              <div v-else class="xq-role-preview-chart-fallback">
                {{ t('insight.previewNoChart') }}
              </div>
              <p v-if="slot.errorText" class="xq-role-preview-err">{{ slot.errorText }}</p>
              <p v-else-if="slot.summaryText" class="xq-role-preview-summary">{{ slot.summaryText }}</p>
            </article>
          </div>
          <p v-if="showDimensionPlanHint" class="xq-role-plan-hint">
            {{ statusHint || t('insight.phase.plan.sub1') }}
          </p>
        </div>
        <div v-if="dimensions.length > 0" class="xq-insight-stream">
      <article class="xq-stream-card xq-stream-card--lead">
        <div class="xq-stream-card-head">
          <h4 class="xq-stream-card-title">{{ t('insight.finalTitle') }}</h4>
          <div v-if="summaryRibbon" class="xq-stream-ribbon">{{ summaryRibbon }}</div>
        </div>
        <div
          v-if="renderedFinal"
          class="markdown-body xq-insight-md"
          v-html="renderedFinal"
        />
        <div v-else-if="showSummarySkeleton" class="xq-skeleton-wrap">
          <p class="xq-skeleton-cap">{{ t('insight.skeletonSummary') }}</p>
          <div class="xq-fishbone" aria-hidden="true">
            <div class="xq-fishbone-spine" />
            <div class="xq-fishbone-rows">
              <div class="xq-fishbone-row is-l"><span class="xq-fishbone-chip w-a" /></div>
              <div class="xq-fishbone-row is-r"><span class="xq-fishbone-chip w-b" /></div>
              <div class="xq-fishbone-row is-l"><span class="xq-fishbone-chip w-c" /></div>
              <div class="xq-fishbone-row is-r"><span class="xq-fishbone-chip w-b" /></div>
              <div class="xq-fishbone-row is-l"><span class="xq-fishbone-chip w-d" /></div>
              <div class="xq-fishbone-row is-r"><span class="xq-fishbone-chip w-a" /></div>
            </div>
          </div>
        </div>
      </article>

      <article
        v-for="dim in dimensions"
        :key="dim.id"
        class="xq-stream-card"
      >
        <div class="xq-insight-dim-head">
          <h4 class="xq-stream-card-title xq-insight-dim-title" :title="dim.title || dim.display_title || dim.id">
            {{ dim.display_title || dim.title || dim.id }}
          </h4>
          <el-tag v-if="dim.score != null" size="small" type="info" effect="plain">
            {{ t('insight.dimScore', { n: dim.score }) }}
          </el-tag>
        </div>
        <p v-if="dim.why_selected" class="xq-insight-dim-why">{{ dim.why_selected }}</p>

        <div v-if="chartsForDim(dim.id).length" class="xq-insight-charts">
          <XlsxQaChart
            v-for="(ch, gi) in chartsForDim(dim.id)"
            :key="`${dim.id}-${gi}`"
            :chart="ch"
            size="small"
          />
        </div>

        <div class="xq-insight-evidence-meta">
          <span v-if="!briefEvidence(dim.id).length" class="xq-ev-tag muted">
            {{ t('insight.evidenceWaiting') }}
          </span>
          <span v-for="ev in briefEvidence(dim.id)" :key="ev.question_id" class="xq-ev-tag">
            {{ ev.business_question }}
            <template v-if="ev.supported === false"> · {{ t('insight.evidenceFail') }}</template>
          </span>
        </div>

        <div
          v-if="(dimTexts[dim.id] || '').trim()"
          class="markdown-body xq-insight-md"
          v-html="renderedDimMd(dim.id)"
        />
        <div v-else-if="dimShowSkeleton(dim.id)" class="xq-skeleton-wrap">
          <p class="xq-skeleton-cap">{{ t('insight.skeletonDimension') }}</p>
          <div class="xq-fishbone xq-fishbone--sm" aria-hidden="true">
            <div class="xq-fishbone-spine" />
            <div class="xq-fishbone-rows">
              <div class="xq-fishbone-row is-l"><span class="xq-fishbone-chip w-b" /></div>
              <div class="xq-fishbone-row is-r"><span class="xq-fishbone-chip w-c" /></div>
              <div class="xq-fishbone-row is-l"><span class="xq-fishbone-chip w-a" /></div>
              <div class="xq-fishbone-row is-r"><span class="xq-fishbone-chip w-d" /></div>
            </div>
          </div>
        </div>
      </article>

          <footer v-if="done && elapsedMs != null" class="xq-insight-footer">
            {{ t('insight.doneHint', { s: (elapsedMs / 1000).toFixed(1) }) }}
          </footer>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowLeft } from '@element-plus/icons-vue'
import { renderSimpleMarkdown } from '@/utils/markdown'
import {
  fetchInsightReport,
  fetchInsightShareReport,
  runInsightStream,
  runInsightShareStream
} from '@/utils/xlsxQaSse'
import XlsxQaChart from './XlsxQaChart.vue'
import { useXqI18n } from '@/utils/xlsxQaI18n'

const props = defineProps({
  moduleId: { type: Number, default: null },
  shareToken: { type: String, default: '' }
})

const emit = defineEmits(['close', 'streaming', 'done', 'error', 'export-ppt', 'export-pdf'])

const { t } = useXqI18n()

const streaming = ref(false)
const hasAttempted = ref(false)
const done = ref(false)
const abortCtrl = ref(null)
const isShareMode = computed(() => !!(props.shareToken || '').trim())

const statusHint = ref('')
const errorBanner = ref('')

const roleCards = ref([])
const profileBundle = ref(null)
const dimensions = ref([])
const evidenceByDim = ref({})
const dimTexts = ref({})
const finalMd = ref('')
const elapsedMs = ref(null)
const finishedDimIds = ref({})

const phaseProfile = ref(false)
const phaseRoles = ref(0)
const phasePlanner = ref(false)
const phaseEvidence = ref(false)
const phaseDimAnalysis = ref(false)
const phaseFinalActive = ref(false)
const phaseFinalDone = ref(false)

const reportFullyLoaded = ref(false)
const _delayTimers = ref([])
/** phase key → interval id（避免跨阶段叠加导致子步骤一跳到底） */
const _subIntervalByKey = {}

const visualPhaseState = ref({
  p: { done: false, active: false },
  r: { done: false, active: false },
  l: { done: false, active: false },
  q: { done: false, active: false },
  f: { done: false, active: false }
})

const subTickIndex = ref({ p: -1, r: -1, l: -1, q: -1, f: -1 })

/** 后端标记完成后，视觉上至少停留多久再显示「已完成」（防止一闪而过） */
const MIN_PHASE_DISPLAY_MS = 2800
/** 同一阶段内两条子步骤之间的最小间隔 */
const SUB_STEP_MS = 850

/** 防止 phaseList watch 在同一 vs.done=false 窗口内重复排队多个 timeout */
const phaseDoneTimersScheduled = ref(new Set())

function _scheduleDelayedPhaseDone(key) {
  const tid = setTimeout(() => {
    visualPhaseState.value = {
      ...visualPhaseState.value,
      [key]: { ...visualPhaseState.value[key], done: true, active: false }
    }
    phaseDoneTimersScheduled.value.delete(key)
  }, MIN_PHASE_DISPLAY_MS)
  _delayTimers.value.push(tid)
}

function _clearSubInterval(key) {
  const tid = _subIntervalByKey[key]
  if (tid != null) {
    clearInterval(tid)
    delete _subIntervalByKey[key]
  }
}

function _startSubTick(key, subCount) {
  _clearSubInterval(key)
  if (subCount <= 0) return

  subTickIndex.value = { ...subTickIndex.value, [key]: 0 }

  let step = 0
  const tid = setInterval(() => {
    step++
    if (step >= subCount) {
      _clearSubInterval(key)
      return
    }
    subTickIndex.value = { ...subTickIndex.value, [key]: step }
  }, SUB_STEP_MS)

  _subIntervalByKey[key] = tid
}

function _clearAllTimers() {
  _delayTimers.value.forEach(clearTimeout)
  _delayTimers.value = []
  Object.keys(_subIntervalByKey).forEach(_clearSubInterval)
  phaseDoneTimersScheduled.value.clear()
}

function resetState() {
  _clearAllTimers()
  errorBanner.value = ''
  roleCards.value = []
  profileBundle.value = null
  dimensions.value = []
  evidenceByDim.value = {}
  dimTexts.value = {}
  finalMd.value = ''
  elapsedMs.value = null
  finishedDimIds.value = {}
  done.value = false
  statusHint.value = ''
  phaseProfile.value = false
  phaseRoles.value = 0
  phasePlanner.value = false
  phaseEvidence.value = false
  phaseDimAnalysis.value = false
  phaseFinalActive.value = false
  phaseFinalDone.value = false
  reportFullyLoaded.value = false
  visualPhaseState.value = {
    p: { done: false, active: false },
    r: { done: false, active: false },
    l: { done: false, active: false },
    q: { done: false, active: false },
    f: { done: false, active: false }
  }
  subTickIndex.value = { p: -1, r: -1, l: -1, q: -1, f: -1 }
  phaseDoneTimersScheduled.value.clear()
}

const phaseList = computed(() => [
  { key: 'p', label: t('insight.phase.profile'), done: phaseProfile.value, active: !phaseProfile.value && streaming.value },
  {
    key: 'r',
    label: t('insight.phase.roles'),
    done: phaseRoles.value >= 4,
    active: phaseProfile.value && phaseRoles.value < 4 && streaming.value
  },
  {
    key: 'l',
    label: t('insight.phase.plan'),
    done: phasePlanner.value,
    active: phaseRoles.value >= 4 && !phasePlanner.value && streaming.value
  },
  {
    key: 'q',
    label: t('insight.phase.evidence'),
    done: dimensions.value.length > 0 && finishedDimCount.value >= dimensions.value.length,
    active: phasePlanner.value && finishedDimCount.value < dimensions.value.length && streaming.value
  },
  {
    key: 'f',
    label: t('insight.phase.final'),
    done: phaseFinalDone.value,
    active: phaseFinalActive.value && streaming.value
  }
])

const phaseSubs = computed(() => ({
  p: [t('insight.phase.profile.sub1'), t('insight.phase.profile.sub2'), t('insight.phase.profile.sub3')],
  r: [t('insight.phase.roles.sub1'), t('insight.phase.roles.sub2'), t('insight.phase.roles.sub3'), t('insight.phase.roles.sub4')],
  l: [t('insight.phase.plan.sub1'), t('insight.phase.plan.sub2'), t('insight.phase.plan.sub3')],
  q: [t('insight.phase.evidence.sub1'), t('insight.phase.evidence.sub2'), t('insight.phase.evidence.sub3')],
  f: [t('insight.phase.final.sub1'), t('insight.phase.final.sub2'), t('insight.phase.final.sub3')]
}))

const displayPhaseList = computed(() =>
  phaseList.value.map((p) => {
    const vs = visualPhaseState.value[p.key]
    return {
      ...p,
      visualDone: vs?.done ?? false,
      visualActive: vs?.active ?? false,
      subs: phaseSubs.value[p.key] || [],
      activeSubIdx: subTickIndex.value[p.key] ?? -1
    }
  })
)

watch(
  phaseList,
  (list) => {
    for (const p of list) {
      const vs = visualPhaseState.value[p.key]
      if (p.active && !vs.active && !vs.done) {
        visualPhaseState.value = {
          ...visualPhaseState.value,
          [p.key]: { ...vs, active: true }
        }
        _startSubTick(p.key, (phaseSubs.value[p.key] || []).length)
      }
      if (p.done && !vs.done && !phaseDoneTimersScheduled.value.has(p.key)) {
        phaseDoneTimersScheduled.value.add(p.key)
        _clearSubInterval(p.key)
        _scheduleDelayedPhaseDone(p.key)
      }
    }
  },
  { deep: true }
)

watch(done, (v) => {
  if (v) {
    const lastPhase = phaseList.value[phaseList.value.length - 1]
    const lastVs = visualPhaseState.value[lastPhase.key]
    const waitLastVisual = lastVs.done ? 0 : MIN_PHASE_DISPLAY_MS
    const tid = setTimeout(() => {
      reportFullyLoaded.value = true
    }, waitLastVisual + 900)
    _delayTimers.value.push(tid)
  }
})

const finishedDimCount = computed(() => Object.values(finishedDimIds.value).filter(Boolean).length)
const renderedFinal = computed(() => renderInsightMarkdown(finalMd.value))

function normalizeBusinessNumbers(md) {
  return String(md || '').replace(/-?\d+\.\d{2,}/g, (m) => Number(m).toFixed(1))
}

function renderInsightMarkdown(md) {
  return renderSimpleMarkdown(normalizeBusinessNumbers(md))
}

const hasFinalText = computed(() => !!(finalMd.value || '').trim())

const showPerspectiveSkeleton = computed(() => {
  return hasAttempted.value && streaming.value && !dimensions.value.length && !profileBundle.value
})

const showPerspectivePanel = computed(() => {
  return hasAttempted.value && streaming.value && !dimensions.value.length && !!profileBundle.value
})

const showDimensionPlanHint = computed(
  () => showPerspectivePanel.value && phaseRoles.value >= 4 && !dimensions.value.length
)

const perspectivePanelSubtitle = computed(() => {
  if (phaseRoles.value >= 4) return t('insight.previewPlanWait')
  return t('insight.previewProfileSubtitle')
})

const previewChartsByRole = computed(() => buildPreviewChartsFromProfile(profileBundle.value, t))

const perspectivePreviewSlots = computed(() => {
  const charts = previewChartsByRole.value
  return ROLE_PREVIEW_ORDER.map((def, idx) => {
    const rc = roleCards.value.find((r) => r.role === def.key)
    const summary = (rc?.role_summary || '').trim()
    const err = typeof rc?.error === 'string' ? rc.error.trim() : ''
    const finished = !!(rc && (rc.done || err))
    const summaryText =
      finished && !err && summary ? (summary.length > 140 ? summary.slice(0, 137) + '…' : summary) : ''
    return {
      role: def.key,
      label: rc?.name || t(def.labelKey),
      badge: String(idx + 1).padStart(2, '0'),
      chart: charts[def.key],
      roleDone: finished && !err,
      summaryText,
      errorText: err || ''
    }
  })
})

const showSummarySkeleton = computed(() => {
  if (hasFinalText.value || !dimensions.value.length) return false
  return streaming.value
})

const summaryRibbon = computed(() => {
  if (hasFinalText.value || !dimensions.value.length || !streaming.value) return ''
  if (phaseFinalActive.value) return t('insight.finalStreaming')
  const allAnalyzed = dimensions.value.every((d) => finishedDimIds.value[d.id])
  if (!allAnalyzed) return t('insight.finalWaiting')
  return t('insight.skeletonAnalyzing')
})

function dimShowSkeleton(dimId) {
  if (finishedDimIds.value[dimId]) return false
  if ((dimTexts.value[dimId] || '').trim()) return false
  return streaming.value
}

function renderedDimMd(dimId) {
  return renderInsightMarkdown(dimTexts.value[dimId] || '')
}

function chartsForDim(dimId) {
  const evs = evidenceByDim.value[dimId] || []
  return evs.filter((e) => e.supported && e.chart && e.chart.chart_type && e.chart.chart_type !== 'none').map((e) => e.chart)
}

function briefEvidence(dimId) {
  return evidenceByDim.value[dimId] || []
}

/** 与步骤条子文案顺序一致：市场 → 运营 → 管理 → 风控（对应后端 sales / operations / management / boss） */
const ROLE_PREVIEW_ORDER = [
  { key: 'sales', labelKey: 'insight.phase.roles.sub1' },
  { key: 'operations', labelKey: 'insight.phase.roles.sub2' },
  { key: 'management', labelKey: 'insight.phase.roles.sub3' },
  { key: 'boss', labelKey: 'insight.phase.roles.sub4' }
]

function buildPreviewChartsFromProfile(profile, translate) {
  const out = { sales: null, operations: null, management: null, boss: null }
  const tn = typeof translate === 'function' ? translate : (x) => x
  if (!profile?.sheets?.length) return out

  const sheet = profile.sheets[0]
  const samples = sheet.top_value_samples || {}
  const numeric = sheet.numeric_summaries || {}
  const timeCandidates = sheet.time_candidates || []
  const sampleKeys = Object.keys(samples).filter((k) => Array.isArray(samples[k]) && samples[k].length)

  const mc = tn('insight.previewMetricCount')
  const dimColNum = tn('insight.previewMetricDim')
  const valColNum = tn('insight.previewMetricRef')

  const shortCol = (k) => (String(k).length > 14 ? String(k).slice(0, 13) + '…' : String(k))

  function pairsToRows(pairs) {
    return pairs.slice(0, 10).map(([val, cnt]) => [String(val ?? '').slice(0, 22), cnt])
  }

  function barChart(colKey, pairs, tagTitle) {
    const label = shortCol(colKey)
    const rows = pairsToRows(pairs)
    return {
      chart_type: 'bar',
      title: `${tagTitle} · ${label}`,
      columns: [label, mc],
      rows,
      dimension_field: label,
      metric_fields: [mc],
      explain: ''
    }
  }

  function lineChart(colKey, pairs, tagTitle) {
    const label = shortCol(colKey)
    const sorted = [...pairs].sort((a, b) => String(a[0]).localeCompare(String(b[0]), 'zh-CN'))
    const rows = pairsToRows(sorted)
    return {
      chart_type: 'line',
      title: `${tagTitle} · ${label}`,
      columns: [label, mc],
      rows,
      dimension_field: label,
      metric_fields: [mc],
      explain: ''
    }
  }

  function pieChart(colKey, pairs, tagTitle) {
    const label = shortCol(colKey)
    const rows = pairsToRows(pairs)
    return {
      chart_type: 'pie',
      title: `${tagTitle} · ${label}`,
      columns: [label, mc],
      rows,
      dimension_field: label,
      metric_fields: [mc],
      explain: ''
    }
  }

  function numericBar(tagTitle) {
    const entries = Object.entries(numeric).slice(0, 10)
    if (!entries.length) return null
    const rows = entries.map(([k, v]) => {
      let ref = v?.avg
      if (ref == null) ref = v?.max
      if (ref == null) ref = v?.min
      const num = typeof ref === 'number' ? Math.round(ref * 10) / 10 : ref
      return [shortCol(k), num]
    })
    return {
      chart_type: 'bar',
      title: `${tagTitle}`,
      columns: [dimColNum, valColNum],
      rows,
      dimension_field: dimColNum,
      metric_fields: [valColNum],
    }
  }

  if (sampleKeys[0]) {
    out.sales = barChart(sampleKeys[0], samples[sampleKeys[0]], tn('insight.previewTagMarket'))
  }

  const timeCol = timeCandidates.find((c) => samples[c])
  if (timeCol && samples[timeCol]?.length >= 2) {
    out.operations = lineChart(timeCol, samples[timeCol], tn('insight.previewTagOpsTime'))
  } else if (sampleKeys[1]) {
    out.operations = barChart(sampleKeys[1], samples[sampleKeys[1]], tn('insight.previewTagOps'))
  } else if (sampleKeys[0] && samples[sampleKeys[0]].length >= 2) {
    out.operations = pieChart(sampleKeys[0], samples[sampleKeys[0]], tn('insight.previewTagShare'))
  }

  out.management = numericBar(tn('insight.previewTagMgmtNum'))
  if (!out.management && sampleKeys[2]) {
    out.management = barChart(sampleKeys[2], samples[sampleKeys[2]], tn('insight.previewTagMgmt'))
  }

  if (sampleKeys[3]) {
    const pairs = samples[sampleKeys[3]]
    out.boss =
      pairs.length >= 3
        ? pieChart(sampleKeys[3], pairs, tn('insight.previewTagRiskPie'))
        : barChart(sampleKeys[3], pairs, tn('insight.previewTagRisk'))
  }

  const roles = ['sales', 'operations', 'management', 'boss']
  let skIdx = 0
  const fallbackTag = tn('insight.previewTagFallback')
  for (const r of roles) {
    if (out[r]) continue
    while (skIdx < sampleKeys.length) {
      const k = sampleKeys[skIdx++]
      const pairs = samples[k]
      if (pairs?.length) {
        out[r] = barChart(k, pairs, fallbackTag)
        break
      }
    }
    if (!out[r] && Object.keys(numeric).length) {
      out[r] = numericBar(fallbackTag)
    }
  }

  return out
}

function upsertRole(next) {
  if (!next?.role) return
  const idx = roleCards.value.findIndex((r) => r.role === next.role)
  if (idx >= 0) {
    const copy = [...roleCards.value]
    copy[idx] = { ...copy[idx], ...next }
    roleCards.value = copy
  } else {
    roleCards.value = [...roleCards.value, next]
  }
}

function hydrateSavedReport(saved) {
  if (!saved?.exists) return false
  roleCards.value = Array.isArray(saved.role_cards) ? saved.role_cards : []
  dimensions.value = Array.isArray(saved.dimensions) ? saved.dimensions : []
  evidenceByDim.value = saved.evidence && typeof saved.evidence === 'object' ? saved.evidence : {}
  dimTexts.value = saved.dim_texts && typeof saved.dim_texts === 'object' ? saved.dim_texts : {}
  finalMd.value = typeof saved.final_md === 'string' ? saved.final_md : ''
  elapsedMs.value = typeof saved.elapsed_ms === 'number' ? saved.elapsed_ms : null
  done.value = saved.status === 'done'

  phaseProfile.value = true
  phaseRoles.value = roleCards.value.filter((r) => r.done || r.error).length
  phasePlanner.value = dimensions.value.length > 0
  phaseEvidence.value = Object.values(evidenceByDim.value).some((items) => Array.isArray(items) && items.length)
  finishedDimIds.value = Object.fromEntries(
    Object.entries(dimTexts.value)
      .filter(([, txt]) => String(txt || '').trim())
      .map(([id]) => [id, true])
  )
  phaseDimAnalysis.value = dimensions.value.length > 0 && dimensions.value.every((d) => finishedDimIds.value[d.id])
  phaseFinalDone.value = !!finalMd.value.trim()
  phaseFinalActive.value = saved.status === 'generating' && saved.phase === 'final'
  statusHint.value = saved.status === 'generating' ? t('insight.working') : ''
  if (saved.status === 'failed' && saved.error_message) {
    errorBanner.value = saved.error_message
  }

  if (saved.status === 'done') {
    visualPhaseState.value = {
      p: { done: true, active: false },
      r: { done: true, active: false },
      l: { done: true, active: false },
      q: { done: true, active: false },
      f: { done: true, active: false }
    }
    reportFullyLoaded.value = true
  }
  return true
}

function onClose() {
  abortStream()
  emit('close')
}

function abortStream() {
  try {
    abortCtrl.value?.abort()
  } catch {
    /* ignore */
  }
  abortCtrl.value = null
}

async function runStream({ preserveExisting = false } = {}) {
  const mid = props.moduleId
  const tok = (props.shareToken || '').trim()
  if (!mid && !tok) {
    errorBanner.value = t('insight.errNoTarget')
    return
  }

  abortStream()
  if (!preserveExisting) resetState()
  hasAttempted.value = true
  streaming.value = true
  emit('streaming', true)

  const ctrl = new AbortController()
  abortCtrl.value = ctrl

  const onEvent = (evt, data) => {
    switch (evt) {
      case 'insight_start':
        statusHint.value = data?.message || ''
        break
      case 'insight_error':
        errorBanner.value = data?.message || t('insight.errGeneric')
        emit('error', data?.message)
        break
      case 'profile_start':
        statusHint.value = data?.message || ''
        break
      case 'profile_result':
        phaseProfile.value = true
        profileBundle.value = data?.profile ?? null
        break
      case 'role_start':
        upsertRole({
          role: data?.role,
          name: data?.name,
          done: false,
          hypotheses: [],
          role_summary: '',
          thinking_feedback: '',
          error: ''
        })
        break
      case 'role_result':
        phaseRoles.value += 1
        upsertRole({
          role: data?.role,
          name: data?.name,
          done: true,
          hypotheses: Array.isArray(data?.hypotheses) ? data.hypotheses : [],
          role_summary: typeof data?.role_summary === 'string' ? data.role_summary : '',
          thinking_feedback: typeof data?.thinking_feedback === 'string' ? data.thinking_feedback : '',
          error: typeof data?.error === 'string' ? data.error : ''
        })
        break
      case 'planner_start':
        statusHint.value = data?.message || ''
        break
      case 'dimensions_result':
        phasePlanner.value = true
        dimensions.value = Array.isArray(data?.dimensions) ? data.dimensions : []
        evidenceByDim.value = {}
        dimTexts.value = {}
        finishedDimIds.value = {}
        finalMd.value = ''
        break
      case 'query_plan_start':
        phaseEvidence.value = false
        statusHint.value = data?.message || ''
        break
      case 'query_start':
        break
      case 'query_result': {
        phaseEvidence.value = true
        const did = data?.dim_id
        if (!did) break
        const cur = evidenceByDim.value[did] ? [...evidenceByDim.value[did]] : []
        cur.push(data)
        evidenceByDim.value = { ...evidenceByDim.value, [did]: cur }
        break
      }
      case 'dimension_analysis_delta': {
        const id = data.dim_id
        const d = data.delta || ''
        dimTexts.value = { ...dimTexts.value, [id]: (dimTexts.value[id] || '') + d }
        break
      }
      case 'dimension_analysis_done':
        finishedDimIds.value = { ...finishedDimIds.value, [data.dim_id]: true }
        phaseDimAnalysis.value = dimensions.value.length > 0 && finishedDimCount.value >= dimensions.value.length
        break
      case 'final_start':
        phaseFinalActive.value = true
        statusHint.value = data?.message || ''
        break
      case 'final_delta':
        finalMd.value += data?.delta || ''
        break
      case 'final_done':
        phaseFinalDone.value = true
        break
      case 'insight_done':
        done.value = true
        elapsedMs.value = typeof data?.elapsed_ms === 'number' ? data.elapsed_ms : null
        streaming.value = false
        emit('streaming', false)
        emit('done')
        break
      default:
        break
    }
  }

  try {
    if (tok) {
      await runInsightShareStream(tok, { signal: ctrl.signal, onEvent })
    } else {
      await runInsightStream(mid, { signal: ctrl.signal, onEvent })
    }
  } catch (e) {
    const aborted = e?.name === 'AbortError' || ctrl.signal.aborted
    if (!aborted) {
      errorBanner.value = e?.message || t('insight.errGeneric')
      emit('error', e?.message)
    }
  } finally {
    streaming.value = false
    emit('streaming', false)
    abortCtrl.value = null
    phaseFinalActive.value = false
  }
}

function retry() {
  if (streaming.value) return
  runStream()
}

async function bootstrap() {
  const mid = props.moduleId
  const tok = (props.shareToken || '').trim()
  if (!mid && !tok) {
    errorBanner.value = t('insight.errNoTarget')
    return
  }

  hasAttempted.value = true
  try {
    const saved = tok ? await fetchInsightShareReport(tok) : await fetchInsightReport(mid)
    const hasSaved = hydrateSavedReport(saved)
    if (hasSaved && saved.status === 'done') return
    await runStream({ preserveExisting: hasSaved && saved.status === 'generating' })
  } catch {
    await runStream()
  }
}

onMounted(() => {
  bootstrap()
})

onBeforeUnmount(() => {
  abortStream()
  _clearAllTimers()
})
</script>

<style scoped>
.xq-insight {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  max-width: 920px;
  margin: 0 auto;
  width: 100%;
  padding: 4px 4px 0;
  box-sizing: border-box;
}

.xq-insight-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.xq-insight-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
}

.xq-post-chrome {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  position: sticky;
  top: 0;
  z-index: 5;
  padding: 8px 2px 12px;
  margin-bottom: 4px;
  background: linear-gradient(180deg, #fff 70%, rgba(255, 255, 255, 0));
}

.xq-post-back {
  font-weight: 500;
}

.xq-post-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.xq-insight-alert {
  margin-bottom: 12px;
  flex-shrink: 0;
}

/* =============================================
   Pipeline Dock — Premium Stepper
   ============================================= */
.pipeline-fade-enter-active {
  transition: opacity 0.5s ease, transform 0.5s ease;
}
.pipeline-fade-leave-active {
  transition: opacity 0.6s ease, transform 0.6s ease;
}
.pipeline-fade-enter-from {
  opacity: 0;
  transform: translateY(-12px);
}
.pipeline-fade-leave-to {
  opacity: 0;
  transform: translateY(-20px);
}

.xq-pipeline-wrap {
  flex-shrink: 0;
  margin-bottom: 12px;
}

.xq-pipeline-glass {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 10px 12px 12px;
  border-radius: 16px;
  background: linear-gradient(145deg, #f8fafc 0%, #f0fdfa 38%, #ecfeff 100%);
  border: 1px solid rgba(45, 212, 191, 0.22);
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.04),
    0 8px 28px rgba(15, 118, 110, 0.07);
  overflow: hidden;
}

.xq-pipeline-toolbar {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: nowrap;
  padding-bottom: 10px;
  margin-bottom: 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}

.xq-pipeline-back {
  flex-shrink: 0;
  font-weight: 500;
}

.xq-pipeline-hint {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  font-weight: 500;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.xq-pipeline-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.xq-pipeline-bg-grid {
  position: absolute;
  inset: 0;
  opacity: 0.35;
  background-image:
    linear-gradient(rgba(15, 118, 110, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 118, 110, 0.06) 1px, transparent 1px);
  background-size: 24px 24px;
  pointer-events: none;
}

.xq-pipeline-flow {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  width: 100%;
}

/* ---- Node ---- */
.xq-pipe-node {
  flex: 1 1 0;
  min-width: 0;
  position: relative;
}

.xq-pipe-node-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 6px 8px;
  width: 100%;
  min-width: 0;
}

.xq-pipe-node-main {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 48px;
}

.xq-pipe-ring {
  position: relative;
  width: 40px;
  height: 40px;
}

.xq-pipe-ring-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.xq-pipe-ring-track {
  fill: none;
  stroke: rgba(148, 163, 184, 0.45);
  stroke-width: 2.5;
}

.xq-pipe-ring-fill {
  fill: none;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-dasharray: 120;
  transition:
    stroke-dashoffset 1.65s cubic-bezier(0.4, 0, 0.2, 1),
    stroke 0.55s ease,
    filter 0.55s ease;
}

.xq-pipe-node.is-pending .xq-pipe-ring-fill {
  stroke: rgba(203, 213, 225, 0.55);
  filter: none;
}
.xq-pipe-node.is-active .xq-pipe-ring-fill {
  stroke: #14b8a6;
  filter: drop-shadow(0 0 5px rgba(20, 184, 166, 0.35));
}
.xq-pipe-node.is-done .xq-pipe-ring-fill {
  stroke: #10b981;
  filter: drop-shadow(0 0 3px rgba(16, 185, 129, 0.25));
}

.xq-pipe-icon {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ico-flip-enter-active,
.ico-flip-leave-active {
  transition: opacity 0.35s ease, transform 0.35s ease;
}
.ico-flip-enter-from {
  opacity: 0;
  transform: scale(0.5) rotate(-30deg);
}
.ico-flip-leave-to {
  opacity: 0;
  transform: scale(0.5) rotate(30deg);
}

.xq-pipe-check {
  width: 16px;
  height: 16px;
  color: #059669;
}
.xq-pipe-check svg {
  width: 100%;
  height: 100%;
}

.xq-pipe-spinner {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(20, 184, 166, 0.35);
  border-top-color: #14b8a6;
  border-radius: 50%;
  animation: xq-spin 0.85s linear infinite;
}

.xq-pipe-num {
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
}

.xq-pipe-node.is-active .xq-pipe-num {
  color: #0d9488;
}

.xq-pipe-label {
  margin-top: 6px;
  font-size: 10.5px;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.03em;
  line-height: 1.25;
  max-width: 4.8em;
  text-align: center;
  transition: color 0.5s ease;
}

.xq-pipe-node.is-active .xq-pipe-label {
  color: #0f766e;
}
.xq-pipe-node.is-done .xq-pipe-label {
  color: #047857;
}

/* ---- Sub-nodes（主标题右侧，纵向紧凑排列） ---- */
.xq-pipe-subs {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: flex-start;
  text-align: left;
  padding: 2px 0;
}

.xq-pipe-sub {
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0.32;
  transition: opacity 0.55s ease;
}

.xq-pipe-sub.is-done {
  opacity: 0.72;
}
.xq-pipe-sub.is-active {
  opacity: 1;
}

.xq-pipe-sub-dot {
  width: 3.5px;
  height: 3.5px;
  border-radius: 50%;
  background: #cbd5e1;
  flex-shrink: 0;
  transition: background 0.45s ease, box-shadow 0.45s ease;
}

.xq-pipe-sub.is-done .xq-pipe-sub-dot {
  background: #10b981;
}
.xq-pipe-sub.is-active .xq-pipe-sub-dot {
  background: #14b8a6;
  box-shadow: 0 0 5px rgba(20, 184, 166, 0.45);
  animation: xq-sub-blink 1.1s ease-in-out infinite;
}

.xq-pipe-sub-text {
  font-size: 9px;
  font-weight: 500;
  color: #94a3b8;
  white-space: nowrap;
  letter-spacing: 0.02em;
  transition: color 0.45s ease;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.xq-pipe-sub.is-done .xq-pipe-sub-text {
  color: #059669;
}
.xq-pipe-sub.is-active .xq-pipe-sub-text {
  color: #0f766e;
  font-weight: 600;
}

/* ---- Connector ---- */
.xq-pipe-connector {
  flex: 0 0 18px;
  height: 3px;
  margin: 0 2px;
  align-self: center;
  position: relative;
  border-radius: 2px;
  background: #e2e8f0;
  overflow: visible;
  transition: background 0.7s ease;
}

.xq-pipe-connector.is-done {
  background: linear-gradient(90deg, #6ee7b7, #34d399);
}

.xq-pipe-conn-line {
  display: none;
}

.xq-pipe-conn-particle {
  position: absolute;
  top: -2px;
  left: -3px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.45);
  animation: xq-particle-travel 0.75s ease-out forwards;
}

@keyframes xq-particle-travel {
  0% { left: -3px; opacity: 1; }
  100% { left: calc(100% - 3px); opacity: 0; }
}

@keyframes xq-spin {
  to { transform: rotate(360deg); }
}

@keyframes xq-sub-blink {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.xq-insight-stream {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 22px;
}

.xq-stream-card {
  padding: 18px 18px 16px;
  border-radius: 16px;
  background: #fff;
  border: 1px solid #e8ecf1;
  box-shadow:
    0 1px 3px rgba(15, 23, 42, 0.04),
    0 8px 24px rgba(15, 23, 42, 0.06);
}

.xq-stream-card--lead {
  border-color: #c7d2fe;
  background: linear-gradient(180deg, #fafbff 0%, #fff 52%);
  box-shadow:
    0 1px 3px rgba(79, 70, 229, 0.06),
    0 10px 28px rgba(79, 70, 229, 0.08);
}

.xq-stream-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.xq-stream-card-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: 0;
}

.xq-insight-dim-title {
  flex: 1 1 auto;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.xq-stream-ribbon {
  font-size: 11px;
  font-weight: 600;
  color: #4f46e5;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.22);
  white-space: nowrap;
}

.xq-pre-skeleton {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 14px 16px 18px;
  margin-bottom: 14px;
}

.xq-pre-sk-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.xq-pre-sk-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e5e7eb;
  flex-shrink: 0;
}

.xq-pre-sk-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  line-height: 1.3;
}

.xq-pre-sk-sub {
  margin-top: 3px;
  font-size: 12px;
  color: #64748b;
}

.xq-pre-sk-table {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.xq-pre-sk-row {
  display: grid;
  grid-template-columns: 1fr 1.6fr 1.25fr 0.9fr;
  gap: 14px;
  align-items: center;
  min-height: 24px;
}

.xq-pre-sk-row--head {
  padding-bottom: 2px;
  border-bottom: 1px solid #f1f5f9;
}

.xq-pre-sk-cell,
.xq-pre-sk-line,
.xq-pre-sk-pill {
  display: block;
  height: 11px;
  border-radius: 4px;
  background: linear-gradient(90deg, #f3f4f6 25%, #e9ebee 50%, #f3f4f6 75%);
  background-size: 200% 100%;
  animation: xq-pre-sk-shimmer 1.4s ease-in-out infinite;
}

.xq-pre-sk-pill {
  width: 64px;
  height: 18px;
  border-radius: 999px;
}

.xq-pre-sk-pill.is-short {
  width: 44px;
  animation-delay: 0.12s;
}

.xq-dim-plan-sk-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.xq-dim-plan-sk-card {
  min-height: 96px;
  padding: 12px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #eef2f7;
}

.xq-dim-plan-sk-card .xq-pre-sk-line {
  margin-bottom: 10px;
}

.xq-dim-plan-sk-footer {
  display: flex;
  gap: 8px;
  margin-top: 14px;
}

/* —— 多维研判 · 数据画像预览（等待维度阶段） —— */
.xq-role-perspective-panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 14px 16px 16px;
  margin-bottom: 14px;
}

.xq-role-perspective-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 14px;
}

.xq-role-perspective-dot {
  width: 8px;
  height: 8px;
  margin-top: 6px;
  border-radius: 50%;
  background: linear-gradient(135deg, #0d9488, #0f766e);
  flex-shrink: 0;
}

.xq-role-perspective-head-text {
  min-width: 0;
}

.xq-role-perspective-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  line-height: 1.3;
}

.xq-role-perspective-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.45;
}

.xq-role-preview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 640px) {
  .xq-role-preview-grid {
    grid-template-columns: 1fr;
  }
}

.xq-role-preview-card {
  min-height: 0;
  padding: 12px 12px 10px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #eef2f7;
}

.xq-role-preview-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  min-height: 24px;
}

.xq-role-preview-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: #0f766e;
  font-variant-numeric: tabular-nums;
}

.xq-role-preview-name {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.xq-role-preview-status {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.xq-role-preview-status.is-done {
  color: #059669;
}

.xq-role-preview-status.is-wait {
  color: #94a3b8;
  animation: xq-role-wait-pulse 1.2s ease-in-out infinite;
}

.xq-role-preview-status.is-err {
  color: #dc2626;
}

@keyframes xq-role-wait-pulse {
  0%,
  100% {
    opacity: 0.45;
  }
  50% {
    opacity: 1;
  }
}

.xq-role-preview-chart {
  margin: 0 -4px;
  min-height: 200px;
}

.xq-role-preview-chart :deep(.xq-chart) {
  border-radius: 8px;
  background: #fff;
  border: 1px solid #e8ecf1;
  padding: 8px 8px 4px;
}

.xq-role-preview-chart-fallback {
  font-size: 11px;
  color: #94a3b8;
  padding: 28px 10px;
  text-align: center;
  background: #fff;
  border-radius: 8px;
  border: 1px dashed #e2e8f0;
}

.xq-role-preview-summary {
  margin: 10px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: #475569;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.xq-role-preview-err {
  margin: 10px 0 0;
  font-size: 11px;
  line-height: 1.45;
  color: #b91c1c;
}

.xq-role-plan-hint {
  margin: 14px 0 0;
  padding: 10px 12px;
  font-size: 12px;
  color: #0f766e;
  font-weight: 600;
  background: rgba(13, 148, 136, 0.08);
  border-radius: 8px;
  border: 1px solid rgba(13, 148, 136, 0.18);
}

.w-14 { width: 14%; }
.w-18 { width: 18%; }
.w-20 { width: 20%; }
.w-22 { width: 22%; }
.w-24 { width: 24%; }
.w-26 { width: 26%; }
.w-32 { width: 32%; }
.w-36 { width: 36%; }
.w-48 { width: 48%; }
.w-68 { width: 68%; }
.w-86 { width: 86%; }

@keyframes xq-pre-sk-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.xq-skeleton-wrap {
  padding: 4px 0 2px;
}

.xq-skeleton-cap {
  margin: 0 0 12px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.02em;
}

.xq-fishbone {
  position: relative;
  min-height: 148px;
  padding: 10px 8px 14px;
}

.xq-fishbone--sm {
  min-height: 112px;
}

.xq-fishbone-spine {
  position: absolute;
  left: 50%;
  top: 12px;
  bottom: 12px;
  width: 2px;
  margin-left: -1px;
  border-radius: 1px;
  background: linear-gradient(
    180deg,
    transparent 0%,
    #e2e8f0 12%,
    #cbd5e1 50%,
    #e2e8f0 88%,
    transparent 100%
  );
  opacity: 0.85;
}

.xq-fishbone-rows {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.xq-fishbone-row {
  height: 20px;
  display: flex;
  align-items: center;
}

.xq-fishbone-row.is-l {
  justify-content: flex-end;
  padding-right: calc(50% + 14px);
}

.xq-fishbone-row.is-r {
  justify-content: flex-start;
  padding-left: calc(50% + 14px);
}

.xq-fishbone-chip {
  display: block;
  height: 11px;
  border-radius: 6px;
  max-width: 100%;
  background: linear-gradient(105deg, #e2e8f0 0%, #f1f5f9 38%, #e8edf4 72%, #e2e8f0 100%);
  background-size: 200% 100%;
  animation: xq-fish-shimmer 1.35s ease-in-out infinite;
}

.xq-fishbone-chip.w-a {
  width: min(88%, 280px);
}
.xq-fishbone-chip.w-b {
  width: min(72%, 220px);
}
.xq-fishbone-chip.w-c {
  width: min(80%, 248px);
}
.xq-fishbone-chip.w-d {
  width: min(64%, 200px);
}

.xq-fishbone--sm .xq-fishbone-chip.w-a {
  width: min(78%, 240px);
}
.xq-fishbone--sm .xq-fishbone-chip.w-b {
  width: min(70%, 200px);
}
.xq-fishbone--sm .xq-fishbone-chip.w-c {
  width: min(76%, 220px);
}
.xq-fishbone--sm .xq-fishbone-chip.w-d {
  width: min(62%, 180px);
}

@keyframes xq-fish-shimmer {
  0% {
    background-position: 100% 0;
  }
  100% {
    background-position: -100% 0;
  }
}

.xq-insight-roles {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}

.xq-role-card {
  padding: 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.xq-role-card.is-done {
  background: #fff;
  border-color: #bfdbfe;
}

.xq-role-card.is-clickable {
  cursor: pointer;
  text-align: left;
  font: inherit;
  width: 100%;
  box-sizing: border-box;
}

.xq-role-card.is-clickable:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}

.xq-role-card.is-clickable:focus-visible {
  outline: 2px solid #3b82f6;
  outline-offset: 2px;
}

.xq-role-card.is-clickable.is-done:hover {
  background: #f8fbff;
}

.xq-role-card.is-fail {
  border-color: #fecdd3;
  background: #fff1f2;
}

.xq-role-card.is-fail.is-clickable:hover {
  border-color: #fca5a5;
  background: #ffe4e6;
}

.xq-role-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 0;
}

.xq-role-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.xq-role-foot {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
}

.xq-role-tap {
  font-size: 11px;
  font-weight: 600;
  color: #2563eb;
  letter-spacing: 0.02em;
}

:deep(.xq-role-detail-dialog .el-dialog__body) {
  padding-top: 8px;
}

.xq-role-dialog-alert {
  margin-bottom: 14px;
}

.xq-role-dialog-block + .xq-role-dialog-block {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.xq-role-dialog-h {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.xq-role-dialog-muted {
  margin: 0;
  font-size: 13px;
  color: #94a3b8;
  line-height: 1.5;
}

.xq-role-hyp-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: #475569;
  line-height: 1.55;
}

.xq-role-hyp-li {
  margin-bottom: 10px;
}

.xq-role-hyp-li strong {
  color: #334155;
  display: block;
  margin-bottom: 4px;
}

.xq-role-hyp-body {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.xq-insight-block {
  margin-bottom: 22px;
}

.xq-insight-block-title {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.xq-insight-placeholder {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: #64748b;
  padding: 12px 14px;
  background: linear-gradient(105deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 10px;
  border: 1px dashed #cbd5e1;
}

.xq-insight-placeholder.sm {
  padding: 8px 12px;
  font-size: 12px;
}

.xq-dot-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3b82f6;
  animation: xq-pulse 1s ease-in-out infinite;
}

@keyframes xq-pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.95);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

.xq-insight-md {
  font-size: 13px;
  line-height: 1.65;
  color: #334155;
}

.xq-insight-md :deep(p) {
  margin: 0.45em 0;
}

.xq-insight-md :deep(strong) {
  font-weight: 600;
  color: #0f172a;
}

.xq-insight-md :deep(em) {
  font-style: italic;
  color: #475569;
}

.xq-insight-md :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: #f1f5f9;
  font-size: 12px;
  color: #0f172a;
}

.xq-insight-md :deep(pre) {
  overflow-x: auto;
  padding: 10px;
  border-radius: 8px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 12px;
}

.xq-insight-md :deep(h2) {
  font-size: 15px;
  font-weight: 700;
  margin: 1.1em 0 0.5em;
  padding-bottom: 6px;
  border-bottom: 1px solid #e2e8f0;
  color: #0f172a;
  letter-spacing: -0.01em;
}

.xq-insight-md :deep(h2:first-child) {
  margin-top: 0;
}

.xq-insight-md :deep(h3) {
  font-size: 13.5px;
  font-weight: 600;
  margin: 1em 0 0.4em;
  color: #1e293b;
}

.xq-insight-md :deep(ul),
.xq-insight-md :deep(ol) {
  margin: 0.35em 0 0.55em;
  padding-left: 1.35em;
}

.xq-insight-md :deep(ul) {
  list-style-type: disc;
}

.xq-insight-md :deep(ol) {
  list-style-type: decimal;
}

.xq-insight-md :deep(li) {
  margin: 0.25em 0;
  padding-left: 0.15em;
}

.xq-insight-md :deep(li::marker) {
  color: #64748b;
}

.xq-insight-md :deep(.md-table-wrap) {
  margin: 0.65em 0;
  overflow-x: auto;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fff;
}

.xq-insight-md :deep(.md-table-wrap table) {
  margin: 0;
  width: 100%;
  min-width: 360px;
  border-collapse: collapse;
  font-size: 12px;
}

.xq-insight-md :deep(th),
.xq-insight-md :deep(td) {
  border: 1px solid #e8ecf1;
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}

.xq-insight-md :deep(th) {
  background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
  font-weight: 600;
  color: #334155;
  white-space: nowrap;
}

.xq-insight-md :deep(tbody tr:nth-child(even) td) {
  background: #fafbfc;
}

.xq-insight-md :deep(tbody tr:hover td) {
  background: #f0f9ff;
}

.xq-insight-md :deep(blockquote),
.xq-insight-md :deep(.md-blockquote) {
  margin: 0.55em 0;
  padding: 10px 12px 10px 14px;
  border-left: 3px solid #38bdf8;
  border-radius: 0 8px 8px 0;
  background: #f8fafc;
  color: #475569;
  font-size: 12.5px;
  line-height: 1.62;
}

.xq-insight-md :deep(blockquote strong),
.xq-insight-md :deep(.md-blockquote strong) {
  color: #0f172a;
}

.xq-insight-dim {
  margin-bottom: 22px;
  padding: 16px;
  border-radius: 14px;
  background: #fafafa;
  border: 1px solid #ececec;
}

.xq-insight-dim-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.xq-insight-dim-why {
  margin: 6px 0 12px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.xq-insight-charts {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 12px;
}

.xq-insight-evidence-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.xq-ev-tag {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #475569;
  max-width: 100%;
}

.xq-ev-tag.muted {
  color: #94a3b8;
  background: #f8fafc;
  border-style: dashed;
}

.xq-insight-footer {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  margin-top: 8px;
}

@media (max-width: 640px) {
  .xq-pipeline-toolbar {
    flex-wrap: wrap;
    gap: 6px;
  }
  .xq-pipeline-actions {
    flex-basis: 100%;
    justify-content: flex-end;
  }
  .xq-post-chrome {
    flex-direction: column;
    align-items: stretch;
  }
  .xq-pre-sk-row {
    grid-template-columns: 0.9fr 1.4fr 1fr;
  }
  .xq-pre-sk-row .xq-pre-sk-cell:nth-child(4) {
    display: none;
  }
  .xq-dim-plan-sk-grid {
    grid-template-columns: 1fr;
  }
  .xq-pipeline-glass {
    padding: 10px 8px;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .xq-pipeline-flow {
    min-width: 560px;
  }
  .xq-pipe-label {
    font-size: 10px;
    max-width: 4em;
  }
  .xq-pipe-connector {
    flex: 0 0 12px;
  }
  .xq-pipe-sub-text {
    font-size: 8px;
  }
}
</style>
