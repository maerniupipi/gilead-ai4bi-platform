<template>
  <el-dialog
    v-model="visibleInner"
    class="agent-studio-dialog"
    width="680px"
    align-center
    destroy-on-close
    append-to-body
    :show-close="true"
    :close-on-click-modal="false"
    @closed="onClosed"
  >
    <template #header>
      <div class="agent-app-create-dialog__head">
        <span class="agent-app-create-dialog__title">编辑工作流</span>
        <p class="agent-app-create-dialog__subtitle">修改名称、备注、展示图标与对外调用 Token</p>
      </div>
    </template>

    <div v-if="app" class="agent-app-create-dialog__shell">
      <div class="agent-app-create-dialog__summary" aria-label="工作流概要">
        <div class="agent-app-create-dialog__preview-logo">
          <span>{{ form.icon }}</span>
        </div>
        <div class="agent-app-create-dialog__preview-copy">
          <strong>{{ form.name || '未命名工作流' }}</strong>
          <p>{{ currentFolderName }}</p>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="agent-app-create-dialog__form agent-app-create-dialog__fields"
        @submit.prevent
      >
        <section class="agent-app-create-dialog__section">
          <div class="agent-app-create-dialog__section-head">
            <span>Identity</span>
            <strong>基础身份</strong>
          </div>
          <el-form-item label="应用名称" prop="name">
            <el-input
              v-model="form.name"
              maxlength="128"
              show-word-limit
              placeholder="应用名称"
              clearable
              class="agent-app-create-dialog__name-input"
            />
          </el-form-item>
          <el-form-item v-if="folders.length" label="所属文件夹" prop="folder_id">
            <el-select v-model="form.folder_id" placeholder="请选择文件夹" style="width: 100%">
              <el-option v-for="f in folders" :key="f.id" :label="f.name" :value="f.id" />
            </el-select>
          </el-form-item>
        </section>

        <section class="agent-app-create-dialog__section">
          <div class="agent-app-create-dialog__section-head">
            <span>Visual</span>
            <strong>展示图标</strong>
          </div>
          <div class="agent-app-create-dialog__emoji-grid" aria-label="选择图标">
            <button
              v-for="e in emojiChoices"
              :key="e"
              type="button"
              class="agent-app-create-dialog__emoji"
              :class="{ 'is-active': form.icon === e }"
              @click="form.icon = e"
            >
              {{ e }}
            </button>
          </div>
        </section>

        <section class="agent-app-create-dialog__section agent-app-create-dialog__section--merged">
          <div class="agent-app-create-dialog__section-head">
            <span>Profile & Access</span>
            <strong>说明与调用</strong>
          </div>
          <div class="agent-app-create-dialog__inline-fields">
            <el-form-item label="备注" prop="description">
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="2"
                maxlength="500"
                show-word-limit
                placeholder="选填，展示在卡片上"
                class="agent-app-create-dialog__textarea"
              />
            </el-form-item>
            <el-form-item label="Token" prop="api_token">
              <el-input
                v-model="form.api_token"
                maxlength="128"
                show-password
                :placeholder="app.api_token_configured ? '已配置，留空则不修改' : '未配置，可输入新 token'"
              />
            </el-form-item>
          </div>
          <p class="agent-app-create-dialog__token-hint">
            {{ app.api_token_configured ? '当前已配置 Token；填写新值才会覆盖。' : '未配置 Token 时仅能在平台内调试。' }}
          </p>
        </section>
      </el-form>
    </div>

    <template #footer>
      <div class="agent-app-create-dialog__footer">
        <el-button size="large" round @click="visibleInner = false">取消</el-button>
        <el-button type="primary" size="large" round :loading="submitting" @click="submit">
          保存
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import agentAppApi from '@/api/agentApp'
import {
  AGENT_APP_ICON_CHOICES,
  DEFAULT_AGENT_APP_ICON,
  clampAgentAppIcon
} from '@/utils/agentAppIcon'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  app: { type: Object, default: null },
  folders: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:modelValue', 'updated'])

const visibleInner = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v)
})

const formRef = ref(null)
const submitting = ref(false)
const emojiChoices = AGENT_APP_ICON_CHOICES

const form = ref({
  name: '',
  description: '',
  icon: DEFAULT_AGENT_APP_ICON,
  folder_id: undefined,
  api_token: ''
})

const rules = {
  name: [{ required: true, message: '请输入应用名称', trigger: 'blur' }]
}

const currentFolderName = computed(() => {
  const fid = form.value.folder_id
  if (fid == null) return '未选择'
  return props.folders.find((f) => Number(f.id) === Number(fid))?.name || '未选择'
})

function syncFromApp() {
  const a = props.app
  if (!a) return
  form.value = {
    name: a.name || '',
    description: a.description || '',
    icon: clampAgentAppIcon(a.icon),
    folder_id: a.folder_id != null ? Number(a.folder_id) : undefined,
    api_token: ''
  }
  formRef.value?.clearValidate?.()
}

function onClosed() {
  form.value = { name: '', description: '', icon: DEFAULT_AGENT_APP_ICON, folder_id: undefined, api_token: '' }
  formRef.value?.clearValidate?.()
}

watch(
  () => [props.modelValue, props.app?.id],
  () => {
    if (props.modelValue && props.app) syncFromApp()
  },
  { immediate: true }
)

async function submit() {
  const formEl = formRef.value
  if (!formEl || !props.app?.id) return
  try {
    await formEl.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    const payload = {
      name: form.value.name,
      description: (form.value.description || '').trim(),
      icon: clampAgentAppIcon(form.value.icon)
    }
    if ((form.value.api_token || '').trim()) {
      payload.api_token = form.value.api_token.trim()
    }
    if (form.value.folder_id != null && props.folders.length) {
      payload.folder_id = form.value.folder_id
    }
    await agentAppApi.updateAgentApp(props.app.id, payload)
    visibleInner.value = false
    emit('updated')
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    submitting.value = false
  }
}
</script>
