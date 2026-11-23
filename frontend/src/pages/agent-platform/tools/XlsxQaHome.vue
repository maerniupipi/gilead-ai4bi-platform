<template>
  <div class="xlsx-qa-home u-animate-in">
    <header class="xlsx-qa-home-head">
      <div class="head-main">
        <div class="head-crumbs">
          <router-link to="/agent-platform/tools" class="crumb-link">{{ t('crumb.tools') }}</router-link>
          <span class="crumb-sep">/</span>
          <span>{{ t('crumb.xlsxQa') }}</span>
        </div>
        <h1 class="xlsx-qa-home-title">{{ t('home.title') }}</h1>
        <p class="xlsx-qa-home-desc">
          {{ t('home.desc') }}
        </p>
      </div>
      <div class="head-actions">
        <el-input
          v-model="keyword"
          :placeholder="t('home.search.placeholder')"
          clearable
          class="head-search"
          @keyup.enter="load"
          @clear="load"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" :icon="Plus" @click="openCreate">{{ t('home.btn.create') }}</el-button>
        <el-button class="lang-toggle" :title="t('lang.switch')" @click="toggleLang">中 / EN</el-button>
      </div>
    </header>

    <div v-loading="loading" class="xlsx-qa-home-body">
      <div v-if="!loading && !modules.length" class="xlsx-qa-empty">
        <el-empty :description="t('home.empty')" />
      </div>

      <div v-else class="module-grid">
        <article
          v-for="m in modules"
          :key="m.id"
          class="module-card"
          @click="onOpen(m)"
        >
          <div class="module-card-head">
            <div class="module-card-icon">
              <el-icon :size="20"><Document /></el-icon>
            </div>
            <div class="module-card-title-row">
              <h3 class="module-card-title">{{ m.name }}</h3>
              <el-tag v-if="m.primary_document_status" size="small" :type="statusTagType(m.primary_document_status)">
                {{ statusLabel(m.primary_document_status) }}
              </el-tag>
            </div>
          </div>
          <div class="module-card-desc">{{ m.description || '—' }}</div>
          <div class="module-card-meta">
            <span>
              <el-icon><Files /></el-icon>
              {{ m.primary_document_file_name || t('home.card.noFile') }}
            </span>
            <span>
              <el-icon><ChatLineRound /></el-icon>
              {{ t('home.card.convs', { n: m.conversation_count || 0 }) }}
            </span>
          </div>
          <div class="module-card-foot">
            <span class="module-card-time">{{ m.updated_at || m.created_at }}</span>
            <div class="module-card-actions">
              <el-button link size="small" class="module-card-share" @click.stop="onShare(m)">
                {{ t('home.btn.share') }}
              </el-button>
              <el-button link size="small" class="module-card-delete" @click.stop="onDelete(m)">
                {{ t('common.delete') }}
              </el-button>
              <el-dropdown trigger="click" @click.stop>
              <el-button link size="small">
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click.stop="openEdit(m)">{{ t('common.edit') }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
              </el-dropdown>
            </div>
          </div>
        </article>
      </div>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? t('home.dialog.edit') : t('home.dialog.create')"
      width="460px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="100px" label-position="right">
        <el-form-item :label="t('home.form.name')" required>
          <el-input v-model="form.name" maxlength="128" show-word-limit :placeholder="t('home.form.name.placeholder')" />
        </el-form-item>
        <el-form-item :label="t('home.form.desc')">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            :placeholder="t('home.form.desc.placeholder')"
          />
        </el-form-item>
        <el-form-item :label="t('home.form.provider')">
          <el-select v-model="form.llm_provider_id" :placeholder="t('home.form.provider.placeholder')" clearable style="width: 100%">
            <el-option
              v-for="p in providers"
              :key="p.id"
              :label="p.name"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="availableModels.length" :label="t('home.form.model')">
          <el-select v-model="form.llm_model" :placeholder="t('home.form.model.placeholder')" clearable style="width: 100%">
            <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('home.form.language')">
          <el-select v-model="form.language" style="width: 100%">
            <el-option
              v-for="l in languageOptions"
              :key="l.value"
              :label="l.label"
              :value="l.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document,
  Files,
  ChatLineRound,
  MoreFilled,
  Plus,
  Search
} from '@element-plus/icons-vue'

import {
  listXlsxQaModules,
  createXlsxQaModule,
  updateXlsxQaModule,
  deleteXlsxQaModule,
  issueXlsxQaShare
} from '../../../api/xlsxQa'
import { buildXlsxQaShareUrl } from '../../../api/xlsxQaShare'
import { getModelProviders } from '../../../api/modelProvider'
import { useXqI18n, MODULE_LANGUAGES } from '../../../utils/xlsxQaI18n'

const { t, lang, toggleLang } = useXqI18n()

const router = useRouter()

const loading = ref(false)
const modules = ref([])
const keyword = ref('')

const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)
const form = ref({ name: '', description: '', llm_provider_id: null, llm_model: '', language: 'auto' })

// 模块语言选项（国际化显示）
const languageOptions = computed(() =>
  MODULE_LANGUAGES.map((l) => ({
    value: l.value,
    label: lang.value === 'zh' ? l.labelZh : l.labelEn
  }))
)

const providers = ref([])
const availableModels = computed(() => {
  const p = providers.value.find((x) => x.id === form.value.llm_provider_id)
  if (!p) return []
  const raw = p.models
  if (!raw) return []
  try {
    const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(arr) ? arr.map(String) : []
  } catch {
    return String(raw).split(',').map((s) => s.trim()).filter(Boolean)
  }
})

watch(
  () => form.value.llm_provider_id,
  () => {
    if (!availableModels.value.includes(form.value.llm_model)) {
      form.value.llm_model = ''
    }
  }
)

async function load() {
  loading.value = true
  try {
    modules.value = await listXlsxQaModules({ keyword: keyword.value || undefined })
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    loading.value = false
  }
}

async function loadProviders() {
  try {
    providers.value = await getModelProviders()
  } catch {
    providers.value = []
  }
}

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '', llm_provider_id: null, llm_model: '', language: 'auto' }
  dialogVisible.value = true
}

function openEdit(m) {
  editing.value = m
  form.value = {
    name: m.name,
    description: m.description || '',
    llm_provider_id: m.llm_provider_id || null,
    llm_model: m.llm_model || '',
    language: m.language || 'auto'
  }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.value.name.trim()) {
    ElMessage.warning(t('home.toast.needName'))
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await updateXlsxQaModule(editing.value.id, { ...form.value })
      ElMessage.success(t('home.toast.updated'))
    } else {
      await createXlsxQaModule({ ...form.value })
      ElMessage.success(t('home.toast.created'))
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  } finally {
    saving.value = false
  }
}

async function onDelete(m) {
  try {
    await ElMessageBox.confirm(
      t('home.delete.confirm.body', { name: m.name }),
      t('home.delete.confirm.title'),
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await deleteXlsxQaModule(m.id)
    ElMessage.success(t('home.toast.deleted'))
    await load()
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

function onOpen(m) {
  router.push(`/agent-platform/tools/xlsx-qa/${m.id}`)
}

async function onShare(m) {
  try {
    const out = await issueXlsxQaShare(m.id, { rotate: false })
    const url = buildXlsxQaShareUrl(out.token, out.share_public_base_url)
    try {
      await navigator.clipboard.writeText(url)
      ElMessage.success(t('home.share.copied'))
    } catch {
      try {
        await ElMessageBox.alert(url, t('home.share.manual'), {
          confirmButtonText: t('common.confirm')
        })
      } catch {
        /* user closed */
      }
    }
  } catch (e) {
    ElMessage.error(e.message || t('common.failed'))
  }
}

function statusTagType(s) {
  if (s === 'ready') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'parsing' || s === 'pending') return 'warning'
  return 'info'
}
function statusLabel(s) {
  if (!s) return ''
  const k = `status.${s}`
  const v = t(k)
  return v === k ? s : v
}

onMounted(() => {
  load()
  loadProviders()
})
</script>

<style scoped>
.xlsx-qa-home {
  padding: 24px 28px 40px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.xlsx-qa-home-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}
.head-crumbs {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 4px;
}
.crumb-link {
  color: #64748b;
  text-decoration: none;
}
.crumb-link:hover {
  color: #2563eb;
}
.crumb-sep {
  margin: 0 6px;
}
.xlsx-qa-home-title {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
  color: #0f172a;
}
.xlsx-qa-home-desc {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}
.xlsx-qa-home-desc .hint {
  color: #94a3b8;
  margin-left: 4px;
}
.head-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
.head-search {
  width: 260px;
}
.lang-toggle {
  font-weight: 600;
  letter-spacing: 0.5px;
  color: #475569;
}
.xlsx-qa-home-body {
  min-height: 200px;
}
.xlsx-qa-empty {
  padding: 48px 0;
}
.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.module-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 14px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.18s ease;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 172px;
}
.module-card:hover {
  border-color: #c6d1e0;
  box-shadow: 0 10px 24px -16px rgba(15, 23, 42, 0.35);
  transform: translateY(-2px);
}
.module-card-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.module-card-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #34d399 0%, #059669 100%);
  flex-shrink: 0;
}
.module-card-title-row {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.module-card-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.module-card-desc {
  font-size: 12.5px;
  color: #6b7280;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 36px;
}
.module-card-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #64748b;
}
.module-card-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}
.module-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
}
.module-card-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.module-card-share {
  color: #2563eb;
}
.module-card-share:hover {
  color: #1d4ed8;
}
.module-card-delete {
  color: #ef4444;
}
.module-card-delete:hover {
  color: #dc2626;
}
.module-card-time {
  font-size: 11px;
  color: #94a3b8;
}
</style>
