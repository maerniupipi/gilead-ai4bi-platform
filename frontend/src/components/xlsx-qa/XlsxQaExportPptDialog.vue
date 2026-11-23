<template>
  <el-dialog
    v-model="visible"
    class="xe-export-dialog"
    :title="t('exp.title')"
    width="960px"
    :close-on-click-modal="false"
    @open="onOpen"
    @close="onClose"
  >
    <div class="xe-export-shell">
    <div class="xe-redesign">
      <!-- ======================== LEFT: History ======================== -->
      <div class="xe-left">
        <div class="xe-left-header">{{ t('exp.history.title') }}</div>
        <div class="xe-history-list">
          <div v-if="!loadingHistory && !historyItems.length" class="xe-history-empty">
            <svg class="xe-empty-icon" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="8" y="8" width="32" height="32" rx="3" stroke="#cbd5e1" stroke-width="1.5"/>
              <rect x="14" y="14" width="20" height="14" rx="1" fill="#e2e8f0"/>
              <path d="M18 24h12M18 28h8" stroke="#94a3b8" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <span>{{ t('exp.history.empty') }}</span>
          </div>
          <div
            v-for="item in historyItems"
            :key="item.id"
            class="xe-history-item"
            :class="{
              'is-generating': item.status === 'generating',
              'is-failed': item.status === 'failed',
              'is-ready': item.status === 'ready',
            }"
          >
            <div class="xe-history-status-icon">
              <el-icon v-if="item.status === 'generating'" class="is-spinning"><Loading /></el-icon>
              <el-icon v-else-if="item.status === 'failed'" class="xe-icon-failed"><CircleCloseFilled /></el-icon>
              <el-icon v-else class="xe-icon-ready"><CircleCheckFilled /></el-icon>
            </div>
            <div class="xe-history-body">
              <div class="xe-history-title">
                {{ item.conversation_title }}
                <span v-if="isInsightHistory(item)" class="xe-history-insight-tag">{{ t('exp.history.insight') }}</span>
              </div>
              <div class="xe-history-meta">{{ formatTemplate(item.template_id) }} / {{ formatDate(item.created_at) }}</div>
              <div v-if="item.status === 'generating'" class="xe-history-progress">
                <div class="xe-history-progress-current">{{ item.status_message || t('exp.history.generating') }}</div>
                <div v-if="progressTailMessages(item).length" class="xe-history-progress-scroll">
                  <div
                    v-for="(msg, i) in progressTailMessages(item)"
                    :key="i"
                    class="xe-history-progress-line"
                  >
                    {{ msg }}
                  </div>
                </div>
              </div>
              <div v-if="item.status === 'failed'" class="xe-history-error">{{ t('exp.history.failed') }}</div>
            </div>
            <div class="xe-history-actions">
              <el-button
                v-if="item.status === 'ready'"
                type="primary"
                size="small"
                class="xe-history-action-btn"
                @click="downloadHistory(item)"
              >
                {{ t('exp.history.download') }}
              </el-button>
              <el-button
                type="danger"
                size="small"
                plain
                class="xe-history-action-btn"
                @click="deleteHistoryItem(item)"
              >
                {{ t('exp.history.delete') }}
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- ======================== RIGHT: Generate ======================== -->
      <div class="xe-right">
        <!-- Template grid -->
        <div class="xe-section">
          <div class="xe-section-title">{{ t('exp.panel.templates') }}</div>
          <div class="xe-template-grid">
            <div
              v-for="tpl in templateGrid"
              :key="tpl.id"
              class="xe-tpl-card"
              :class="{
                'is-selected': options.template_id === tpl.id,
                'is-custom': tpl.isCustom,
              }"
              @click="options.template_id = tpl.id"
            >
              <span v-if="tpl.isCustom" class="xe-tpl-hot">HOT</span>
              <img v-if="tpl.isCustom" :src="customCoverUrl" class="xe-tpl-cover" />
              <svg v-else class="xe-tpl-preview" viewBox="0 0 120 48" xmlns="http://www.w3.org/2000/svg">
                <rect width="120" height="48" :fill="tpl.colors.bg" rx="3"/>
                <rect x="0" y="0" width="8" height="48" :fill="tpl.colors.primary" rx="3 0 0 3"/>
                <rect x="12" y="8" width="40" height="6" :fill="tpl.colors.primary" rx="1" opacity="0.8"/>
                <rect x="12" y="18" width="96" height="4" :fill="tpl.colors.primary" rx="1" opacity="0.3"/>
                <rect x="12" y="26" width="96" height="4" :fill="tpl.colors.accent" rx="1" opacity="0.2"/>
                <rect x="12" y="34" width="60" height="4" :fill="tpl.colors.primary" rx="1" opacity="0.15"/>
              </svg>
              <span class="xe-tpl-name">{{ tpl.displayName }}</span>
              <span v-if="tpl.displayDesc" class="xe-tpl-desc">{{ tpl.displayDesc }}</span>
            </div>
          </div>
        </div>

        <!-- Logo section (only for custom template) -->
        <div v-if="isCustomTemplate" class="xe-logo-section">
          <div class="xe-logo-preview">
            <img v-if="moduleLogoUrl" :src="moduleLogoUrl" class="xe-logo-img" />
            <svg v-else class="xe-logo-placeholder" viewBox="0 0 80 40" xmlns="http://www.w3.org/2000/svg">
              <rect width="80" height="40" rx="4" fill="none" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="4 3"/>
              <path d="M32 14h16M32 20h12M32 26h16" stroke="#94a3b8" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
          </div>
          <div class="xe-logo-actions">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept="image/png,image/jpeg"
              :on-change="handleLogoChange"
            >
              <el-button size="small">{{ t('exp.panel.logoUpload') }}</el-button>
            </el-upload>
            <el-button
              v-if="moduleLogoUrl"
              link
              size="small"
              type="danger"
              @click="removeLogo"
            >
              {{ t('exp.panel.logoRemove') }}
            </el-button>
          </div>
          <span class="xe-logo-hint">{{ t('exp.panel.logoHint') }}</span>
        </div>

        <!-- Content options -->
        <div v-if="!insightMode" class="xe-toolbar">
          <span class="xe-sel-info">
            <template v-if="selectedCount">
              {{ t('exp.selected_n', { n: selectedCount }) }}
            </template>
            <template v-else>{{ t('exp.unselected') }}</template>
            <span v-if="assistantList.length" class="xe-total"> / 共 {{ assistantList.length }} 条</span>
            <span v-if="isCustomTemplate" class="xe-total">（最多 5 条）</span>
          </span>
          <span class="xe-sep" />
          <el-button link size="small" @click="selectAll">全选</el-button>
          <el-button link size="small" @click="clearAll">清空</el-button>
        </div>

        <!-- Q&A selection list -->
        <div v-if="!insightMode && !assistantList.length" class="xe-empty">{{ t('exp.empty') }}</div>
        <div v-else-if="!insightMode" class="xe-list xe-list--fill">
          <div
            v-for="(item, i) in assistantList"
            :key="item.ast.id"
            class="xe-item"
            :class="{ 'is-selected': selectedIds.has(item.ast.id) }"
            @click="toggleItem(item.ast.id)"
          >
            <el-checkbox
              :model-value="selectedIds.has(item.ast.id)"
              @click.stop
              @change="toggleItem(item.ast.id)"
            />
            <div class="xe-item-body">
              <div class="xe-item-meta">
                <span class="xe-item-index">Q{{ i + 1 }}</span>
                <span class="xe-item-q">{{ item.question }}</span>
              </div>
              <div class="xe-item-a">{{ item.preview }}</div>
            </div>
            <div v-if="item.chartCount" class="xe-item-badge">
              {{ item.chartCount }} 图
            </div>
          </div>
        </div>
      </div>
    </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
      <el-button
        type="primary"
        :loading="generating || hasActiveGeneration"
        :disabled="(!insightMode && !selectedCount) || hasActiveGeneration"
        @click="onGenerate"
      >
        {{ (generating || hasActiveGeneration) ? t('exp.panel.generating') : t('exp.panel.btn') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import {
  exportXlsxQaConversationPptAsync,
  exportXlsxQaConversationCustomPptAsync,
  listPptHistory,
  getPptHistoryDownloadUrl,
  deletePptHistory,
  uploadModuleLogo,
  getModuleLogo,
  deleteModuleLogo,
  getCustomPptCoverUrl,
} from '../../api/xlsxQa'
import { useXqI18n } from '../../utils/xlsxQaI18n'

const { t } = useXqI18n()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  conversationId: { type: Number, default: null },
  moduleId: { type: Number, default: null },
  messages: { type: Array, default: () => [] },
  initialSelectedIds: { type: Array, default: () => [] },
  /** 自定义导出函数，签名 (convId, data) => Promise。不传则使用默认接口。 */
  exportFn: { type: Function, default: null },
  /** 深度洞察报告模式：只显示专属模板，不显示 Q&A 选择。 */
  insightMode: { type: Boolean, default: false },
  /** 分享模式下的历史列表函数 (moduleId) => Promise */
  listHistoryFn: { type: Function, default: null },
  /** 分享模式下的下载链接函数 (historyId) => Promise */
  getDownloadUrlFn: { type: Function, default: null },
  /** 分享模式下的删除历史函数 (historyId) => Promise */
  deleteHistoryFn: { type: Function, default: null },
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// ------------------------------------------------------------------
// State
// ------------------------------------------------------------------
const generating = ref(false)
const hasActiveGeneration = computed(() => historyItems.value.some(h => h.status === 'generating'))
const loadingHistory = ref(false)
const historyItems = ref([])
const pollingTimer = ref(null)
const moduleLogoUrl = ref(null)
const logoFile = ref(null)
const selectedIds = ref(new Set())
const options = reactive({
  template_id: 'executive',
  include_subquestions: true,
  include_chart: true,
})

// ------------------------------------------------------------------
// Templates
// ------------------------------------------------------------------
const FALLBACK_TEMPLATES = [
  { id: 'executive', name: '商务简报', description: '', colors: { accent: '#16a34a', palette: ['#2563eb'], bg: '#f7fafc' } },
  { id: 'insight', name: '洞察分析', description: '', colors: { accent: '#2563eb', palette: ['#10b981'], bg: '#f8fafc' } },
  { id: 'clean', name: '简约数据', description: '', colors: { accent: '#334155', palette: ['#0e7480'], bg: '#ffffff' } },
  { id: 'midnight', name: '午夜深蓝', description: '', colors: { accent: '#ffb224', palette: ['#38bdf8'], bg: '#0d1b2a' } },
  { id: 'coral', name: '珊瑚活力', description: '', colors: { accent: '#f96167', palette: ['#f97316'], bg: '#fffaf7' } },
  { id: 'teal', name: '青绿信赖', description: '', colors: { accent: '#0d9488', palette: ['#06b6d4'], bg: '#f0fdfa' } },
  { id: 'berry', name: '浆果奶油', description: '', colors: { accent: '#9d174d', palette: ['#be185d'], bg: '#fffafc' } },
  { id: 'charcoal', name: '炭黑深沉', description: '', colors: { accent: '#f59e0b', palette: ['#38bdf8'], bg: '#1e1e1e' } },
]

const templateGrid = computed(() => {
  if (props.insightMode) {
    return [{
      id: 'custom_med',
      displayName: t('exp.panel.customName'),
      displayDesc: t('exp.panel.customDesc'),
      isCustom: true,
      colors: { primary: '#108aa8', accent: '#0b5e75', bg: '#e9f7f7' },
    }]
  }
  const system = FALLBACK_TEMPLATES.map(tpl => ({
    id: tpl.id,
    displayName: tpl.name,
    displayDesc: '',
    isCustom: false,
    colors: {
      primary: tpl.colors.accent || '#334155',
      accent: tpl.colors.palette?.[1] || tpl.colors.palette?.[0] || '#2563eb',
      bg: tpl.colors.bg || '#ffffff',
    },
  }))
  system.push({
    id: 'custom_med',
    displayName: t('exp.panel.customName'),
    displayDesc: t('exp.panel.customDesc'),
    isCustom: true,
    colors: { primary: '#108aa8', accent: '#0b5e75', bg: '#e9f7f7' },
  })
  return system
})

const isCustomTemplate = computed(() => options.template_id === 'custom_med')
const customCoverUrl = computed(() => getCustomPptCoverUrl())
const selectedCount = computed(() => selectedIds.value.size)

// ------------------------------------------------------------------
// Q&A list (pair user → assistant)
// ------------------------------------------------------------------
const assistantList = computed(() => {
  const list = []
  let lastUserQ = ''
  for (const m of props.messages) {
    if (m.role === 'user') {
      lastUserQ = m.content || ''
    } else if (m.role === 'assistant') {
      if (typeof m.id !== 'number') continue
      if (m.status === 'failed') continue
      const summary =
        m.extras?.summary_markdown ||
        m.extras?.plan_summary ||
        m.content ||
        ''
      const chartCount = Array.isArray(m.extras?.charts)
        ? m.extras.charts.length
        : (m.extras?.chart ? 1 : 0)
      list.push({
        ast: m,
        question: lastUserQ || t('exp.noQ'),
        preview: shorten(summary.replace(/[#*`>]/g, '').replace(/\n/g, ' '), 120),
        chartCount,
      })
    }
  }
  return list
})

function toggleItem(id) {
  const s = new Set(selectedIds.value)
  if (s.has(id)) s.delete(id)
  else {
    if (isCustomTemplate.value && s.size >= 5) {
      ElMessage.warning('专属定制 PPT 最多选择 5 个问题')
      return
    }
    s.add(id)
  }
  selectedIds.value = s
}

function selectAll() {
  const ids = assistantList.value.map(x => x.ast.id)
  selectedIds.value = new Set(isCustomTemplate.value ? ids.slice(0, 5) : ids)
}

function clearAll() {
  selectedIds.value = new Set()
}

function shorten(s, n) {
  s = String(s || '').trim()
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

// Watch template change → enforce max 5 for custom
watch(isCustomTemplate, (custom) => {
  if (!custom || selectedIds.value.size <= 5) return
  const keep = assistantList.value
    .map(x => x.ast.id)
    .filter(id => selectedIds.value.has(id))
    .slice(0, 5)
  selectedIds.value = new Set(keep)
})

// ------------------------------------------------------------------
// Dialog lifecycle
// ------------------------------------------------------------------
function onOpen() {
  if (props.insightMode) {
    options.template_id = 'custom_med'
    loadHistory()
    if (props.moduleId) {
      loadModuleLogo()
    }
    startPolling()
    return
  }
  options.include_subquestions = true
  options.include_chart = true
  // Init selection
  const allIds = assistantList.value.map(x => x.ast.id)
  const pre = (props.initialSelectedIds || []).filter(id => allIds.includes(id))
  selectedIds.value = new Set(pre.length ? pre : allIds)
  // Load history & logo
  loadHistory()
  if (props.moduleId) {
    loadModuleLogo()
  }
  startPolling()
}

function onClose() {
  stopPolling()
}

onUnmounted(() => {
  stopPolling()
})

// ------------------------------------------------------------------
// History
// ------------------------------------------------------------------
/** 与当前 status_message 重复的最后一条不展示，避免「当前进度」与列表最后一行重复 */
function progressTailMessages(item) {
  const msgs = Array.isArray(item.progress_messages) ? item.progress_messages : []
  if (!msgs.length) return []
  const cur = String(item.status_message || '').trim()
  const last = String(msgs[msgs.length - 1] || '').trim()
  if (cur && last === cur) return msgs.slice(0, -1)
  return msgs
}

async function loadHistory() {
  if (!props.moduleId) return
  loadingHistory.value = true
  try {
    const fn = props.listHistoryFn || listPptHistory
    const res = await fn(props.moduleId)
    const list = res.data || res
    historyItems.value = Array.isArray(list) ? list : []
  } catch {
    // silently fail
  } finally {
    loadingHistory.value = false
  }
}

function startPolling() {
  stopPolling()
  pollingTimer.value = setInterval(async () => {
    const hasGenerating = historyItems.value.some(h => h.status === 'generating')
    if (!hasGenerating) {
      stopPolling()
      return
    }
    await loadHistory()
  }, 2000)
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

async function downloadHistory(item) {
  try {
    const fn = props.getDownloadUrlFn || getPptHistoryDownloadUrl
    const res = await fn(item.id)
    const data = res.data || res
    if (data.url) {
      window.open(data.url, '_blank')
    }
  } catch (e) {
    ElMessage.error(e.message || '获取下载链接失败')
  }
}

async function deleteHistoryItem(item) {
  try {
    await ElMessageBox.confirm('确定要删除这条导出记录吗？', '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    const fn = props.deleteHistoryFn || deletePptHistory
    await fn(item.id)
    historyItems.value = historyItems.value.filter(h => h.id !== item.id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

// ------------------------------------------------------------------
// Logo
// ------------------------------------------------------------------
async function loadModuleLogo() {
  if (!props.moduleId) return
  try {
    const res = await getModuleLogo(props.moduleId)
    const data = res.data || res
    moduleLogoUrl.value = data.url || null
  } catch {
    moduleLogoUrl.value = null
  }
}

function handleLogoChange(uploadFile) {
  const raw = uploadFile?.raw
  if (!raw) return
  if (!/^image\/(png|jpeg)$/.test(raw.type || '')) {
    ElMessage.warning('Logo 仅支持 PNG/JPG')
    return
  }
  if (raw.size > 2 * 1024 * 1024) {
    ElMessage.warning('Logo 文件不能超过 2MB')
    return
  }
  logoFile.value = raw
  uploadLogoFile()
}

async function uploadLogoFile() {
  if (!logoFile.value || !props.moduleId) return
  try {
    await uploadModuleLogo(props.moduleId, logoFile.value)
    await loadModuleLogo()
    logoFile.value = null
    ElMessage.success('Logo 已更新')
  } catch (e) {
    ElMessage.error(e.message || 'Logo 上传失败')
  }
}

async function removeLogo() {
  if (!props.moduleId) return
  try {
    await deleteModuleLogo(props.moduleId)
    moduleLogoUrl.value = null
    logoFile.value = null
    ElMessage.success('Logo 已移除')
  } catch (e) {
    ElMessage.error(e.message || '移除失败')
  }
}

// ------------------------------------------------------------------
// Generate
// ------------------------------------------------------------------
async function onGenerate() {
  if (!props.insightMode) {
    if (!props.conversationId || !selectedIds.value.size) return
  }
  if ((isCustomTemplate.value || props.insightMode) && !props.exportFn) {
    if (logoFile.value) {
      await uploadLogoFile()
    }
  }
  generating.value = true
  try {
    let payload
    let doExport
    if (props.insightMode) {
      payload = { template_id: options.template_id }
      doExport = () => props.exportFn(props.moduleId, payload)
    } else {
      const orderedIds = assistantList.value
        .map(x => x.ast.id)
        .filter(id => selectedIds.value.has(id))

      payload = {
        message_ids: orderedIds,
        template_id: options.template_id,
        include_subquestions: options.include_subquestions,
        include_chart: options.include_chart,
      }
      doExport = props.exportFn
        ? () => props.exportFn(props.conversationId, payload)
        : isCustomTemplate.value
          ? () => exportXlsxQaConversationCustomPptAsync(props.conversationId, payload)
          : () => exportXlsxQaConversationPptAsync(props.conversationId, payload)
    }

    const resp = await doExport()
    const data = resp.data || resp
    historyItems.value.unshift({
      id: data.history_id,
      conversation_title: props.insightMode ? '数据深度洞察报告' : '',
      template_id: options.template_id,
      status: 'generating',
      status_message: '准备导出...',
      progress_messages: [],
      created_at: new Date().toISOString(),
    })
    startPolling()
    ElMessage.success('已开始生成 PPT，请稍候...')
  } catch (e) {
    ElMessage.error(e.message || '启动导出失败')
  } finally {
    generating.value = false
  }
}

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------
function formatTemplate(id) {
  const map = {
    executive: '商务简报', insight: '洞察分析', clean: '简约数据',
    midnight: '午夜深蓝', coral: '珊瑚活力', teal: '青绿信赖',
    berry: '浆果奶油', charcoal: '炭黑深沉', custom_med: '定制模板',
    custom_med_insight: '定制模板',
  }
  return map[id] || id
}

function isInsightHistory(item) {
  return item.template_id === 'custom_med_insight'
    || item.conversation_title === '数据深度洞察报告'
}

function formatDate(s) {
  if (!s) return ''
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<style scoped>
/* ============================================================
   Layout（高度由 .xe-export-dialog 与 shell 约束，不在整窗上出现纵向滚动条）
   ============================================================ */
.xe-export-shell {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.xe-redesign {
  display: flex;
  align-items: stretch;
  gap: 20px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.xe-left {
  width: 350px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
}

.xe-left-header {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 10px;
}

.xe-right {
  flex: 1;
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-left: 1px solid #e5e7eb;
  padding-left: 20px;
  overflow: hidden;
}

/* ============================================================
   History list
   ============================================================ */
.xe-history-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.xe-history-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 0;
  color: #94a3b8;
  font-size: 13px;
}
.xe-empty-icon {
  width: 48px;
  height: 48px;
}

.xe-history-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  transition: background 0.15s ease;
}
.xe-history-item.is-generating {
  background: #f0fdf4;
  border-color: #bbf7d0;
}
.xe-history-item.is-failed {
  background: #fef2f2;
  border-color: #fecaca;
}
.xe-history-item.is-ready {
  background: #f8fafc;
}

.xe-history-status-icon {
  flex-shrink: 0;
  padding-top: 1px;
}
.xe-history-status-icon .el-icon {
  font-size: 18px;
}
.is-spinning {
  animation: xe-spin 1.2s linear infinite;
  color: #16a34a;
}
.xe-icon-failed { color: #dc2626; }
.xe-icon-ready { color: #16a34a; }

.xe-history-body {
  flex: 1;
  min-width: 0;
}
.xe-history-title {
  font-size: 12.5px;
  font-weight: 600;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 6px;
}
.xe-history-insight-tag {
  flex-shrink: 0;
  display: inline-block;
  font-size: 10px;
  font-weight: 600;
  color: #059669;
  background: #d1fae5;
  border-radius: 10px;
  padding: 1px 7px;
  line-height: 1.5;
  white-space: nowrap;
}
.xe-history-meta {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

.xe-history-progress {
  margin-top: 6px;
}
.xe-history-progress-current {
  font-size: 11.5px;
  color: #059669;
  font-weight: 500;
}
.xe-history-item.is-generating .xe-history-progress-current {
  animation:
    xe-progress-soft 2.8s ease-in-out infinite,
    xe-progress-glow 2.8s ease-in-out infinite;
}
.xe-history-progress-scroll {
  margin-top: 4px;
  max-height: 88px;
  overflow-y: auto;
  padding-right: 4px;
}
.xe-history-progress-line {
  font-size: 11px;
  color: #64748b;
  padding: 1px 0;
  opacity: 0.6;
  transition: opacity 0.3s;
}
.xe-history-error {
  margin-top: 4px;
  font-size: 11px;
  color: #dc2626;
  line-height: 1.4;
}

.xe-history-actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
.xe-history-action-btn {
  padding-left: 12px;
  padding-right: 12px;
  margin: 0;
}

/* ============================================================
   Template grid
   ============================================================ */
.xe-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}
.xe-section-title {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
}

.xe-template-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.xe-tpl-card {
  position: relative;
  border: 1.5px solid #e5e7eb;
  border-radius: 8px;
  padding: 7px 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  user-select: none;
}
.xe-tpl-card:hover {
  border-color: #10b981;
  background: #f9fdfb;
}
.xe-tpl-card.is-selected {
  border-color: #10b981;
  background: #ecfdf5;
  box-shadow: 0 0 0 1px #10b981;
}
.xe-tpl-card.is-custom {
  grid-column: span 2;
  grid-row: span 2;
  min-height: 180px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.xe-tpl-hot {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 2;
  background: linear-gradient(135deg, #f97316, #ef4444);
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  padding: 2px 7px;
  border-radius: 10px;
  letter-spacing: 0.5px;
  line-height: 1.4;
}

.xe-tpl-preview {
  display: block;
  width: 100%;
  height: 32px;
  border-radius: 4px;
  margin-bottom: 4px;
  border: 1px solid #e5e7eb;
}

.xe-tpl-cover {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 6px;
  position: absolute;
  inset: 0;
  z-index: 0;
}
.xe-tpl-card.is-custom .xe-tpl-name,
.xe-tpl-card.is-custom .xe-tpl-desc {
  position: relative;
  z-index: 1;
  text-shadow: 0 0 8px rgba(255,255,255,0.9), 0 0 4px rgba(255,255,255,0.8);
}

.xe-tpl-name {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #111827;
  line-height: 1.25;
}
.xe-tpl-desc {
  display: block;
  margin-top: 3px;
  color: #64748b;
  font-size: 10px;
  line-height: 1.35;
}

.xe-tpl-card.is-custom.is-selected {
  border-color: #10b981;
  background: transparent;
}

/* ============================================================
   Logo section
   ============================================================ */
.xe-logo-section {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  flex-shrink: 0;
}
.xe-logo-preview {
  width: 56px;
  height: 28px;
  flex-shrink: 0;
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
  border: 1px solid #e5e7eb;
}
.xe-logo-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.xe-logo-placeholder {
  width: 100%;
  height: 100%;
  display: block;
}
.xe-logo-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.xe-logo-hint {
  color: #94a3b8;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ============================================================
   Toolbar + Q&A list
   ============================================================ */
.xe-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 8px 14px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 12.5px;
  flex-shrink: 0;
}
.xe-sel-info {
  color: #111827;
  font-size: 12.5px;
  font-weight: 600;
  min-width: 56px;
}
.xe-total { color: #6b7280; font-weight: 400; }
.xe-sep {
  width: 1px;
  height: 18px;
  background: #d1d5db;
  margin: 0 2px;
  flex-shrink: 0;
}

.xe-empty {
  padding: 24px 0;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  flex-shrink: 0;
}

.xe-list {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.xe-list--fill {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.xe-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid #f1f5f9;
  cursor: pointer;
  transition: background 0.15s ease;
  user-select: none;
}
.xe-item:last-child { border-bottom: none; }
.xe-item:hover { background: #f8fafc; }
.xe-item.is-selected { background: #ecfdf5; }

.xe-item-body { flex: 1; min-width: 0; }
.xe-item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}
.xe-item-index {
  flex-shrink: 0;
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: #10b981;
  border-radius: 4px;
  padding: 1px 5px;
  line-height: 1.5;
}
.xe-item-q {
  font-size: 12.5px;
  color: #111827;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.xe-item-a {
  font-size: 11.5px;
  color: #64748b;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.xe-item-badge {
  flex-shrink: 0;
  font-size: 11px;
  color: #059669;
  background: #d1fae5;
  border-radius: 12px;
  padding: 2px 8px;
  white-space: nowrap;
  align-self: center;
}

/* ============================================================
   Animations
   ============================================================ */
@keyframes xe-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes xe-progress-soft {
  0%,
  100% {
    color: #047857;
    opacity: 1;
  }
  50% {
    color: #0f766e;
    opacity: 0.88;
  }
}

@keyframes xe-progress-glow {
  0%,
  100% {
    text-shadow: 0 0 0 rgba(16, 185, 129, 0);
  }
  50% {
    text-shadow: 0 0 10px rgba(16, 185, 129, 0.22);
  }
}
</style>

<style>
/* 弹窗 teleport 到 body，需非 scoped 才能约束 .el-dialog__body */
.xe-export-dialog.el-dialog {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 48px);
  margin-top: 5vh !important;
  margin-bottom: auto;
}

.xe-export-dialog .el-dialog__header {
  flex-shrink: 0;
}

.xe-export-dialog .el-dialog__body {
  flex: 1;
  min-height: 0;
  overflow: hidden !important;
}

.xe-export-dialog .el-dialog__footer {
  flex-shrink: 0;
}
</style>
