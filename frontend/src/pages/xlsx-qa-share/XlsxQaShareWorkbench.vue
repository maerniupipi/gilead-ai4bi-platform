<template>
  <div v-if="!shareToken" class="xq-share-invalid">
    <el-empty description="无效的分享链接" />
  </div>
  <div v-else v-loading="loading" class="xq-share">
    <header class="xq-share-head">
      <div class="h-title">{{ moduleDetail?.name || '…' }}</div>
      <div class="h-actions">
        <el-tag v-if="docStatus" :type="docStatusType" size="small">{{ docStatusLabel }}</el-tag>
        <el-button v-if="moduleDetail?.primary_document" link size="small" @click="onDownload">
          <el-icon><Download /></el-icon>
          {{ t('wb.btn.download') }}
        </el-button>
        <el-button v-if="activeConvId" link size="small" @click="exportDialogVisible = true">
          <el-icon><DocumentCopy /></el-icon>
          {{ t('wb.btn.exportPpt') }}
        </el-button>
        <el-button
          link
          size="small"
          :disabled="pdfExportDisabled"
          :loading="pdfExporting"
          @click="onExportPdf"
        >
          <el-icon><Download /></el-icon>
          {{ t('wb.btn.exportPdf') }}
        </el-button>
        <el-button size="small" class="lang-toggle" :title="t('lang.switch')" @click="toggleLang">
          <span class="lang-toggle-text">中 / EN</span>
        </el-button>
      </div>
    </header>

    <div class="xq-share-body">
      <aside class="xq-share-side">
        <div class="side-head">
          <span>{{ t('wb.side.conv') }}</span>
          <el-button :disabled="!canAsk || insightStreaming" size="small" :icon="Plus" @click="onNewConversation">{{ t('wb.side.new') }}</el-button>
        </div>
        <div class="conv-list">
          <div
            v-if="insightHistoryVisible"
            class="conv-item conv-item--insight"
            :class="{ 'is-active': insightMode }"
            @click="openInsight"
          >
            <div class="conv-title conv-title--with-tag">
              <span class="conv-insight-icon">◆</span>
              <span>{{ t('insight.cardTitle') }}</span>
              <span class="conv-insight-tag">{{ insightHistoryTag }}</span>
            </div>
            <div class="conv-meta">{{ insightHistoryMeta }}</div>
          </div>
          <div
            v-for="c in conversations"
            :key="c.id"
            class="conv-item"
            :class="{ 'is-active': c.id === activeConvId }"
            @click="selectConv(c.id)"
          >
            <div class="conv-title">{{ c.title }}</div>
            <div class="conv-meta">{{ t('wb.side.msgCount', { n: c.message_count }) }}</div>
            <el-icon class="conv-del" @click.stop="onDeleteConv(c)"><Delete /></el-icon>
          </div>
          <div v-if="!conversations.length" class="conv-empty">{{ t('wb.side.empty') }}</div>
        </div>
      </aside>

      <section class="xq-share-main">
        <div v-if="!canAsk" class="no-file-hint">
          <el-empty :description="noFileHint">
            <el-button
              v-if="!moduleDetail?.primary_document"
              type="primary"
              :icon="UploadFilled"
              @click="triggerUpload"
            >
              {{ t('wb.noFile.upload') }}
            </el-button>
          </el-empty>
        </div>

        <div v-else ref="scrollerRef" class="messages-scroller" :class="{ 'messages-scroller--insight': insightMode }">
          <template v-if="insightMode">
            <XlsxQaInsightReport
              :share-token="shareToken"
              @close="insightMode = false; insightStreaming = false"
              @streaming="insightStreaming = $event"
              @done="onInsightDone"
              @export-ppt="onExportInsightPpt"
              @export-pdf="onExportInsightPdf"
            />
          </template>
          <template v-else>
          <div v-if="!messages.length && !isStreaming" class="welcome">
            <button
              v-if="showInsightWelcomeCard"
              type="button"
              class="insight-entry-card"
              @click="openInsight"
            >
              <span class="insight-entry-badge">{{ t('insight.badge') }}</span>
              <div class="insight-entry-title">{{ t('insight.cardTitle') }}</div>
              <p class="insight-entry-desc">{{ t('insight.cardDesc') }}</p>
              <span class="insight-entry-cta">{{ t('insight.cardCta') }}</span>
            </button>
            <div class="welcome-title">{{ t('wb.welcome.title') }}</div>
            <div class="welcome-desc">{{ t('wb.welcome.desc') }}</div>
            <div class="welcome-samples">
              <el-button
                v-for="q in sampleQuestions"
                :key="q"
                size="small"
                round
                plain
                @click="askQuick(q)"
              >
                {{ q }}
              </el-button>
            </div>
          </div>

          <XlsxQaMessageBubble
            v-for="m in messages"
            :key="m._localKey || m.id"
            :message="m"
            :streaming="m._streaming"
            :selectable="false"
            :selected="false"
            @follow-up="askQuick"
          />
          </template>
        </div>

        <div v-if="!insightMode" class="composer" :class="{ 'is-disabled': !canAsk || isStreaming || insightStreaming }">
          <el-input
            v-model="questionInput"
            type="textarea"
            :rows="2"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="!canAsk || isStreaming || insightStreaming"
            :placeholder="canAsk ? t('wb.composer.placeholder') : t('wb.composer.disabled')"
            resize="none"
            @keydown.enter.exact.prevent="onSubmit"
          />
          <div class="composer-foot">
            <el-button
              type="primary"
              :disabled="!canAsk || !questionInput.trim()"
              :loading="isStreaming"
              :icon="Promotion"
              @click="onSubmit"
            >
              {{ t('wb.composer.send') }}
            </el-button>
          </div>
        </div>
      </section>

      <aside class="xq-share-right">
        <!-- 无文档：上传区 -->
        <div v-if="!hasDocuments && !moduleDetail?.primary_document" class="right-upload">
          <div class="right-title">{{ t('wb.right.uploadTitle') }}</div>
          <div class="right-desc">{{ t('wb.right.uploadDesc') }}</div>
          <input
            ref="fileInputRef"
            type="file"
            accept=".xlsx,.xlsm"
            style="display:none"
            @change="onFileChange"
          />
          <el-button
            type="primary"
            :loading="uploading"
            :icon="UploadFilled"
            style="width:100%"
            @click="triggerUpload"
          >
            {{ uploading ? t('wb.right.uploadingBtn', { p: uploadProgress }) : t('wb.right.uploadBtn') }}
          </el-button>
          <div v-if="uploading" class="upload-tip">{{ t('wb.right.uploadTip') }}</div>
        </div>

        <!-- 单文档模式（向后兼容） -->
        <div v-else-if="moduleDetail?.primary_document && !moduleHasMultiDocs" class="doc-panel">
          <div class="right-title">
            <span>{{ t('wb.right.dataFile') }}</span>
          </div>
          <div class="doc-info">
            <div class="doc-name">
              <el-icon><Grid /></el-icon>
              {{ moduleDetail.primary_document.file_name }}
            </div>
            <div class="doc-meta">
              <span>Sheet: {{ moduleDetail.primary_document.sheet_name || 'Sheet1' }}</span>
              <span>{{ t('wb.right.rows', { n: moduleDetail.primary_document.total_rows }) }}</span>
              <span>{{ t('wb.right.cols', { n: moduleDetail.primary_document.total_columns }) }}</span>
            </div>
          </div>

          <el-tabs v-model="rightTab" class="right-tabs">
            <el-tab-pane :label="t('wb.right.tab.columns')" name="columns">
              <div class="column-list">
                <div
                  v-for="col in moduleDetail.primary_document.columns"
                  :key="col.column_name"
                  class="column-row"
                >
                  <div class="column-main">
                    <div class="column-raw">{{ col.raw_header || col.column_name }}</div>
                    <div class="column-sub">
                      <code>{{ col.column_name }}</code>
                      <el-tag size="small" type="info">{{ col.column_type }}</el-tag>
                    </div>
                  </div>
                  <div v-if="col.sample?.length" class="column-samples" :title="col.sample.join(', ')">
                    e.g. {{ col.sample.slice(0, 3).join(' / ') }}
                  </div>
                </div>
              </div>
            </el-tab-pane>
            <el-tab-pane :label="t('wb.right.tab.understanding')" name="understanding">
              <div class="understanding-pane">
                <div
                  v-if="moduleDetail.primary_document.understanding_md"
                  class="understanding-md markdown-body"
                  v-html="renderedUnderstanding"
                />
                <el-empty v-else :description="t('wb.right.und.empty')" :image-size="64" />
              </div>
            </el-tab-pane>
            <el-tab-pane :label="t('wb.right.tab.preview')" name="preview" lazy>
              <div v-loading="previewLoading" class="preview-pane">
                <el-button size="small" plain @click="loadPreview">{{ t('wb.right.preview.refresh') }}</el-button>
                <el-table
                  v-if="preview?.columns?.length"
                  :data="previewRows"
                  size="small"
                  border
                  stripe
                  max-height="320"
                  style="margin-top:8px"
                >
                  <el-table-column
                    v-for="c in preview.columns"
                    :key="c"
                    :prop="c"
                    :label="c"
                    show-overflow-tooltip
                    min-width="120"
                  />
                </el-table>
                <div v-if="preview?.total_rows" class="preview-meta">
                  {{ t('wb.right.preview.meta', { shown: previewRows.length, got: preview.total_rows, total: moduleDetail.primary_document.total_rows }) }}
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>

        <!-- 多文档模式 -->
        <div v-else class="doc-panel multi-doc-panel">
          <el-tabs v-model="multiDocTab" class="multi-doc-tabs">
            <el-tab-pane :label="t('wb.right.multiFile', { n: allDocuments.length })" name="files">
              <div
                v-for="doc in allDocuments"
                :key="doc.id"
                class="doc-card"
              >
                <div class="doc-card-head" @click="toggleDocExpand(doc.id)">
                  <el-icon class="doc-expand-icon">
                    <ArrowRight v-if="!expandedDocIds.has(doc.id)" />
                    <ArrowDown v-else />
                  </el-icon>
                  <div class="doc-card-info">
                    <div class="doc-card-name">
                      <el-icon><Grid /></el-icon>
                      <span class="doc-card-filename">{{ doc.file_name }}</span>
                      <el-tag v-if="doc.status !== 'ready'" :type="doc.status === 'failed' ? 'danger' : 'warning'" size="small">
                        {{ t(`status.${doc.status}`) }}
                      </el-tag>
                    </div>
                    <div class="doc-card-meta">
                      <span>{{ t('wb.right.docSheetCount', { n: doc.sheet_count || 0 }) }}</span>
                      <span>{{ t('wb.right.rows', { n: doc.total_rows }) }}</span>
                      <span>{{ t('wb.right.cols', { n: doc.total_columns }) }}</span>
                    </div>
                  </div>
                </div>

                <!-- 展开的 Sheet 列表 -->
                <div v-show="expandedDocIds.has(doc.id)" class="doc-sheet-list">
                  <div
                    v-for="sh in doc.sheets || []"
                    :key="sh.id"
                    class="sheet-item"
                  >
                    <div
                      class="sheet-row"
                      :class="{ 'is-expanded': expandedSheetIds.has(sh.id) }"
                      @click="sh.status === 'ready' && toggleSheetExpand(sh.id)"
                    >
                      <el-icon class="sheet-expand-icon" v-if="sh.status === 'ready'">
                        <ArrowRight v-if="!expandedSheetIds.has(sh.id)" />
                        <ArrowDown v-else />
                      </el-icon>
                      <div class="sheet-row-main">
                        <div class="sheet-row-name">
                          <el-tag
                            :type="sh.status === 'ready' ? 'success' : sh.status === 'failed' ? 'danger' : 'warning'"
                            size="small"
                            effect="plain"
                          >
                            {{ t(`status.${sh.status}`) }}
                          </el-tag>
                          <span class="sheet-name-text">{{ sh.sheet_name }}</span>
                        </div>
                        <div class="sheet-row-meta">
                          <span>{{ sh.total_rows || 0 }} 行</span>
                          <span>{{ (sh.columns || []).length }} 列</span>
                        </div>
                      </div>
                    </div>

                    <!-- Sheet 详情面板 -->
                    <div v-if="expandedSheetIds.has(sh.id)" class="sheet-detail-panel">
                      <el-tabs
                        :model-value="getSheetDetailTab(sh.id)"
                        @update:model-value="setSheetDetailTab(sh.id, $event)"
                        class="sheet-detail-tabs"
                        size="small"
                      >
                        <el-tab-pane :label="t('wb.right.tab.columns')" name="columns">
                          <div class="column-list column-list-compact">
                            <div
                              v-for="col in sh.columns || []"
                              :key="col.column_name"
                              class="column-row"
                            >
                              <div class="column-main">
                                <div class="column-raw">{{ col.raw_header || col.column_name }}</div>
                                <div class="column-sub">
                                  <code>{{ col.column_name }}</code>
                                  <el-tag size="small" type="info">{{ col.column_type }}</el-tag>
                                </div>
                              </div>
                              <div v-if="col.sample?.length" class="column-samples" :title="col.sample.join(', ')">
                                e.g. {{ col.sample.slice(0, 3).join(' / ') }}
                              </div>
                            </div>
                          </div>
                        </el-tab-pane>
                        <el-tab-pane :label="t('wb.right.tab.understanding')" name="understanding">
                          <div class="understanding-pane">
                            <div
                              v-if="sh.understanding_md"
                              class="understanding-md markdown-body"
                              v-html="renderSimpleMarkdown(sh.understanding_md)"
                            />
                            <el-empty v-else :description="t('wb.right.und.empty')" :image-size="48" />
                          </div>
                        </el-tab-pane>
                        <el-tab-pane :label="t('wb.right.tab.preview')" name="preview" lazy>
                          <div v-loading="sheetPreviewLoading[sh.id]" class="preview-pane">
                            <el-button size="small" plain @click="loadSheetPreview(sh.id)">{{ t('wb.right.preview.refresh') }}</el-button>
                            <el-table
                              v-if="sheetPreview[sh.id]?.columns?.length"
                              :data="getSheetPreviewRows(sh.id)"
                              size="small"
                              border
                              stripe
                              max-height="240"
                              style="margin-top:8px"
                            >
                              <el-table-column
                                v-for="c in sheetPreview[sh.id].columns"
                                :key="c"
                                :prop="c"
                                :label="c"
                                show-overflow-tooltip
                                min-width="100"
                              />
                            </el-table>
                            <div v-if="sheetPreview[sh.id]?.total_rows" class="preview-meta">
                              {{ t('wb.right.preview.meta', { shown: getSheetPreviewRows(sh.id).length, got: sheetPreview[sh.id].total_rows, total: sh.total_rows }) }}
                            </div>
                          </div>
                        </el-tab-pane>
                      </el-tabs>
                    </div>
                  </div>
                  <div v-if="!doc.sheets?.length" class="sheet-empty">
                    {{ t('wb.right.und.notGenerated') }}
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <!-- 文件理解 tab -->
            <el-tab-pane
              v-if="moduleDetail?.module_understanding_md"
              label="文件理解"
              name="understanding"
            >
              <div class="file-understanding-pane">
                <div class="understanding-md markdown-body" v-html="renderSimpleMarkdown(moduleDetail.module_understanding_md)" />
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </aside>
    </div>
  </div>

  <!-- 导出 PPT -->
  <XlsxQaExportPptDialog
    v-model="exportDialogVisible"
    :conversation-id="activeConvId"
    :module-id="moduleDetail?.id"
    :messages="messages"
    :export-fn="shareExportPpt"
    :list-history-fn="shareListPptHistory"
    :get-download-url-fn="shareGetPptHistoryDownloadUrl"
    :delete-history-fn="shareDeletePptHistory"
  />

  <!-- 洞察报告导出 PPT -->
  <XlsxQaExportPptDialog
    v-model="insightExportDialogVisible"
    :insight-mode="true"
    :module-id="moduleDetail?.id"
    :export-fn="shareInsightPptExportFn"
    :list-history-fn="shareListPptHistory"
    :get-download-url-fn="shareGetPptHistoryDownloadUrl"
    :delete-history-fn="shareDeletePptHistory"
  />
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus,
  Delete,
  Download,
  UploadFilled,
  Grid,
  InfoFilled,
  Promotion,
  DocumentCopy,
  ArrowRight,
  ArrowDown,
} from '@element-plus/icons-vue'

import { createXlsxQaShareApi } from '@/api/xlsxQaShare'
import { askXlsxQaShareStream, fetchInsightShareReport } from '@/utils/xlsxQaSse'
import { renderSimpleMarkdown } from '@/utils/markdown'
import XlsxQaInsightReport from '@/components/xlsx-qa/XlsxQaInsightReport.vue'
import XlsxQaMessageBubble from '@/components/xlsx-qa/XlsxQaMessageBubble.vue'
import XlsxQaExportPptDialog from '@/components/xlsx-qa/XlsxQaExportPptDialog.vue'
import { useXqI18n } from '@/utils/xlsxQaI18n'

const props = defineProps({
  token: { type: String, default: '' }
})

const { t, lang, toggleLang } = useXqI18n()

const shareToken = computed(() => String(props.token || '').trim())
/** 每次调用新建 client（token 不变时开销可忽略） */
function sx() {
  return createXlsxQaShareApi(shareToken.value)
}

const loading = ref(false)
const moduleDetail = ref(null)
const conversations = ref([])
const activeConvId = ref(null)
const messages = ref([])

const uploading = ref(false)
const uploadProgress = ref(0)
const fileInputRef = ref(null)

const questionInput = ref('')
const isStreaming = ref(false)
const insightMode = ref(false)
const insightStreaming = ref(false)
const insightReportInfo = ref(null)
const abortCtrl = ref(null)
const scrollerRef = ref(null)

const exportDialogVisible = ref(false)
const insightExportDialogVisible = ref(false)
const pdfExporting = ref(false)

const rightTab = ref('columns')
const preview = ref(null)
const previewLoading = ref(false)

// 多文档状态
const multiDocTab = ref('files')
const expandedDocIds = ref(new Set())
const expandedSheetIds = ref(new Set())
const sheetDetailTab = ref({})
const sheetPreview = ref({})
const sheetPreviewLoading = ref({})

/** 分享页 PPT 导出：走 share token 路由，无需登录 */
function shareExportPpt(convId, data) {
  return sx().exportConversationPpt(convId, data)
}

/** 分享页洞察 PPT 导出 */
function shareInsightPptExportFn(_moduleId, _payload) {
  return sx().exportInsightPpt()
}

/** 分享页 PPT 历史列表 */
function shareListPptHistory() {
  return sx().listPptHistory()
}

/** 分享页 PPT 历史下载链接 */
function shareGetPptHistoryDownloadUrl(historyId) {
  return sx().getPptHistoryDownloadUrl(historyId)
}

/** 分享页删除 PPT 历史 */
function shareDeletePptHistory(historyId) {
  return sx().deletePptHistory(historyId)
}

function onExportInsightPpt() {
  if (insightStreaming.value || isStreaming.value) return
  if (insightReportInfo.value?.status !== 'done') {
    ElMessage.warning('请先生成完整的数据洞察报告')
    return
  }
  insightExportDialogVisible.value = true
}

async function onExportInsightPdf() {
  if (insightStreaming.value || isStreaming.value) return
  if (insightReportInfo.value?.status !== 'done') {
    ElMessage.warning('请先生成完整的数据洞察报告')
    return
  }
  pdfExporting.value = true
  try {
    const resp = await sx().exportInsightPdf()
    downloadBlobResponse(resp, '数据洞察报告.pdf')
    ElMessage.success('PDF 已开始下载')
  } catch (e) {
    ElMessage.error(e.message || '导出 PDF 失败')
  } finally {
    pdfExporting.value = false
  }
}

const hasAnyAssistant = computed(() =>
  messages.value.some((m) => m.role === 'assistant' && typeof m.id === 'number' && m.status !== 'failed')
)
const pdfExportDisabled = computed(() => {
  if (pdfExporting.value || insightStreaming.value || isStreaming.value) return true
  if (insightMode.value) return !canAsk.value
  return !activeConvId.value || !hasAnyAssistant.value
})

async function onExportPdf() {
  if (pdfExportDisabled.value) return
  pdfExporting.value = true
  try {
    const resp = insightMode.value
      ? await sx().exportInsightPdf()
      : await sx().exportConversationPdf(activeConvId.value, { include_subquestions: true, include_chart: true })
    downloadBlobResponse(resp, insightMode.value ? '数据洞察报告.pdf' : '数据问答报告.pdf')
    ElMessage.success('PDF 已开始下载')
  } catch (e) {
    ElMessage.error(e.message || '导出 PDF 失败')
  } finally {
    pdfExporting.value = false
  }
}

function downloadBlobResponse(resp, fallbackName) {
  const blob = resp?.data instanceof Blob ? resp.data : resp
  if (!(blob instanceof Blob)) return
  const cd = resp?.headers?.['content-disposition'] || resp?.headers?.['Content-Disposition'] || ''
  const m = cd.match(/filename\*=UTF-8''([^;]+)/i)
  const filename = m ? decodeURIComponent(m[1]) : fallbackName
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const renderedUnderstanding = computed(() =>
  renderSimpleMarkdown(moduleDetail.value?.primary_document?.understanding_md || '')
)

// 多文档辅助
const allDocuments = computed(() => moduleDetail.value?.documents || [])
const hasDocuments = computed(() => allDocuments.value.length > 0)
const moduleHasMultiDocs = computed(() => allDocuments.value.length > 0)

const docStatus = computed(() => {
  if (moduleHasMultiDocs.value) {
    for (const doc of allDocuments.value) {
      if (doc.status === 'failed') return 'failed'
      if (doc.status === 'parsing') return 'parsing'
    }
    return moduleDetail.value?.all_sheets_ready ? 'ready' : 'parsing'
  }
  return moduleDetail.value?.primary_document?.status
})
const docStatusLabel = computed(() => {
  const s = docStatus.value
  return s ? t(`status.${s}`) : ''
})
const docStatusType = computed(() => (
  { ready: 'success', failed: 'danger', parsing: 'warning', pending: 'warning' }[docStatus.value] || 'info'
))

const canAsk = computed(() => docStatus.value === 'ready')
const noFileHint = computed(() => {
  if (!hasDocuments.value && !moduleDetail.value?.primary_document) return t('wb.noFile.hint')
  if (docStatus.value !== 'ready') return t('wb.noFile.status', { s: docStatusLabel.value })
  return ''
})

function openInsight() {
  if (!canAsk.value || isStreaming.value || insightStreaming.value) return
  insightMode.value = true
}

/** 已成功生成过洞察报告时不再展示欢迎区的「一键生成洞察」推荐卡片 */
const showInsightWelcomeCard = computed(() => insightReportInfo.value?.status !== 'done')

const insightHistoryVisible = computed(() => {
  const s = insightReportInfo.value?.status
  return ['done', 'generating', 'failed'].includes(s)
})
const insightHistoryTag = computed(() => {
  const s = insightReportInfo.value?.status
  if (s === 'done') return '洞察'
  if (s === 'generating') return '生成中'
  if (s === 'failed') return '失败'
  return '洞察'
})
const insightHistoryMeta = computed(() => {
  const info = insightReportInfo.value || {}
  const n = Array.isArray(info.dimensions) ? info.dimensions.length : 0
  const t1 = n ? `${n} 个维度` : '数据洞察报告'
  const t2 = info.updated_at ? formatShortDate(info.updated_at) : ''
  return t2 ? `${t1} · ${t2}` : t1
})

async function loadInsightReportInfo() {
  try {
    const data = await fetchInsightShareReport(shareToken.value)
    insightReportInfo.value = data?.exists ? data : null
  } catch {
    insightReportInfo.value = null
  }
}

function onInsightDone() {
  insightStreaming.value = false
  loadInsightReportInfo()
}

function formatShortDate(s) {
  const d = new Date(s)
  if (isNaN(d.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const fallbackQuestions = computed(() => [
  t('wb.fallback.q1'),
  t('wb.fallback.q2'),
  t('wb.fallback.q3'),
])
const sampleQuestions = computed(() => {
  // 多文档模式：取第一个 sheet 的 suggested_questions
  if (moduleHasMultiDocs.value) {
    for (const doc of allDocuments.value) {
      for (const sh of (doc.sheets || [])) {
        if (sh.suggested_questions?.length) return sh.suggested_questions
      }
    }
  }
  const list = moduleDetail.value?.primary_document?.suggested_questions
  return Array.isArray(list) && list.length ? list : fallbackQuestions.value
})

// Sheet 展开和预览
function toggleDocExpand(docId) {
  const s = new Set(expandedDocIds.value)
  if (s.has(docId)) s.delete(docId)
  else s.add(docId)
  expandedDocIds.value = s
}

function toggleSheetExpand(sheetId) {
  const s = new Set(expandedSheetIds.value)
  if (s.has(sheetId)) s.delete(sheetId)
  else s.add(sheetId)
  expandedSheetIds.value = s
}

function getSheetDetailTab(sheetId) {
  return sheetDetailTab.value[sheetId] || 'columns'
}

function setSheetDetailTab(sheetId, tab) {
  sheetDetailTab.value = { ...sheetDetailTab.value, [sheetId]: tab }
  if (tab === 'preview' && !sheetPreview.value[sheetId]) {
    loadSheetPreview(sheetId)
  }
}

async function loadSheetPreview(sheetId) {
  let docId = null
  for (const doc of allDocuments.value) {
    if ((doc.sheets || []).some(s => s.id === sheetId)) {
      docId = doc.id
      break
    }
  }
  if (!docId) return
  sheetPreviewLoading.value = { ...sheetPreviewLoading.value, [sheetId]: true }
  try {
    const data = await sx().previewSheet(docId, sheetId, 20)
    sheetPreview.value = { ...sheetPreview.value, [sheetId]: data }
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    sheetPreviewLoading.value = { ...sheetPreviewLoading.value, [sheetId]: false }
  }
}

function getSheetPreviewRows(sheetId) {
  const p = sheetPreview.value[sheetId]
  if (!p?.columns?.length) return []
  const cols = p.columns
  return (p.rows || []).map((r) => {
    const o = {}
    cols.forEach((c, i) => {
      const v = r[i]
      o[c] = v === null || v === undefined ? '' : v
    })
    return o
  })
}

const previewRows = computed(() => {
  if (!preview.value?.columns?.length) return []
  const cols = preview.value.columns
  return (preview.value.rows || []).map((r) => {
    const o = {}
    cols.forEach((c, i) => {
      const v = r[i]
      o[c] = v === null || v === undefined ? '' : v
    })
    return o
  })
})

async function loadModule() {
  moduleDetail.value = await sx().getModule()
}

async function loadConversations() {
  conversations.value = await sx().listConversations()
  if (!activeConvId.value && conversations.value.length) {
    activeConvId.value = conversations.value[0].id
  }
}

async function loadMessages(convId) {
  if (!convId) {
    messages.value = []
    return
  }
  const rows = await sx().listMessages(convId)
  messages.value = rows.map((m) => ({ ...m }))
  scrollBottom()
}

function selectConv(id) {
  activeConvId.value = id
  insightMode.value = false
  insightStreaming.value = false
  loadMessages(id)
}

const skipNextAutoLoad = ref(false)

async function onNewConversation() {
  const conv = await sx().createConversation({})
  conversations.value.unshift({ ...conv })
  skipNextAutoLoad.value = true
  activeConvId.value = conv.id
  messages.value = []
}

async function onDeleteConv(c) {
  try {
    await ElMessageBox.confirm(t('wb.deleteConv.body', { t: c.title }), t('wb.deleteConv.title'), { type: 'warning' })
  } catch {
    return
  }
  await sx().deleteConversation(c.id)
  conversations.value = conversations.value.filter((x) => x.id !== c.id)
  if (activeConvId.value === c.id) {
    activeConvId.value = conversations.value[0]?.id || null
    await loadMessages(activeConvId.value)
  }
}

function triggerUpload() {
  fileInputRef.value?.click()
}

async function onFileChange(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  if (!/\.xlsm?$|\.xlsx$/i.test(file.name)) {
    ElMessage.error(t('wb.onlyXlsx'))
    return
  }
  uploading.value = true
  uploadProgress.value = 0
  try {
    await sx().uploadDocument(file, {
      onProgress: (p) => (uploadProgress.value = p)
    })
    ElMessage.success(t('wb.uploadOk'))
    await loadModule()
    _startParsePoller()
  } catch (err) {
    ElMessage.error(err.message || t('common.failed'))
  } finally {
    uploading.value = false
    uploadProgress.value = 0
  }
}

let _parsePoller = null
function _startParsePoller() {
  const needsPoll = moduleHasMultiDocs.value
    ? !moduleDetail.value?.all_sheets_ready
    : moduleDetail.value?.primary_document && !moduleDetail.value.primary_document.understanding_md
  if (!needsPoll) return
  _parsePoller = setInterval(async () => {
    try {
      const detail = await sx().getModule()
      moduleDetail.value = detail
      const done = moduleHasMultiDocs.value
        ? detail?.all_sheets_ready
        : detail?.primary_document?.understanding_md
      if (done) {
        clearInterval(_parsePoller)
        _parsePoller = null
      }
    } catch { /* ignore polling errors */ }
  }, 3000)
}

async function onDownload() {
  const doc = moduleDetail.value?.primary_document
  if (!doc) return
  const res = await sx().getDocumentDownloadUrl(doc.id)
  window.open(res.url, '_blank')
}

async function loadPreview() {
  const doc = moduleDetail.value?.primary_document
  if (!doc) return
  previewLoading.value = true
  try {
    preview.value = await sx().previewDocument(doc.id, 20)
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    previewLoading.value = false
  }
}

watch(rightTab, (v) => {
  if (v === 'preview' && !preview.value) loadPreview()
})

function askQuick(q) {
  questionInput.value = q
  onSubmit()
}

async function ensureConversation() {
  if (activeConvId.value) return activeConvId.value
  const conv = await sx().createConversation({})
  conversations.value.unshift({ ...conv })
  skipNextAutoLoad.value = true
  activeConvId.value = conv.id
  return conv.id
}

async function onSubmit() {
  const q = questionInput.value.trim()
  if (!q || isStreaming.value || !canAsk.value) return
  try {
    const convId = await ensureConversation()
    questionInput.value = ''

    const userMsg = {
      id: `tmp-user-${Date.now()}`,
      _localKey: `tmp-user-${Date.now()}`,
      conversation_id: convId,
      role: 'user',
      content: q,
      status: 'ok',
      extras: null
    }
    const assistantMsg = {
      id: `tmp-ast-${Date.now()}`,
      _localKey: `tmp-ast-${Date.now()}`,
      _streaming: true,
      _stage: null,
      conversation_id: convId,
      role: 'assistant',
      content: '',
      status: 'ok',
      extras: {
        plan_summary: '',
        subquestions: [],
        summary_markdown: '',
        follow_up_questions: []
      }
    }
    messages.value.push(userMsg, assistantMsg)
    const reactiveAssistant = messages.value[messages.value.length - 1]
    scrollBottom()

    isStreaming.value = true
    abortCtrl.value = new AbortController()

    await askXlsxQaShareStream(
      shareToken.value,
      convId,
      { question: q },
      {
        signal: abortCtrl.value.signal,
        onEvent: (evt, data) => handleSseEvent(reactiveAssistant, evt, data)
      }
    )

    reactiveAssistant._streaming = false
    loadConversations()
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant') {
      last.status = 'failed'
      last.content = e.message || t('bubble.failNote')
      last._streaming = false
      last._stage = null
    }
  } finally {
    isStreaming.value = false
    abortCtrl.value = null
  }
}

function handleSseEvent(msg, evt, data) {
  if (!data) return
  const extras = msg.extras
  if (evt === 'plan') {
    extras.plan_summary = data.plan_summary || ''
    extras.subquestions = (data.subquestions || []).map((sq) => ({
      id: sq.id,
      question: sq.question,
      purpose: sq.purpose || '',
      sql: '',
      sql_status: 'pending',
      columns: [],
      rows: [],
      total_rows: 0,
      error: null
    }))
  } else if (evt === 'sql') {
    const sq = extras.subquestions.find((s) => s.id === data.subquestion_id)
    if (sq) {
      sq.sql = data.sql || ''
      sq.sql_status = data.error ? 'error' : 'running'
      if (data.error) sq.error = data.error
    }
  } else if (evt === 'sql_result') {
    const sq = extras.subquestions.find((s) => s.id === data.subquestion_id)
    if (sq) {
      sq.sql_status = data.sql_status || 'ok'
      sq.columns = data.columns || []
      sq.rows = data.rows || []
      sq.total_rows = data.total_rows || 0
      sq.truncated = data.truncated || false
      sq.error = data.error || null
    }
  } else if (evt === 'chart') {
    if (Array.isArray(data.charts) && data.charts.length) {
      extras.charts = data.charts
      extras.primary_chart_id = data.primary_id || data.charts[0].subquestion_id
      extras.chart = data.chart || data.charts.find((c) => c.subquestion_id === extras.primary_chart_id) || data.charts[0]
    } else if (data.chart) {
      extras.chart = data.chart
      extras.charts = [data.chart]
      extras.primary_chart_id = data.chart.subquestion_id
    }
  } else if (evt === 'summary') {
    extras.summary_markdown = data.summary_markdown || ''
    extras.follow_up_questions = data.follow_up_questions || []
  } else if (evt === 'done') {
    msg._streaming = false
    if (data?.state) {
      Object.assign(extras, data.state)
    }
  } else if (evt === 'error') {
    msg.status = 'failed'
    msg.content = data.message || t('bubble.failNote')
  } else if (evt === 'stage_start') {
    msg._stage = { stage: data.stage || '', message: data.message || '' }
  } else if (evt === 'stage_error') {
    msg._stage = {
      stage: data.stage || '',
      message: data.message
        ? (lang.value === 'en' ? `(${data.message}, continuing…)` : `（${data.message}，继续下一步…）`)
        : (lang.value === 'en' ? '(Stage skipped, continuing…)' : '（该阶段跳过，继续下一步…）')
    }
  } else if (evt === 'assistant_message_saved') {
    if (typeof data.message_id === 'number') {
      msg.id = data.message_id
      if (data.status) msg.status = data.status
    }
  }
  scrollBottom()
}

function scrollBottom() {
  nextTick(() => {
    const el = scrollerRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
  })
}

onMounted(async () => {
  if (!shareToken.value) return
  loading.value = true
  try {
    await loadModule()
    await loadConversations()
    await loadInsightReportInfo()
    if (activeConvId.value) await loadMessages(activeConvId.value)
    _startParsePoller()
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  if (abortCtrl.value) abortCtrl.value.abort()
  if (_parsePoller !== null) {
    clearInterval(_parsePoller)
    _parsePoller = null
  }
})

watch(activeConvId, (v) => {
  if (skipNextAutoLoad.value) {
    skipNextAutoLoad.value = false
    return
  }
  if (v) loadMessages(v)
})
</script>

<style scoped>
.xq-share-invalid {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8fafc;
}
.xq-share {
  display: flex;
  flex-direction: column;
  height: 100vh;
  max-height: 100vh;
  overflow: hidden;
  background: #f8fafc;
}
.xq-share-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 6px;
}
.h-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
  min-width: 0;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.h-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.lang-toggle {
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #475569;
}
.lang-toggle-text { font-size: 12px; }

.xq-share-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 240px 1fr 340px;
  gap: 12px;
  padding: 12px;
  overflow: hidden;
}

/* ── Tablet (hide right panel) ── */
@media (max-width: 1199px) {
  .xq-share-body {
    grid-template-columns: 200px 1fr;
  }
  .xq-share-right {
    display: none;
  }
}

/* ── Mobile (stack vertically) ── */
@media (max-width: 767px) {
  .xq-share-body {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
    padding: 6px;
    gap: 6px;
  }
  .xq-share-side {
    max-height: 160px;
  }
  .xq-share-right {
    display: none;
  }
  .xq-share-head {
    padding: 8px 12px;
  }
  .h-title {
    font-size: 14px;
  }
  .conv-list {
    display: flex;
    flex-direction: row;
    overflow-x: auto;
    overflow-y: hidden;
    gap: 6px;
    padding: 6px;
  }
  .conv-item {
    flex-shrink: 0;
    max-width: 160px;
    margin-bottom: 0;
  }
  .side-head {
    padding: 8px 10px;
  }
  .messages-scroller {
    padding: 10px 12px;
  }
  .composer {
    padding: 8px 10px 10px;
  }
  .welcome {
    padding: 24px 12px;
  }
}

.xq-share-side {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  border-bottom: 1px solid #f1f5f9;
}
.conv-list {
  flex: 1;
  overflow: auto;
  padding: 6px;
}
.conv-item {
  position: relative;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.12s ease;
}
.conv-item:hover { background: #f1f5f9; }
.conv-item:hover .conv-del { opacity: 1; }
.conv-item.is-active {
  background: #eff6ff;
  box-shadow: inset 2px 0 0 #2563eb;
}
.conv-title {
  font-size: 13px;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-title--with-tag {
  display: flex;
  align-items: center;
  gap: 6px;
}
.conv-insight-icon {
  color: #0f766e;
  font-size: 10px;
}
.conv-insight-tag {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
  color: #0f766e;
  background: #ccfbf1;
  border: 1px solid #99f6e4;
}
.conv-item--insight {
  background: #f0fdfa;
}
.conv-item--insight.is-active {
  background: #ccfbf1;
  box-shadow: inset 2px 0 0 #0f766e;
}
.conv-meta {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}
.conv-del {
  position: absolute;
  top: 10px;
  right: 8px;
  opacity: 0;
  color: #ef4444;
  transition: opacity 0.12s ease;
}
.conv-empty {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
  padding: 20px 0;
}

.xq-share-main {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.messages-scroller {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}

.messages-scroller--insight {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  min-height: 0;
}
.insight-entry-card {
  display: block;
  width: 100%;
  max-width: 440px;
  margin: 0 auto 28px;
  padding: 18px 20px 16px;
  text-align: left;
  border: none;
  border-radius: 16px;
  cursor: pointer;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 55%, #fdf4ff 100%);
  box-shadow:
    0 0 0 1px rgba(99, 102, 241, 0.18),
    0 12px 28px rgba(79, 70, 229, 0.08);
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease;
}
.insight-entry-card:hover {
  transform: translateY(-2px);
  box-shadow:
    0 0 0 1px rgba(99, 102, 241, 0.28),
    0 16px 34px rgba(79, 70, 229, 0.12);
}
.insight-entry-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #4338ca;
  background: rgba(255, 255, 255, 0.85);
  padding: 4px 10px;
  border-radius: 999px;
  margin-bottom: 10px;
}
.insight-entry-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
  line-height: 1.35;
}
.insight-entry-desc {
  font-size: 13px;
  color: #475569;
  line-height: 1.55;
  margin: 0 0 14px;
}
.insight-entry-cta {
  display: inline-flex;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(90deg, #4f46e5, #7c3aed);
  padding: 8px 18px;
  border-radius: 999px;
}
.welcome {
  text-align: center;
  padding: 40px 16px;
}
.welcome-title {
  font-size: 16px;
  color: #1f2937;
  margin-bottom: 6px;
  font-weight: 600;
}
.welcome-desc {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 16px;
}
.welcome-samples {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}
.composer {
  border-top: 1px solid #f1f5f9;
  padding: 10px 12px 12px;
  background: #fff;
}
.composer.is-disabled { opacity: 0.7; }
.composer-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
.composer-tip {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11.5px;
  color: #94a3b8;
}
.no-file-hint {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.xq-share-right {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.right-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  padding: 12px 14px;
  border-bottom: 1px solid #f1f5f9;
}
.right-desc {
  color: #64748b;
  font-size: 12.5px;
  padding: 10px 14px;
  line-height: 1.55;
}
.right-upload {
  display: flex;
  flex-direction: column;
  padding: 0 14px 14px;
  gap: 10px;
}
.upload-tip {
  font-size: 12px;
  color: #64748b;
  text-align: center;
}
.doc-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.doc-info {
  padding: 10px 14px 12px;
  border-bottom: 1px solid #f1f5f9;
}
.doc-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #111827;
  font-size: 13px;
  word-break: break-all;
}
.doc-meta {
  margin-top: 4px;
  font-size: 11.5px;
  color: #94a3b8;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.right-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 14px;
}
.right-tabs :deep(.el-tabs__content) {
  overflow: auto;
}
.column-list { display: flex; flex-direction: column; }
.column-row {
  padding: 8px 0;
  border-bottom: 1px dashed #f1f5f9;
}
.column-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.column-raw {
  font-size: 13px;
  color: #111827;
  font-weight: 500;
  word-break: break-all;
  min-width: 0;
  flex: 1;
}
.column-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.column-sub code {
  background: #f3f4f6;
  color: #4b5563;
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
}
.column-samples {
  font-size: 11.5px;
  color: #94a3b8;
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.preview-meta {
  margin-top: 8px;
  font-size: 11.5px;
  color: #94a3b8;
}
.understanding-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 480px;
  overflow: auto;
}
.understanding-md {
  font-size: 12.5px;
  line-height: 1.65;
  color: #1f2937;
  padding: 4px 2px 12px;
}
.understanding-md :deep(h2) {
  font-size: 13.5px;
  margin: 14px 0 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid #e2e8f0;
  color: #0f172a;
}
.understanding-md :deep(h3) { font-size: 13px; margin: 10px 0 4px; color: #334155; }
.understanding-md :deep(ul),
.understanding-md :deep(ol) { padding-left: 1.35em; margin: 4px 0; }
.understanding-md :deep(ol) { list-style-type: decimal; }
.understanding-md :deep(li) { margin: 2px 0; }
.understanding-md :deep(li::marker) { color: #64748b; }
.understanding-md :deep(blockquote),
.understanding-md :deep(.md-blockquote) {
  margin: 6px 0;
  padding: 8px 10px 8px 12px;
  border-left: 3px solid #38bdf8;
  border-radius: 0 6px 6px 0;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
}
.understanding-md :deep(.md-table-wrap) {
  margin: 6px 0;
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.understanding-md :deep(code) {
  background: #f1f5f9; padding: 1px 5px; border-radius: 3px; font-size: 11.5px;
}
.understanding-md :deep(strong) { color: #0f172a; }
.understanding-md :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 6px 0;
  font-size: 11.5px;
}
.understanding-md :deep(th),
.understanding-md :deep(td) {
  border: 1px solid #e2e8f0;
  padding: 4px 8px;
  text-align: left;
  white-space: nowrap;
}
.understanding-md :deep(th) {
  background: #f1f5f9;
  font-weight: 600;
  color: #334155;
}
.understanding-md :deep(tr:hover td) {
  background: #f8fafc;
}

/* 多文档面板 */
.multi-doc-panel {
  overflow-y: auto;
}
.doc-card {
  border-bottom: 1px solid #f1f5f9;
}
.doc-card:last-child {
  border-bottom: none;
}
.doc-card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  cursor: pointer;
  transition: background 0.12s ease;
}
.doc-card-head:hover {
  background: #f8fafc;
}
.doc-expand-icon {
  font-size: 12px;
  color: #94a3b8;
  flex-shrink: 0;
  transition: transform 0.15s ease;
}
.doc-card-info {
  flex: 1;
  min-width: 0;
}
.doc-card-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 500;
  color: #111827;
}
.doc-card-filename {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-card-meta {
  margin-top: 2px;
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  gap: 10px;
}
.doc-sheet-list {
  padding: 0 14px 8px 28px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sheet-item {
  display: flex;
  flex-direction: column;
}
.sheet-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  border-radius: 6px;
  background: #f8fafc;
  transition: background 0.1s ease;
  cursor: pointer;
}
.sheet-row:hover {
  background: #f1f5f9;
}
.sheet-row.is-expanded {
  background: #eff6ff;
  border-radius: 6px 6px 0 0;
}
.sheet-expand-icon {
  font-size: 11px;
  color: #94a3b8;
  flex-shrink: 0;
  margin-right: 4px;
}
.sheet-row-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.sheet-row-name {
  display: flex;
  align-items: center;
  gap: 6px;
}
.sheet-name-text {
  font-size: 12px;
  color: #374151;
  font-weight: 500;
}
.sheet-row-meta {
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  gap: 8px;
}
.sheet-empty {
  font-size: 11px;
  color: #94a3b8;
  text-align: center;
  padding: 8px 0;
}

/* Sheet 详情面板 */
.sheet-detail-panel {
  border: 1px solid #e0e7ff;
  border-top: none;
  border-radius: 0 0 6px 6px;
  background: #fff;
  padding: 8px 10px;
}
.sheet-detail-tabs {
  min-height: 0;
}
.sheet-detail-tabs :deep(.el-tabs__header) {
  margin-bottom: 6px;
}
.sheet-detail-tabs :deep(.el-tabs__content) {
  overflow: auto;
  max-height: 320px;
}
.column-list-compact {
  max-height: 240px;
  overflow-y: auto;
}

/* 多文档 tabs */
.multi-doc-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.multi-doc-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  padding: 0 14px;
}
.multi-doc-tabs :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.multi-doc-tab-head {
  display: flex;
  justify-content: flex-end;
  padding: 0 14px 6px;
}

/* 文件理解 pane */
.file-understanding-pane {
  padding: 10px 14px 14px;
}
.file-understanding-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 6px;
}
</style>
