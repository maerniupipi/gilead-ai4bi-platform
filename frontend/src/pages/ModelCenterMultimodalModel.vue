<template>
  <div class="model-center-page">
    <PageHeader :breadcrumbs="[{ label: '模型中心' }, { label: '多模态模型' }]">
      <template #actions><el-button :icon="Refresh" :disabled="saving" :loading="loading" @click="load">刷新配置</el-button></template>
    </PageHeader>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="page-alert" />
    <el-card shadow="never" class="ppt-model-card" v-loading="loading">
      <template #header>
        <div class="card-heading"><div class="heading-icon"><Document /></div><div><h2>AI PPT 生成模型</h2><p>从已有语言模型中选择，用于提炼多轮问答并生成汇报内容。</p></div><el-tag type="info" effect="plain">平台全局配置</el-tag></div>
      </template>
      <div v-if="current" class="current-model">
        <span class="current-label">当前使用</span><div class="current-value"><strong>{{ current.provider_name || '尚未选择供应商' }}</strong><code>{{ current.model || '尚未选择模型' }}</code></div>
        <el-tag :type="current.available ? 'success' : 'warning'" size="small">{{ current.available ? '已配置' : current.configured ? '需要重新选择' : '待配置' }}</el-tag>
      </div>
      <el-alert v-if="current?.reason" :title="current.reason" type="warning" :closable="false" show-icon class="page-alert" />
      <el-alert v-else-if="current?.source === 'environment'" title="当前沿用旧部署配置。保存后，AI PPT 将使用本页面选择的模型。" type="info" :closable="false" show-icon class="page-alert" />
      <el-alert v-if="!loading && loaded && !options.length" title="暂无可用语言模型。请先在语言模型中配置并启用供应商及模型。" type="warning" :closable="false" show-icon class="page-alert" />
      <el-form :model="form" label-position="top" @submit.prevent="save">
        <div class="model-fields">
          <el-form-item label="模型供应商"><el-select v-model="form.provider_id" filterable placeholder="选择语言模型供应商" :disabled="loading || saving || !loaded" @change="providerChanged"><el-option v-for="provider in options" :key="provider.id" :value="provider.id" :label="provider.name" /></el-select></el-form-item>
          <el-form-item label="生成模型"><el-select v-model="form.model" filterable placeholder="选择已有模型" :disabled="loading || saving || !selectedProvider"><el-option v-for="model in selectedProvider?.models || []" :key="model" :value="model" :label="model" /></el-select></el-form-item>
        </div>
        <div class="form-note">候选项来自已启用的 OpenAI 兼容语言模型，无需重复填写 API Key。<el-button link type="primary" @click="router.push('/management/model-provider')">管理语言模型 <ArrowRight /></el-button></div>
        <div class="form-actions"><el-button type="primary" :loading="saving" :disabled="loading || !canSave" @click="save">保存配置</el-button><el-button :disabled="loading || saving || !dirty" @click="reset">重置</el-button><span v-if="current?.updated_at">更新于 {{ formatTime(current.updated_at) }}</span></div>
      </el-form>
      <div class="usage-note"><strong>配置生效范围</strong><p>用于用户端“AI PPT 生成”。保存后对新提交的任务生效，已提交的任务继续使用提交时的模型。</p><p>普通 PPT 导出直接整理已有回答；问答模型仍在对应项目或工作流中配置。</p></div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Document, Refresh } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { getPptModel, getPptModelOptions, savePptModel } from '@/api/chatbiPptModel'
const router = useRouter()
const options = ref([]), current = ref(null), loading = ref(false), saving = ref(false), loaded = ref(false), error = ref('')
const form = reactive({ provider_id: null, model: '' })
const selectedProvider = computed(() => options.value.find(provider => provider.id === form.provider_id))
const dirty = computed(() => form.provider_id !== current.value?.provider_id || form.model !== (current.value?.model || ''))
const canSave = computed(() => loaded.value && dirty.value && selectedProvider.value?.models.includes(form.model))
const formatTime = value => new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
function providerChanged() { form.model = '' }
function reset() {
  const provider = options.value.find(item => item.id === current.value?.provider_id)
  form.provider_id = provider?.id || null
  form.model = provider?.models.includes(current.value?.model) ? current.value.model : ''
}
async function load() {
  loading.value = true; error.value = ''; loaded.value = false
  try {
    const [value, providers] = await Promise.all([getPptModel(), getPptModelOptions()])
    current.value = value; options.value = providers; loaded.value = true; reset()
  } catch (failure) { error.value = failure.message || '加载 AI PPT 模型配置失败' }
  finally { loading.value = false }
}
async function save() {
  if (!canSave.value || saving.value) return
  saving.value = true; error.value = ''
  try {
    current.value = await savePptModel({ provider_id: form.provider_id, model: form.model })
    reset(); ElMessage.success('AI PPT 模型配置已保存')
  } catch (failure) { error.value = failure.message || '保存 AI PPT 模型配置失败' }
  finally { saving.value = false }
}
onMounted(load)
</script>

<style scoped>
.model-center-page { padding: 28px 32px; }
.ppt-model-card { margin-top: 24px; max-width: 1160px; }
.ppt-model-card :deep(.el-card__header) { padding: 25px 28px; }.ppt-model-card :deep(.el-card__body) { padding: 28px; }
.card-heading { display: flex; align-items: center; gap: 16px; }
.heading-icon { display: grid; place-items: center; width: 46px; height: 46px; flex: 0 0 auto; border-radius: 12px; background: var(--brand-mgmt-soft, #fff6e6); color: var(--brand-mgmt, #f59e0b); }.heading-icon svg { width: 24px; height: 24px; }
.card-heading h2 { font-size: 18px; font-weight: 600; color: #252b35; margin: 0 0 7px; }.card-heading p { font-size: 13px; color: #89919e; line-height: 1.6; margin: 0; }.card-heading > .el-tag { margin-left: auto; }
.current-model { display: flex; align-items: center; gap: 22px; padding: 20px 22px; border: 1px solid #eceef2; border-radius: 8px; background: #fafbfc; margin-bottom: 26px; }.current-label { color: #8d95a2; font-size: 13px; flex: 0 0 auto; }.current-value { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; min-width: 0; }.current-value strong { font-size: 14px; color: #3d4654; font-weight: 500; }.current-value code { font: 13px/1.7 ui-monospace, monospace; color: #657184; overflow-wrap: anywhere; }.current-model > .el-tag { margin-left: auto; flex: 0 0 auto; }
.page-alert { margin: 18px 0; }.model-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }.model-fields :deep(.el-select) { width: 100%; }.model-fields :deep(.el-form-item__label) { color: #4e5765; padding-bottom: 10px; }
.form-note { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; color: #9098a4; font-size: 12px; line-height: 1.7; }.form-note :deep(svg) { width: 12px; margin-left: 5px; }.form-actions { display: flex; align-items: center; gap: 12px; margin-top: 26px; }.form-actions .el-button + .el-button { margin-left: 0; }.form-actions > span { color: #959da9; font-size: 12px; margin-left: 10px; }
.usage-note { margin-top: 30px; padding-top: 22px; border-top: 1px solid #edf0f3; }.usage-note strong { color: #697382; font-size: 13px; font-weight: 500; }.usage-note p { margin: 8px 0 0; color: #939ba7; font-size: 12px; line-height: 1.8; }
@media (max-width: 760px) { .model-center-page { padding: 20px 16px; }.model-fields { grid-template-columns: 1fr; gap: 0; }.card-heading { flex-wrap: wrap; }.card-heading > .el-tag { margin-left: 62px; }.current-model { flex-wrap: wrap; gap: 12px; }.form-actions { flex-wrap: wrap; }.form-actions > span { width: 100%; margin-left: 0; } }
</style>
