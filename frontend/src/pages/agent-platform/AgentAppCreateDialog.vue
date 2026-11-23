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
    @closed="onDialogClosed"
  >
    <template #header>
      <div class="agent-app-create-dialog__head">
        <span class="agent-app-create-dialog__title">{{ dialogTitle }}</span>
        <p class="agent-app-create-dialog__subtitle">{{ dialogSubtitle }}</p>
      </div>
    </template>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-position="top"
      class="agent-app-create-dialog__form"
      @submit.prevent
    >
      <el-form-item label="应用名称 & 图标" prop="name">
        <div class="agent-app-create-dialog__name-row">
          <el-input
            v-model="form.name"
            size="large"
            maxlength="64"
            show-word-limit
            placeholder="给你的应用起个名字"
            clearable
            class="agent-app-create-dialog__name-input"
          />
          <div class="agent-app-create-dialog__icon-wrap" title="当前图标">
            <span class="agent-app-create-dialog__icon-preview">{{ form.icon }}</span>
          </div>
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
      </el-form-item>

      <el-form-item label="描述（可选）" prop="description">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="4"
          maxlength="500"
          show-word-limit
          placeholder="输入应用的描述"
          class="agent-app-create-dialog__textarea"
        />
      </el-form-item>

      <el-form-item label="对外调用 Token（可选）" prop="api_token">
        <el-input
          v-model="form.api_token"
          size="large"
          maxlength="128"
          show-password
          placeholder="留空则暂不配置"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="agent-app-create-dialog__footer">
        <el-button size="large" round @click="visibleInner = false">取消</el-button>
        <el-button type="primary" size="large" round :loading="submitting" @click="submit">
          {{ submitLabel }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import agentAppApi from '@/api/agentApp'
import { getOwnerDisplayNameForCreate } from '@/utils/auth'
import {
  AGENT_APP_ICON_CHOICES,
  DEFAULT_AGENT_APP_ICON,
  clampAgentAppIcon
} from '@/utils/agentAppIcon'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 校验后的导入包；有值时表示「导入」流程，保存时写入画布 */
  importPayload: { type: Object, default: null },
  /** 创建时写入的文件夹 ID（与实验中心一致） */
  folderId: { type: Number, default: undefined }
})

const emit = defineEmits(['update:modelValue', 'created', 'closed'])

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
  api_token: ''
})

const isImport = computed(() => props.importPayload != null)

const dialogTitle = computed(() =>
  isImport.value ? '从配置文件导入' : '创建空白应用'
)

const dialogSubtitle = computed(() =>
  isImport.value
    ? '请确认应用名称、描述与图标；保存后将创建应用并写入导入的画布'
    : '为工作流应用命名并选择展示图标'
)

const submitLabel = computed(() => (isImport.value ? '保存' : '创建'))

const rules = {
  name: [{ required: true, message: '请输入应用名称', trigger: 'blur' }]
}

function resetForm() {
  form.value = { name: '', description: '', icon: DEFAULT_AGENT_APP_ICON, api_token: '' }
  formRef.value?.clearValidate?.()
}

function applyFromImport(payload) {
  const a = payload?.app || {}
  const name = String(a.name || '导入的应用').trim() || '导入的应用'
  const desc = a.description
  form.value = {
    name,
    description:
      desc != null && String(desc).trim() !== '' ? String(desc).trim() : '',
    icon: clampAgentAppIcon(a.icon),
    api_token: ''
  }
}

function onDialogClosed() {
  resetForm()
  emit('closed')
}

watch(
  () => [props.modelValue, props.importPayload],
  ([open, payload]) => {
    if (!open) return
    if (payload) {
      applyFromImport(payload)
    } else {
      resetForm()
    }
  }
)

async function submit() {
  const formEl = formRef.value
  if (!formEl) return
  try {
    await formEl.validate()
  } catch {
    return
  }
  submitting.value = true
  try {
    if (isImport.value) {
      const payload = props.importPayload
      const owner = getOwnerDisplayNameForCreate()
      const app = await agentAppApi.createAgentApp({
        name: form.value.name,
        description: form.value.description || undefined,
        icon: clampAgentAppIcon(form.value.icon),
        ...(form.value.api_token.trim() ? { api_token: form.value.api_token.trim() } : {}),
        ...(owner ? { owner_display_name: owner } : {}),
        ...(props.folderId != null ? { folder_id: props.folderId } : {})
      })
      const firstVid = app.versions?.[0]?.id
      if (firstVid == null) {
        throw new Error('创建应用后未找到默认版本')
      }
      const wf = payload.workflow || {}
      await agentAppApi.putWorkflow(app.id, firstVid, {
        nodes: Array.isArray(wf.nodes) ? wf.nodes : [],
        edges: Array.isArray(wf.edges) ? wf.edges : [],
        expected_rev: 0,
        undo_stack: payload.undo_stack || undefined
      })
      ElMessage.success('导入成功')
      visibleInner.value = false
      emit('created', app)
    } else {
      const owner = getOwnerDisplayNameForCreate()
      const app = await agentAppApi.createAgentApp({
        name: form.value.name,
        description: form.value.description || undefined,
        icon: clampAgentAppIcon(form.value.icon),
        ...(form.value.api_token.trim() ? { api_token: form.value.api_token.trim() } : {}),
        ...(owner ? { owner_display_name: owner } : {}),
        ...(props.folderId != null ? { folder_id: props.folderId } : {})
      })
      visibleInner.value = false
      emit('created', app)
    }
  } catch (e) {
    ElMessage.error(e.message || (isImport.value ? '导入失败' : '创建失败'))
  } finally {
    submitting.value = false
  }
}
</script>
