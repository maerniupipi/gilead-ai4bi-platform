<template>
  <el-drawer
    v-model="visible"
    :title="t('pd.title')"
    size="640px"
    :destroy-on-close="false"
    :close-on-click-modal="false"
    @open="handleOpen"
  >
    <div v-loading="loading" class="pd-wrap">
      <!-- 快速配置区 -->
      <div class="pd-quick-config">
        <div class="pd-quick-title">{{ t('pd.quickConfig') }}</div>
        <div class="pd-quick-desc">{{ t('pd.quickConfig.desc') }}</div>
        <div class="pd-quick-row">
          <div class="pd-quick-label">
            <span>{{ t('pd.showSql') }}</span>
            <span class="pd-quick-hint">{{ t('pd.showSql.desc') }}</span>
          </div>
          <el-switch v-model="localShowSql" @change="onShowSqlChange" />
        </div>
        <div class="pd-quick-row">
          <div class="pd-quick-label">
            <span>{{ t('pd.hideRightPanel') }}</span>
            <span class="pd-quick-hint">{{ t('pd.hideRightPanel.desc') }}</span>
          </div>
          <el-switch v-model="localHideRightPanel" @change="onHideRightPanelChange" />
        </div>
      </div>

      <el-divider style="margin: 12px 0" />

      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('pd.intro')"
      >
        <template #default>
          <div class="pd-tip">{{ t('pd.desc') }}</div>
        </template>
      </el-alert>

      <el-tabs v-model="activeKey" class="pd-tabs">
        <el-tab-pane
          v-for="s in sections"
          :key="s.key"
          :label="t(s.labelKey)"
          :name="s.key"
        >
          <div class="pd-section">
            <div class="pd-section-desc">{{ t(s.descKey) }}</div>
            <div class="pd-editor-head">
              <el-tag v-if="isCustom(s.key)" type="warning" size="small">{{ t('pd.customized') }}</el-tag>
              <el-tag v-else type="success" size="small">{{ t('pd.default') }}</el-tag>
              <span class="grow" />
              <el-button link size="small" @click="viewDefault(s.key)">{{ t('pd.viewDefault') }}</el-button>
              <el-button link size="small" @click="resetOne(s.key)" :disabled="!isCustom(s.key)">
                {{ t('pd.resetOne') }}
              </el-button>
            </div>
            <el-input
              v-model="form[s.key]"
              type="textarea"
              :rows="18"
              :autosize="{ minRows: 18, maxRows: 32 }"
              :placeholder="defaults[s.key] || t('pd.placeholder')"
              resize="vertical"
              class="pd-editor"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <div class="pd-footer">
        <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
        <el-button :disabled="!dirty" @click="resetAll">{{ t('pd.resetAll') }}</el-button>
        <el-button type="primary" :loading="saving" :disabled="!dirty" @click="save">
          {{ t('common.save') }}
        </el-button>
      </div>
    </template>

    <el-dialog
      v-model="defaultDialog"
      :title="t('pd.defaultTitle', { name: t(sections.find(s => s.key === defaultKey)?.labelKey || '') })"
      width="640px"
      append-to-body
    >
      <pre class="pd-default-preview">{{ defaults[defaultKey] }}</pre>
      <template #footer>
        <el-button @click="defaultDialog = false">{{ t('common.close') }}</el-button>
        <el-button type="primary" @click="copyDefault">{{ t('pd.copyDefault') }}</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getXlsxQaModulePrompts,
  updateXlsxQaModulePrompts
} from '../../api/xlsxQa'
import { useXqI18n } from '../../utils/xlsxQaI18n'

const { t } = useXqI18n()

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  moduleId: { type: Number, default: null },
  showSql: { type: Boolean, default: false },
  hideRightPanel: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'update:showSql', 'update:hideRightPanel'])

// 快速配置：show SQL
const localShowSql = ref(props.showSql)
watch(() => props.showSql, (v) => { localShowSql.value = v })
function onShowSqlChange(v) {
  emit('update:showSql', v)
}

// 快速配置：隐藏数据面板
const localHideRightPanel = ref(props.hideRightPanel)
watch(() => props.hideRightPanel, (v) => { localHideRightPanel.value = v })
function onHideRightPanelChange(v) {
  emit('update:hideRightPanel', v)
}

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const sections = [
  { key: 'plan_system',        labelKey: 'pd.tab.plan',    descKey: 'pd.tabDesc.plan' },
  { key: 'text_to_sql_system', labelKey: 'pd.tab.sql',     descKey: 'pd.tabDesc.sql' },
  { key: 'chart_system',       labelKey: 'pd.tab.chart',   descKey: 'pd.tabDesc.chart' },
  { key: 'summary_system',     labelKey: 'pd.tab.summary', descKey: 'pd.tabDesc.summary' }
]

const loading = ref(false)
const saving = ref(false)
const activeKey = ref('plan_system')

const form = reactive({
  plan_system: '',
  text_to_sql_system: '',
  chart_system: '',
  summary_system: ''
})
const current = reactive({
  plan_system: null,
  text_to_sql_system: null,
  chart_system: null,
  summary_system: null
})
const defaults = reactive({
  plan_system: '',
  text_to_sql_system: '',
  chart_system: '',
  summary_system: ''
})

const defaultDialog = ref(false)
const defaultKey = ref('plan_system')

function isCustom(k) {
  return !!(current[k] && current[k].trim())
}

const dirty = computed(() =>
  sections.some((s) => (form[s.key] || '') !== (current[s.key] || ''))
)

async function handleOpen() {
  if (!props.moduleId) return
  loading.value = true
  try {
    const res = await getXlsxQaModulePrompts(props.moduleId)
    for (const s of sections) {
      current[s.key] = res?.current?.[s.key] || ''
      defaults[s.key] = res?.defaults?.[s.key] || ''
      form[s.key] = current[s.key] || ''
    }
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    loading.value = false
  }
}

function viewDefault(k) {
  defaultKey.value = k
  defaultDialog.value = true
}
function copyDefault() {
  form[defaultKey.value] = defaults[defaultKey.value] || ''
  defaultDialog.value = false
  ElMessage.success(t('pd.copyOk'))
}

function resetOne(k) {
  form[k] = ''
}

async function resetAll() {
  try {
    await ElMessageBox.confirm(t('pd.resetAll.confirm'), t('common.confirm'), { type: 'warning' })
  } catch { return }
  for (const s of sections) form[s.key] = ''
}

async function save() {
  if (!props.moduleId) return
  saving.value = true
  try {
    const payload = {}
    for (const s of sections) {
      const v = (form[s.key] || '').trim()
      payload[s.key] = v || null
    }
    const res = await updateXlsxQaModulePrompts(props.moduleId, payload)
    for (const s of sections) {
      current[s.key] = res?.current?.[s.key] || ''
      form[s.key] = current[s.key] || ''
    }
    ElMessage.success(t('pd.saveOk'))
    visible.value = false
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    saving.value = false
  }
}

watch(
  () => props.moduleId,
  () => {
    if (visible.value) handleOpen()
  }
)
</script>

<style scoped>
.pd-wrap {
  padding: 4px 16px 16px;
}
.pd-quick-config {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 4px;
}
.pd-quick-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 4px;
}
.pd-quick-desc {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 10px;
}
.pd-quick-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.pd-quick-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  color: #374151;
}
.pd-quick-hint {
  font-size: 11.5px;
  color: #9ca3af;
}
.pd-tip {
  line-height: 1.6;
  font-size: 12.5px;
  color: #475569;
}
.pd-tabs {
  margin-top: 12px;
}
.pd-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pd-section-desc {
  font-size: 12.5px;
  color: #64748b;
  line-height: 1.6;
}
.pd-editor-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.grow { flex: 1; }
.pd-editor :deep(textarea) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12.5px;
  line-height: 1.6;
}
.pd-default-preview {
  max-height: 460px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12.5px;
  line-height: 1.6;
  margin: 0;
}
.pd-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
