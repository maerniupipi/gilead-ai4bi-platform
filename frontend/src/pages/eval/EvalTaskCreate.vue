<template>
  <div class="eval-task-create">
    <div class="create-container">
      <PageHeader :breadcrumbs="[{ label: '任务状态', to: '/eval/tasks' }, { label: '新建任务' }]" />

      <div class="create-header">
        <h1 class="create-title">新建评测任务</h1>
        <p class="create-desc">选择评测集，配置评测对象和执行参数</p>
      </div>

      <div class="create-card">
        <el-steps :active="currentStep" finish-status="success" class="create-steps">
          <el-step title="选择评测集" />
          <el-step title="配置评测对象" />
          <el-step title="执行参数" />
          <el-step title="选择模板" />
          <el-step title="模型配置" />
        </el-steps>

        <div class="create-form">
          <!-- Step 1: 选择评测集 -->
          <div v-show="currentStep === 0" class="step-content">
            <el-form-item label="选择评测集" required>
              <el-select
                v-model="form.suite_id"
                placeholder="请选择要评测的评测集"
                style="width: 100%"
                filterable
                @change="handleSuiteChange"
                class="suite-select"
              >
                <el-option
                  v-for="suite in suites"
                  :key="suite.id"
                  :label="suite.name"
                  :value="suite.id"
                >
                  <div class="suite-option">
                    <span class="suite-name">{{ suite.name }}</span>
                    <span class="suite-case-count">{{ suite.case_count || 0 }} 条用例</span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>

            <el-form-item label="任务名称" prop="name" :error="nameError">
              <el-input
                v-model="form.name"
                placeholder="给任务起个名字"
                size="large"
                maxlength="200"
                @blur="validateName"
              />
            </el-form-item>

            <el-form-item label="任务描述">
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="2"
                placeholder="任务描述（可选）"
              />
            </el-form-item>
          </div>

          <!-- Step 2: 配置评测对象 -->
          <div v-show="currentStep === 1" class="step-content">
            <el-form-item label="评测对象类型" required>
              <div class="target-type-cards">
                <div
                  v-for="type in targetTypes"
                  :key="type.value"
                  class="target-type-card"
                  :class="{
                    active: form.target_type === type.value,
                    disabled: type.disabled
                  }"
                  @click="!type.disabled && selectTargetType(type.value)"
                >
                  <div class="card-body">
                    <el-icon class="type-icon"><component :is="type.icon" /></el-icon>
                    <span class="type-label">{{ type.label }}</span>
                  </div>
                  <span v-if="type.disabled" class="coming-soon">待开放</span>
                </div>
              </div>
            </el-form-item>

            <el-form-item v-if="form.target_type === 'lab'" label="选择评测对象" required>
              <el-select
                v-model="form.target_id"
                placeholder="选择实验室"
                style="width: 100%"
                filterable
              >
                <el-option
                  v-for="lab in labs"
                  :key="lab.id"
                  :label="lab.name"
                  :value="lab.id"
                />
              </el-select>
            </el-form-item>
          </div>

          <!-- Step 3: 执行参数 -->
          <div v-show="currentStep === 2" class="step-content">
            <el-form-item label="超时时间（秒）">
              <el-input-number
                v-model="form.exec_params.timeout_seconds"
                :min="30"
                :max="600"
                style="width: 100%"
              />
              <div class="field-tip">单条用例执行超时；评测会按用例顺序逐条执行。</div>
            </el-form-item>
          </div>

          <!-- Step 4: 选择模板 -->
          <div v-show="currentStep === 3" class="step-content">
            <div class="model-config-intro">
              <p>选择评测对比的提示词模板。模板定义了 AI 如何判断生成结果与期望答案的一致性。</p>
            </div>
            <el-form-item label="对比模板">
              <el-select
                v-model="form.comparison_template_id"
                placeholder="选择对比模板（可选，不选则使用默认规则）"
                style="width: 100%"
                filterable
                clearable
              >
                <el-option
                  v-for="tpl in comparisonTemplates"
                  :key="tpl.id"
                  :label="tpl.name"
                  :value="tpl.id"
                >
                  <div class="template-option">
                    <span class="template-name">{{ tpl.name }}</span>
                    <span class="template-desc">{{ tpl.description || getMethodLabel(tpl.comparison_method) }}</span>
                  </div>
                </el-option>
              </el-select>
            </el-form-item>

            <div v-if="selectedTemplate" class="template-preview">
              <div class="preview-section">
                <div class="preview-label">系统提示词</div>
                <div class="preview-content">{{ selectedTemplate.system_prompt }}</div>
              </div>
              <div class="preview-section">
                <div class="preview-label">用户提示词</div>
                <div class="preview-content">{{ selectedTemplate.user_prompt }}</div>
              </div>
            </div>
          </div>

          <!-- Step 5: 模型配置 -->
          <div v-show="currentStep === 4" class="step-content">
            <div class="model-config-intro">
              <p>选择用于评测对比的 LLM 模型。该模型将自动判断实验室生成的 SQL 是否与预期答案逻辑一致。</p>
            </div>
            <el-form-item label="模型供应商" required>
              <el-select
                v-model="form.exec_params.llm_provider_id"
                placeholder="选择模型供应商"
                style="width: 100%"
                filterable
                @change="handleProviderChange"
              >
                <el-option
                  v-for="p in providers"
                  :key="p.id"
                  :label="p.name"
                  :value="p.id"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="模型" required>
              <el-select
                v-model="form.exec_params.llm_model"
                placeholder="选择模型"
                style="width: 100%"
                filterable
                :disabled="!form.exec_params.llm_provider_id"
              >
                <el-option
                  v-for="m in availableModels"
                  :key="m"
                  :label="m"
                  :value="m"
                />
              </el-select>
              <div class="field-tip" v-if="!form.exec_params.llm_provider_id">请先选择模型供应商</div>
            </el-form-item>
          </div>
        </div>

        <div class="create-footer">
          <div class="footer-left">
            <el-button v-if="currentStep > 0" @click="currentStep--" class="prev-btn">
              上一步
            </el-button>
          </div>
          <div class="footer-right">
            <el-button
              v-if="currentStep < 4"
              type="primary"
              @click="currentStep++"
              :disabled="!canNext"
              class="next-btn"
            >
              下一步
            </el-button>
            <template v-else>
              <el-button @click="handleSubmit('create')" :loading="submitting" class="action-btn">
                创建
              </el-button>
              <el-button @click="openScheduleDialog" :loading="submitting" class="action-btn">
                定时执行
              </el-button>
              <el-button type="primary" @click="handleSubmit('start')" :loading="submitting" class="action-btn action-btn-primary">
                立即执行
              </el-button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 定时执行弹窗 -->
    <el-dialog
      v-model="scheduleDialogVisible"
      title="定时执行"
      width="440px"
      :close-on-click-modal="false"
    >
      <div class="schedule-presets">
        <div class="presets-label">快捷选择</div>
        <div class="presets-grid">
          <div
            v-for="p in schedulePresets"
            :key="p.label"
            class="preset-chip"
            :class="{ active: selectedPreset === p.label }"
            @click="selectPreset(p)"
          >
            {{ p.label }}
          </div>
        </div>
      </div>
      <div class="schedule-custom">
        <div class="custom-label">或自定义时间</div>
        <el-time-picker
          v-model="customTime"
          placeholder="选择时分"
          format="HH:mm"
          value-format="HH:mm"
          style="width: 100%"
          :disabled-hours="disabledHours"
          :disabled-minutes="disabledMinutes"
          @change="onCustomTimeChange"
        />
        <div class="field-tip">仅支持选择未来 24 小时内的时间</div>
      </div>
      <div v-if="scheduledAt" class="schedule-preview">
        将在 <strong>{{ formatScheduledAt(scheduledAt) }}</strong> 自动执行
      </div>
      <template #footer>
        <el-button @click="scheduleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleScheduleConfirm" :loading="submitting" :disabled="!scheduledAt">
          确认定时
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useSpaceContext } from '@/utils/spaceContext'
import * as evalApi from '@/api/eval'
import { listAutobiProjects } from '@/api/autobi'
import { getModelProviders } from '@/api/modelProvider'
import { Cpu, Collection, Connection } from '@element-plus/icons-vue'

const router = useRouter()
const { currentSpace } = useSpaceContext()

const currentStep = ref(0)
const submitting = ref(false)
const suites = ref([])
const labs = ref([])
const providers = ref([])
const availableModels = ref([])
const comparisonTemplates = ref([])
const existingTaskNames = ref([])
const nameError = ref('')
const scheduleDialogVisible = ref(false)
const scheduledAt = ref(null)
const selectedPreset = ref(null)
const customTime = ref(null)

const schedulePresets = [
  { label: '30 分钟后', minutes: 30 },
  { label: '1 小时后', minutes: 60 },
  { label: '2 小时后', minutes: 120 },
  { label: '4 小时后', minutes: 240 },
  { label: '明天 9:00', minutes: -1 },
]

const targetTypes = [
  { value: 'lab', label: '实验室', icon: Collection, disabled: false },
  { value: 'agent', label: '工作流', icon: Cpu, disabled: true },
  { value: 'api', label: '开放 API', icon: Connection, disabled: true },
]

const form = reactive({
  suite_id: null,
  name: '',
  description: '',
  target_type: 'lab',
  target_id: null,
  comparison_template_id: null,
  exec_params: {
    timeout_seconds: 180,
    llm_provider_id: null,
    llm_model: null,
  },
})

const selectedTemplate = computed(() => {
  if (!form.comparison_template_id) return null
  return comparisonTemplates.value.find(t => t.id === form.comparison_template_id) || null
})

function getMethodLabel(method) {
  const map = { llm_judge: 'LLM 评判', exact: '精确匹配', contains: '包含匹配', regex: '正则匹配' }
  return map[method] || method
}

const canNext = computed(() => {
  if (currentStep.value === 0) {
    return form.suite_id && form.name && !nameError.value
  }
  if (currentStep.value === 1) {
    return form.target_id
  }
  if (currentStep.value === 4) {
    return form.exec_params.llm_provider_id && form.exec_params.llm_model
  }
  return true
})

function formatDate() {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

async function loadSuites() {
  if (!currentSpace.value?.id) return
  try {
    const data = await evalApi.getEvalSuites(currentSpace.value.id, { limit: 100 })
    suites.value = data.items || []
  } catch (e) {
    console.error('加载评测集失败:', e)
  }
}

async function loadExistingTaskNames(suiteId) {
  try {
    const data = await evalApi.getEvalTasks(currentSpace.value.id, { suite_id: suiteId, limit: 200 })
    existingTaskNames.value = (data.items || []).map(t => t.name)
  } catch (e) {
    existingTaskNames.value = []
  }
}

function validateName() {
  if (!form.name.trim()) {
    nameError.value = '任务名称不能为空'
    return
  }
  if (existingTaskNames.value.includes(form.name.trim())) {
    nameError.value = '该评测集下已存在同名任务，请修改名称'
    return
  }
  nameError.value = ''
}

async function handleSuiteChange(suiteId) {
  const suite = suites.value.find(s => s.id === suiteId)
  if (suite) {
    form.name = `${suite.name}-评测任务-${formatDate()}`
    nameError.value = ''
    await loadExistingTaskNames(suiteId)
    validateName()
  }
}

function selectTargetType(type) {
  form.target_type = type
  form.target_id = null
}

function openScheduleDialog() {
  selectedPreset.value = null
  customTime.value = null
  scheduledAt.value = null
  scheduleDialogVisible.value = true
}

function selectPreset(preset) {
  selectedPreset.value = preset.label
  customTime.value = null
  const now = new Date()
  if (preset.minutes === -1) {
    // 明天 9:00
    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)
    tomorrow.setHours(9, 0, 0, 0)
    scheduledAt.value = formatForApi(tomorrow)
  } else {
    const target = new Date(now.getTime() + preset.minutes * 60 * 1000)
    scheduledAt.value = formatForApi(target)
  }
}

function onCustomTimeChange(val) {
  if (!val) return
  selectedPreset.value = null
  const [h, m] = val.split(':').map(Number)
  const now = new Date()
  const target = new Date(now)
  target.setHours(h, m, 0, 0)
  // 如果选的时间已过，推到明天
  if (target <= now) {
    target.setDate(target.getDate() + 1)
  }
  const max = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  if (target > max) {
    ElMessage.warning('时间不能超过 24 小时后')
    customTime.value = null
    scheduledAt.value = null
    return
  }
  scheduledAt.value = formatForApi(target)
}

function disabledHours() {
  const now = new Date()
  const max = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  const hours = []
  // 如果是今天，禁用已过的小时
  for (let i = 0; i < 24; i++) {
    const test = new Date(now)
    test.setHours(i, 59, 0, 0)
    if (test <= now) hours.push(i)
  }
  return hours
}

function disabledMinutes(hour) {
  const now = new Date()
  if (hour === now.getHours()) {
    const mins = []
    for (let i = 0; i <= now.getMinutes(); i++) mins.push(i)
    return mins
  }
  return []
}

function formatForApi(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${d}T${h}:${min}:00`
}

function formatScheduledAt(val) {
  if (!val) return ''
  return new Date(val).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function buildPayload() {
  const lab = labs.value.find(l => l.id === form.target_id)
  const payload = {
    suite_id: form.suite_id,
    name: form.name.trim(),
    description: form.description,
    exec_params: {
      timeout_seconds: form.exec_params.timeout_seconds,
    },
    sub_tasks: [{
      target_type: form.target_type,
      target_id: form.target_id,
      target_config: {
        api_access_id: lab?.api_access_id || '',
        llm_provider_id: form.exec_params.llm_provider_id,
        llm_model: form.exec_params.llm_model,
      },
    }],
  }
  if (form.comparison_template_id) {
    payload.comparison_template_id = form.comparison_template_id
    payload.output_template_id = form.comparison_template_id
  }
  return payload
}

async function handleScheduleConfirm() {
  if (!scheduledAt.value) {
    ElMessage.warning('请选择执行时间')
    return
  }
  if (!form.suite_id) {
    ElMessage.warning('请选择评测集')
    return
  }
  validateName()
  if (nameError.value) {
    ElMessage.warning(nameError.value)
    return
  }
  if (!form.target_id) {
    ElMessage.warning('请选择评测对象')
    return
  }

  submitting.value = true
  try {
    const data = { ...buildPayload(), scheduled_at: scheduledAt.value }
    await evalApi.createEvalTask(currentSpace.value.id, data)
    ElMessage.success('定时任务已创建')
    scheduleDialogVisible.value = false
    scheduledAt.value = null
    router.push('/eval/tasks')
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  } finally {
    submitting.value = false
  }
}

async function loadLabs() {
  try {
    const spaceId = currentSpace.value?.id
    if (!spaceId) return
    const res = await listAutobiProjects({ space_id: spaceId, limit: 200 })
    labs.value = (res.items || res || [])
  } catch (e) {
    console.error('加载实验室列表失败:', e)
  }
}

async function loadProviders() {
  try {
    const res = await getModelProviders({ limit: 100 })
    const items = res.items || res || []
    providers.value = items.filter(p => p.is_active && p.protocol === 'openai')
  } catch (e) {
    console.error('加载模型供应商失败:', e)
  }
}

function handleProviderChange(providerId) {
  const provider = providers.value.find(p => p.id === providerId)
  form.exec_params.llm_model = null
  availableModels.value = []
  if (provider) {
    try {
      const models = JSON.parse(provider.models || '[]')
      availableModels.value = Array.isArray(models) ? models : []
    } catch {
      availableModels.value = (provider.models || '').split(',').map(s => s.trim()).filter(Boolean)
    }
    // 自动选中第一个模型
    if (availableModels.value.length > 0) {
      form.exec_params.llm_model = availableModels.value[0]
    }
  }
}

async function handleSubmit(mode) {
  if (!form.suite_id) {
    ElMessage.warning('请选择评测集')
    return
  }
  validateName()
  if (nameError.value) {
    ElMessage.warning(nameError.value)
    return
  }
  if (!form.target_id) {
    ElMessage.warning('请选择评测对象')
    return
  }
  if (!form.exec_params.llm_provider_id || !form.exec_params.llm_model) {
    ElMessage.warning('请在「模型配置」步骤中选择模型供应商和模型')
    return
  }

  submitting.value = true
  try {
    const data = buildPayload()
    const task = await evalApi.createEvalTask(currentSpace.value.id, data)

    if (mode === 'start') {
      ElMessage.success('任务已创建，正在后台启动')
      router.push('/eval/tasks')
      evalApi.startEvalTask(task.id, currentSpace.value.id).catch((e) => {
        ElMessage.warning('任务已创建，但后台启动失败，请到任务列表重试：' + (e.message || e))
      })
    } else {
      ElMessage.success('任务已创建')
      router.push('/eval/tasks')
    }
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  } finally {
    submitting.value = false
  }
}

async function loadComparisonTemplates() {
  if (!currentSpace.value?.id) return
  try {
    const data = await evalApi.getComparisonTemplates(currentSpace.value.id, { limit: 100 })
    comparisonTemplates.value = data.items || []
  } catch (e) {
    console.error('加载对比模板失败:', e)
  }
}

onMounted(() => {
  loadSuites()
  loadLabs()
  loadProviders()
  loadComparisonTemplates()
})

watch(() => currentSpace.value?.id, (newId) => {
  if (newId) {
    loadSuites()
    loadLabs()
    loadProviders()
    loadComparisonTemplates()
  }
})
</script>

<style scoped>
.eval-task-create {
  padding: 28px 32px 40px;
  display: flex;
  justify-content: center;
  background: var(--bg-primary);
  min-height: 100%;
}

.create-container {
  width: 100%;
  max-width: 680px;
}

/* ── Header ── */
.create-header {
  margin-bottom: 24px;
}

.create-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 6px 0;
}

.create-desc {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

/* ── Single card ── */
.create-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 28px 32px 0;
  box-shadow: var(--shadow-xs);
}

/* ── Steps ── */
.create-steps {
  margin-bottom: 28px;
}

.create-steps :deep(.el-step__title) {
  font-size: 13px;
  font-weight: 500;
}

.create-steps :deep(.el-step__title.is-process) {
  font-weight: 600;
  color: var(--el-color-primary);
}

.create-steps :deep(.el-step__head.is-process) {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
}

.create-steps :deep(.el-step__head.is-finish) {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
}

.create-steps :deep(.el-step__title.is-finish) {
  color: var(--el-color-primary);
}

/* ── Form body ── */
.create-form {
  padding-bottom: 28px;
}

/* Labels on top — all inputs align regardless of label text length */
.create-form :deep(.el-form-item) {
  display: flex;
  flex-direction: column;
  margin-bottom: 20px;
}

.create-form :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

.create-form :deep(.el-form-item__label) {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  padding-bottom: 6px;
  text-align: left;
  line-height: 1.4;
}

.create-form :deep(.el-form-item__content) {
  flex: 1;
  width: 100%;
}

.create-form :deep(.el-input__wrapper),
.create-form :deep(.el-textarea__inner) {
  border-radius: 6px;
}

.create-form :deep(.el-select .el-input__wrapper) {
  border-radius: 6px;
}

.step-content {
  min-height: 180px;
}

/* ── Suite option ── */
.suite-option {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.suite-name {
  font-weight: 500;
}

.suite-case-count {
  font-size: 12px;
  color: var(--text-muted);
}

/* ── Target type cards ── */
.target-type-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  width: 100%;
  align-items: stretch;
}

.target-type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 10px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.18s ease;
  width: 100%;
  min-height: 108px;
  box-sizing: border-box;
}

.target-type-card:hover:not(.disabled) {
  border-color: var(--el-color-primary-light-5);
  background: color-mix(in srgb, var(--el-color-primary-light-9) 65%, #fff 35%);
}

.target-type-card.active {
  border-color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary-light-9) 70%, #fff 30%);
}

.target-type-card.disabled {
  opacity: 0.55;
  cursor: not-allowed;
  background: color-mix(in srgb, var(--bg-tertiary) 90%, #fff 10%);
}

.card-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.type-icon {
  font-size: 22px;
  color: var(--text-muted);
  transition: color 0.2s;
}

.target-type-card.active .type-icon {
  color: var(--el-color-primary);
}

.type-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  line-height: 1.2;
}

.target-type-card.active .type-label {
  color: var(--el-color-primary);
  font-weight: 600;
}

.coming-soon {
  font-size: 10px;
  color: var(--text-muted);
  padding: 1px 8px;
  background: color-mix(in srgb, var(--bg-tertiary) 88%, #fff 12%);
  border-radius: 999px;
}

/* ── Field tip ── */
.field-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-warning);
  line-height: 1.5;
}

/* ── Model config intro ── */
.model-config-intro {
  margin-bottom: 20px;
  padding: 12px 16px;
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
  border-left: 3px solid var(--el-color-primary);
}

.model-config-intro p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* ── Footer (inside card, separated by border) ── */
.create-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 0;
  border-top: 1px solid var(--border-color);
  margin: 0 -32px;
  padding-left: 32px;
  padding-right: 32px;
}

.footer-left {
  display: flex;
  gap: 12px;
}

.footer-right {
  display: flex;
  gap: 10px;
}

.prev-btn {
  border-radius: 8px;
}

.next-btn,
.action-btn {
  border-radius: 8px;
  font-weight: 500;
  min-width: 90px;
}

.action-btn-primary {
  min-width: 100px;
}

/* ── Schedule presets ── */
.schedule-presets {
  margin-bottom: 20px;
}

.presets-label,
.custom-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.presets-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preset-chip {
  padding: 6px 14px;
  font-size: 13px;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.15s ease;
  color: var(--text-secondary);
  background: var(--bg-primary);
  user-select: none;
}

.preset-chip:hover {
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
}

.preset-chip.active {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}

.schedule-custom {
  margin-bottom: 16px;
}

.schedule-preview {
  padding: 10px 14px;
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.schedule-preview strong {
  color: var(--el-color-primary);
  font-weight: 600;
}

.template-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.template-name {
  font-size: 14px;
  color: var(--text-primary);
}

.template-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.template-preview {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-top: 8px;
}

.preview-section {
  margin-bottom: 16px;
}

.preview-section:last-child {
  margin-bottom: 0;
}

.preview-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.preview-content {
  padding: 12px 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 13px;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'Fira Code', 'Consolas', monospace;
}
</style>
