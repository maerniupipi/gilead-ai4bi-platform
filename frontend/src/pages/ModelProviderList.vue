<template>
  <div class="model-provider-container">
    <PageHeader
      :breadcrumbs="[{ label: '模型中心' }]"
    />

    <div class="provider-grid">
      <!-- 内置供应商卡片 -->
      <div
        v-for="provider in builtinProviders"
        :key="provider.id"
        class="provider-card"
        :class="{ active: provider.is_active, disabled: !provider.api_key }"
        @click="handleViewModels(provider)"
      >
        <div class="card-top">
          <div class="provider-identity">
            <div class="provider-avatar" :class="{ configured: provider.api_key }">
              {{ provider.name.charAt(0) }}
            </div>
            <div class="provider-meta">
              <div class="provider-name">{{ provider.name }}</div>
              <div class="provider-type">
                <span class="type-badge">内置</span>
                <span class="protocol-tag">{{ provider.protocol.toUpperCase() }}</span>
              </div>
            </div>
          </div>
          <div class="status-area" @click.stop>
            <el-switch
              v-model="provider.is_active"
              :disabled="!provider.api_key"
              size="small"
              @change="handleToggleActive(provider)"
            />
          </div>
        </div>

        <div class="card-divider" />

        <div class="card-middle">
          <div class="info-row">
            <span class="info-label">Base URL</span>
            <span class="info-value url">{{ provider.base_url }}</span>
          </div>

          <div class="models-block" v-if="parseModels(provider.models).length">
            <div class="models-label">模型</div>
            <div class="model-tags">
              <span
                v-for="model in parseModels(provider.models).slice(0, 4)"
                :key="model"
                class="model-tag"
              >{{ model }}</span>
              <span v-if="parseModels(provider.models).length > 4" class="model-tag more">
                +{{ parseModels(provider.models).length - 4 }}
              </span>
            </div>
          </div>
          <div class="models-block empty" v-else>
            <span class="no-models">暂无模型</span>
          </div>
        </div>

        <div class="card-divider" />

        <div class="card-bottom" @click.stop>
          <el-button size="small" class="btn-secondary" @click="handleConfigApiKey(provider)">
            {{ provider.api_key ? '修改 Key' : '配置 Key' }}
          </el-button>
          <el-button
            size="small"
            type="primary"
            class="btn-primary"
            :disabled="!provider.api_key || (!canConfigure && isObfuscated(provider.api_key))"
            @click="handleTest(provider)"
          >
            测试连接
          </el-button>
          <el-button
            size="small"
            class="btn-danger"
            :icon="Delete"
            @click="handleDelete(provider)"
          />
        </div>
      </div>

      <!-- 自定义供应商卡片 -->
      <div
        v-for="provider in customProviders"
        :key="provider.id"
        class="provider-card custom"
        :class="{ active: provider.is_active }"
        @click="handleViewModels(provider)"
      >
        <div class="card-top">
          <div class="provider-identity">
            <div class="provider-avatar custom-avatar">
              {{ provider.name.charAt(0) }}
            </div>
            <div class="provider-meta">
              <div class="provider-name">{{ provider.name }}</div>
              <div class="provider-type">
                <span class="type-badge custom-type">自定义</span>
                <span class="protocol-tag">{{ provider.protocol.toUpperCase() }}</span>
              </div>
            </div>
          </div>
          <div class="status-area" @click.stop>
            <el-switch
              v-model="provider.is_active"
              size="small"
              @change="handleToggleActive(provider)"
            />
          </div>
        </div>

        <div class="card-divider" />

        <div class="card-middle">
          <div class="info-row">
            <span class="info-label">Base URL</span>
            <span class="info-value url">{{ provider.base_url }}</span>
          </div>

          <div class="models-block" v-if="parseModels(provider.models).length">
            <div class="models-label">模型</div>
            <div class="model-tags">
              <span
                v-for="model in parseModels(provider.models).slice(0, 4)"
                :key="model"
                class="model-tag custom-tag"
              >{{ model }}</span>
              <span v-if="parseModels(provider.models).length > 4" class="model-tag more">
                +{{ parseModels(provider.models).length - 4 }}
              </span>
            </div>
          </div>
          <div class="models-block empty" v-else>
            <span class="no-models">暂无模型</span>
          </div>
        </div>

        <div class="card-divider" />

        <div class="card-bottom" @click.stop>
          <el-button size="small" class="btn-secondary" @click="handleEdit(provider)">
            编辑
          </el-button>
          <el-button
            size="small"
            type="primary"
            class="btn-primary"
            :disabled="!provider.api_key || (!canConfigure && isObfuscated(provider.api_key))"
            @click="handleTest(provider)"
          >
            测试连接
          </el-button>
          <el-button
            size="small"
            class="btn-danger"
            :icon="Delete"
            @click="handleDelete(provider)"
          />
        </div>
      </div>

      <!-- 添加按钮卡片（始终在最后） -->
      <div class="provider-card add-card" @click="handleAddCustom">
        <div class="add-inner">
          <div class="add-ring">
            <el-icon :size="28"><Plus /></el-icon>
          </div>
          <div class="add-label">添加供应商</div>
        </div>
      </div>
    </div>

    <!-- API Key 配置对话框 -->
    <el-dialog title="配置 API Key" v-model="apiKeyDialogVisible" width="500px">
      <el-form :model="apiKeyForm" label-width="100px">
        <el-form-item label="供应商">
          <el-input :value="currentProvider?.name" disabled />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="apiKeyForm.api_key"
            :type="canConfigure ? 'password' : 'text'"
            :show-password="canConfigure"
            :disabled="!canConfigure && !!apiKeyForm._hasExistingKey"
            placeholder="请输入API Key"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="apiKeyDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveApiKey">保存</el-button>
      </template>
    </el-dialog>

    <!-- 自定义供应商对话框 -->
    <el-dialog
      :title="customDialogTitle"
      v-model="customDialogVisible"
      width="600px"
      @close="resetCustomForm"
    >
      <el-form :model="customForm" :rules="customRules" ref="customFormRef" label-width="120px">
        <el-form-item label="供应商名称" prop="name">
          <el-input v-model="customForm.name" placeholder="如: DeepSeek" />
        </el-form-item>
        <el-form-item label="Base URL" prop="base_url">
          <el-input v-model="customForm.base_url" placeholder="https://api.example.com/v1" />
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input
            v-model="customForm.api_key"
            :type="canConfigure ? 'password' : 'text'"
            :show-password="canConfigure"
            :disabled="!canConfigure && !!customForm._hasExistingKey"
            placeholder="请输入API Key"
          />
        </el-form-item>
        <el-form-item label="协议类型" prop="protocol">
          <el-select v-model="customForm.protocol" placeholder="请选择协议">
            <el-option label="OpenAI" value="openai" />
            <el-option label="Anthropic" value="anthropic" />
            <el-option label="Google" value="google" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型列表" prop="models">
          <el-input
            v-model="customForm.models"
            type="textarea"
            :rows="4"
            placeholder="每行一个模型名称，如：&#10;deepseek-chat&#10;deepseek-coder"
          />
        </el-form-item>
        <el-form-item label="备注说明">
          <el-input v-model="customForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="customDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitCustom">确定</el-button>
      </template>
    </el-dialog>

    <!-- 模型列表对话框 -->
    <el-dialog
      :title="`${currentProvider?.name} — 模型管理`"
      v-model="modelsDialogVisible"
      width="min(1000px, 94vw)"
    >
      <div class="models-editor">
        <div class="models-add-row">
          <el-input
            v-model="newModelName"
            placeholder="输入模型名称，按回车添加"
            size="default"
            class="model-input"
            @keydown.enter="handleAddModelInline"
          >
            <template #prefix>
              <el-icon class="input-icon"><Plus /></el-icon>
            </template>
          </el-input>
        </div>

        <div class="models-section" v-if="modelsList.length">
          <div class="models-tag-grid">
            <TransitionGroup name="chip">
              <div
                v-for="(model, idx) in modelsList"
                :key="model.name"
                class="model-chip"
              >
                <span class="chip-index">{{ idx + 1 }}</span>
                <span class="chip-name">{{ model.name }}</span>
                <el-tag type="info">思考已关闭</el-tag>
                <el-select v-model="model.thinking.parameter" aria-label="关闭思考的参数协议" style="width: 180px">
                  <el-option label="Qwen / vLLM 开关" value="enable_thinking" />
                  <el-option label="reasoning_effort 强度" value="reasoning_effort" />

                </el-select>
                <span>{{ model.thinking.parameter === 'reasoning_effort' ? 'reasoning_effort = none' : 'enable_thinking = false' }}</span>
                <button class="chip-remove" @click="handleRemoveModel(idx)" :title="`移除 ${model.name}`">
                  <el-icon :size="12"><Delete /></el-icon>
                </button>
              </div>
            </TransitionGroup>
          </div>
          <div class="models-count">
            共 <strong>{{ modelsList.length }}</strong> 个模型
            <p>按模型接口支持的参数选择。Qwen / vLLM 开关控制启停，强度或 Token 预算需服务端支持。保存后对使用此模型的调用生效。</p>
          </div>
        </div>

        <div class="models-empty" v-else>
          <div class="empty-icon">
            <el-icon :size="36"><FolderOpened /></el-icon>
          </div>
          <div class="empty-text">暂无模型</div>
          <div class="empty-hint">在上方输入模型名称，按 Enter 添加</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="modelsDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveModels">保存</el-button>
      </template>
    </el-dialog>

    <!-- 测试对话框 -->
    <el-dialog title="测试模型连接" v-model="testDialogVisible" width="500px">
      <el-form :model="testForm" label-width="100px">
        <el-form-item label="选择模型">
          <el-select v-model="testForm.model" placeholder="请选择要测试的模型">
            <el-option
              v-for="model in parseModels(currentProvider?.models)"
              :key="model"
              :label="model"
              :value="model"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="testDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="executeTest" :loading="testing">开始测试</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, FolderOpened } from '@element-plus/icons-vue'
import {
  getModelProviders,
  createModelProvider,
  updateModelProvider,
  deleteModelProvider,
  testModel
} from '../api/modelProvider'
import { isAuthenticated } from '../utils/auth'

const canConfigure = computed(() => isAuthenticated())

/* ---- API Key 前端混淆（防止 F12 明文泄露，非加密） ---- */
const OBF_PREFIX = 'OBF:'
const OBF_KEY = 'AzBI-2024-Secure'

function obfuscate (plain) {
  if (!plain || typeof plain !== 'string') return ''
  let bin = ''
  for (let i = 0; i < plain.length; i++) {
    bin += String.fromCharCode(plain.charCodeAt(i) ^ OBF_KEY.charCodeAt(i % OBF_KEY.length))
  }
  return OBF_PREFIX + btoa(bin)
}

function deobfuscate (obf) {
  if (!obf || typeof obf !== 'string' || !obf.startsWith(OBF_PREFIX)) return obf || ''
  const bin = atob(obf.slice(OBF_PREFIX.length))
  let out = ''
  for (let i = 0; i < bin.length; i++) {
    out += String.fromCharCode(bin.charCodeAt(i) ^ OBF_KEY.charCodeAt(i % OBF_KEY.length))
  }
  return out
}

function isObfuscated (val) {
  return typeof val === 'string' && val.startsWith(OBF_PREFIX)
}

const providers = ref([])

const builtinProviders = computed(() => providers.value.filter(p => p.is_builtin))
const customProviders = computed(() => providers.value.filter(p => !p.is_builtin))
const apiKeyDialogVisible = ref(false)
const customDialogVisible = ref(false)
const testDialogVisible = ref(false)
const modelsDialogVisible = ref(false)
const customDialogTitle = ref('添加自定义供应商')
const customFormRef = ref(null)
const testing = ref(false)
const currentProvider = ref(null)
const modelsList = ref([])
const newModelName = ref('')

const apiKeyForm = reactive({
  api_key: ''
})

const customForm = reactive({
  name: '',
  base_url: '',
  api_key: '',
  protocol: 'openai',
  models: '',
  description: ''
})

const testForm = reactive({
  model: ''
})

const customRules = {
  name: [{ required: true, message: '请输入供应商名称', trigger: 'blur' }],
  base_url: [{ required: true, message: '请输入Base URL', trigger: 'blur' }],
  protocol: [{ required: true, message: '请选择协议类型', trigger: 'change' }],
  models: [{ required: true, message: '请输入模型列表', trigger: 'blur' }]
}

const parseModels = (modelsStr) => {
  if (!modelsStr) return []
  try {
    return JSON.parse(modelsStr)
  } catch {
    return []
  }
}

const loadProviders = async () => {
  try {
    const data = await getModelProviders()
    // 将 api_key 混淆后存入内存，防止 F12 明文泄露
    providers.value = data.map(p => ({
      ...p,
      api_key: p.api_key ? obfuscate(p.api_key) : p.api_key
    }))
  } catch (error) {
    ElMessage.error('加载失败: ' + (error.message || ''))
  }
}

const handleConfigApiKey = (provider) => {
  currentProvider.value = provider
  if (canConfigure.value && provider.api_key) {
    apiKeyForm.api_key = deobfuscate(provider.api_key)
    apiKeyForm._hasExistingKey = true
  } else if (provider.api_key) {
    apiKeyForm.api_key = '••••••••••••••••'
    apiKeyForm._hasExistingKey = true
  } else {
    apiKeyForm.api_key = ''
    apiKeyForm._hasExistingKey = false
  }
  apiKeyDialogVisible.value = true
}

const handleSaveApiKey = async () => {
  try {
    const payload = {}
    if (canConfigure.value) {
      // 超级管理员：发送解密后的明文（新输入或未修改的原始值）
      payload.api_key = apiKeyForm.api_key
    } else {
      // 非超级管理员：如果没有修改（还是掩码），发送原有的混淆值保持不变
      if (apiKeyForm._hasExistingKey && apiKeyForm.api_key === '••••••••••••••••') {
        payload.api_key = deobfuscate(currentProvider.value.api_key)
      } else {
        payload.api_key = apiKeyForm.api_key
      }
    }
    await updateModelProvider(currentProvider.value.id, payload)
    ElMessage.success('保存成功')
    apiKeyDialogVisible.value = false
    loadProviders()
  } catch (error) {
    ElMessage.error('保存失败: ' + (error.message || ''))
  }
}

const handleToggleActive = async (provider) => {
  try {
    await updateModelProvider(provider.id, {
      is_active: provider.is_active
    })
    ElMessage.success(provider.is_active ? '已启用' : '已禁用')
  } catch (error) {
    ElMessage.error('操作失败: ' + (error.message || ''))
    provider.is_active = !provider.is_active
  }
}

const handleAddCustom = () => {
  customDialogTitle.value = '添加自定义供应商'
  customForm.id = null
  customDialogVisible.value = true
}

const handleEdit = (provider) => {
  customDialogTitle.value = '编辑供应商'
  customForm.id = provider.id
  customForm.name = provider.name
  customForm.base_url = provider.base_url
  if (canConfigure.value && provider.api_key) {
    customForm.api_key = deobfuscate(provider.api_key)
    customForm._hasExistingKey = true
  } else if (provider.api_key) {
    customForm.api_key = '••••••••••••••••'
    customForm._hasExistingKey = true
  } else {
    customForm.api_key = ''
    customForm._hasExistingKey = false
  }
  customForm.protocol = provider.protocol
  customForm.models = parseModels(provider.models).join('\n')
  customForm.description = provider.description || ''
  customDialogVisible.value = true
}

const handleDelete = async (provider) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除供应商「${provider.name}」吗？`,
      '删除确认',
      { type: 'warning' }
    )
    await deleteModelProvider(provider.id)
    ElMessage.success('删除成功')
    loadProviders()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + (error.message || ''))
    }
  }
}

const handleViewModels = (provider) => {
  currentProvider.value = provider
  modelsList.value = parseModels(provider.models).map(name => ({
    name,
    thinking: { ...defaultThinking(), ...(provider.model_settings?.[name] || {}), enabled: false,
      parameter: provider.model_settings?.[name]?.parameter === 'thinking_budget' ? 'enable_thinking' : provider.model_settings?.[name]?.parameter || 'reasoning_effort' }
  }))
  newModelName.value = ''
  modelsDialogVisible.value = true
}

const defaultThinking = () => ({ enabled: false, parameter: 'reasoning_effort', effort: 'medium', budget: 4096 })

const handleAddModelInline = () => {
  const name = newModelName.value.trim()
  if (!name) {
    ElMessage.warning('请输入模型名称')
    return
  }

  if (modelsList.value.some(m => m.name === name)) {
    ElMessage.warning('该模型已存在')
    return
  }

  modelsList.value.push({ name, thinking: defaultThinking() })
  newModelName.value = ''
}

const handleRemoveModel = (index) => {
  modelsList.value.splice(index, 1)
}

const handleSaveModels = async () => {
  if (modelsList.value.length === 0) {
    ElMessage.warning('至少需要保留一个模型')
    return
  }

  try {
    const modelsArray = modelsList.value.map(m => m.name)
    await updateModelProvider(currentProvider.value.id, {
      models: JSON.stringify(modelsArray),
      model_settings: Object.fromEntries(modelsList.value.map(m => [m.name, { ...m.thinking, enabled: false }]))
    })
    ElMessage.success('保存成功')
    modelsDialogVisible.value = false
    loadProviders()
  } catch (error) {
    ElMessage.error('保存失败: ' + (error.message || ''))
  }
}

const handleTest = (provider) => {
  currentProvider.value = provider
  testForm.model = parseModels(provider.models)[0] || ''
  testDialogVisible.value = true
}

const executeTest = async () => {
  if (!testForm.model) {
    ElMessage.warning('请选择要测试的模型')
    return
  }

  testing.value = true
  try {
    // 发送解密后的明文 key 给后端
    const plainKey = isObfuscated(currentProvider.value.api_key)
      ? deobfuscate(currentProvider.value.api_key)
      : currentProvider.value.api_key

    const result = await testModel({
      base_url: currentProvider.value.base_url,
      api_key: plainKey,
      protocol: currentProvider.value.protocol,
      model: testForm.model,
      model_settings: currentProvider.value.model_settings
    })

    if (result.success) {
      ElMessage.success('测试成功！模型连接正常')
    } else {
      ElMessage.error(`测试失败: ${result.message}`)
    }
  } catch (error) {
    ElMessage.error('测试请求失败: ' + (error.message || ''))
  } finally {
    testing.value = false
  }
}

const handleSubmitCustom = async () => {
  try {
    await customFormRef.value.validate()

    const modelsArray = customForm.models.split('\n').map(m => m.trim()).filter(m => m)
    let apiKeyValue = null
    if (canConfigure.value) {
      apiKeyValue = customForm.api_key || null
    } else if (customForm._hasExistingKey && customForm.api_key === '••••••••••••••••') {
      // 未修改，发送解密后的原始值
      apiKeyValue = deobfuscate(currentProvider.value?.api_key) || null
    } else if (customForm.api_key) {
      apiKeyValue = customForm.api_key
    }

    const data = {
      name: customForm.name,
      base_url: customForm.base_url,
      api_key: apiKeyValue,
      protocol: customForm.protocol,
      models: JSON.stringify(modelsArray),
      description: customForm.description,
      is_active: true
    }

    if (customForm.id) {
      await updateModelProvider(customForm.id, data)
      ElMessage.success('更新成功')
    } else {
      await createModelProvider(data)
      ElMessage.success('创建成功')
    }

    customDialogVisible.value = false
    loadProviders()
  } catch (error) {
    if (error !== false) {
      ElMessage.error('操作失败: ' + (error.message || ''))
    }
  }
}

const resetCustomForm = () => {
  customForm.id = null
  customForm.name = ''
  customForm.base_url = ''
  customForm.api_key = ''
  customForm._hasExistingKey = false
  customForm.protocol = 'openai'
  customForm.models = ''
  customForm.description = ''
  customFormRef.value?.clearValidate()
}

onMounted(() => {
  loadProviders()
})
</script>

<style scoped>

/* ============================================================
   Grid
   ============================================================ */
.provider-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}

/* ============================================================
   Card Base
   ============================================================ */
.provider-card {
  background: #fff;
  border: 1px solid #e8eaef;
  border-radius: 12px;
  padding: 0;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  cursor: pointer;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.provider-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
  border-color: #d4d7de;
}

.provider-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 16px rgba(230, 162, 60, 0.08);
}

.provider-card.active:hover {
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08), 0 2px 16px rgba(230, 162, 60, 0.08);
}

.provider-card.disabled {
  opacity: 0.55;
}

/* ============================================================
   Card Top
   ============================================================ */
.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 20px 20px 0 20px;
}

.provider-identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.provider-avatar {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: #f0f2f5;
  color: #909399;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 700;
  flex-shrink: 0;
  transition: background 0.2s ease, color 0.2s ease;
}

.provider-avatar.configured {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.custom-avatar {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}

.provider-meta {
  min-width: 0;
}

.provider-name {
  font-size: 16px;
  font-weight: 600;
  color: #1a1d23;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.provider-type {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}

.type-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: #f0f2f5;
  color: #909399;
  letter-spacing: 0.02em;
}

.type-badge.custom-type {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}

.protocol-tag {
  font-size: 11px;
  color: #9ca3af;
  font-weight: 500;
  letter-spacing: 0.04em;
}

.status-area {
  flex-shrink: 0;
  margin-top: 2px;
}

/* ============================================================
   Card Divider
   ============================================================ */
.card-divider {
  height: 1px;
  background: #f0f2f5;
  margin: 16px 20px 0 20px;
}

/* ============================================================
   Card Middle
   ============================================================ */
.card-middle {
  padding: 16px 20px 0 20px;
  flex: 1;
}

.info-row {
  display: flex;
  align-items: baseline;
  margin-bottom: 6px;
  font-size: 13px;
}

.info-label {
  color: #9ca3af;
  flex-shrink: 0;
  width: 64px;
  font-weight: 500;
}

.info-value {
  color: #5c6370;
  min-width: 0;
}

.info-value.url {
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 12px;
  word-break: break-all;
  color: #6b7280;
  line-height: 1.5;
}

.models-block {
  margin-top: 14px;
}

.models-label {
  font-size: 12px;
  font-weight: 600;
  color: #9ca3af;
  margin-bottom: 8px;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.model-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.model-tag {
  font-size: 12px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 6px;
  background: #f5f6f8;
  color: #5c6370;
  letter-spacing: 0.01em;
}

.model-tag.custom-tag {
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
}

.model-tag.more {
  background: #f0f2f5;
  color: #9ca3af;
  font-weight: 600;
}

.models-block.empty {
  margin-top: 14px;
}

.no-models {
  font-size: 12px;
  color: #d1d5db;
  font-style: italic;
}

/* ============================================================
   Card Bottom
   ============================================================ */
.card-bottom {
  display: flex;
  gap: 8px;
  padding: 14px 20px 18px 20px;
  align-items: center;
}

.card-bottom .btn-secondary {
  flex: 1;
  border: 1px solid #e4e7ed;
  color: #5c6370;
  background: #fff;
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.15s ease;
}

.card-bottom .btn-secondary:hover {
  border-color: #d1d5db;
  color: #1a1d23;
}

.card-bottom .btn-primary {
  flex: 1;
  border-radius: 8px;
  font-weight: 500;
}

.card-bottom .btn-danger {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid transparent;
  color: #9ca3af;
  background: transparent;
  border-radius: 8px;
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.card-bottom .btn-danger:hover {
  color: #f56c6c;
  background: #fef0f0;
  border-color: #fde2e2;
}

/* ============================================================
   Add Card
   ============================================================ */
.add-card {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 280px;
  border-style: dashed;
  border-color: #d4d7de;
  background: #fafbfc;
}

.add-card:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: none;
}

.add-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.add-ring {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 2px dashed #d1d5db;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  transition: all 0.2s ease;
}

.add-card:hover .add-ring {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  background: #fff;
  border-style: solid;
  box-shadow: 0 4px 16px rgba(230, 162, 60, 0.15);
}

.add-label {
  font-size: 14px;
  font-weight: 500;
  color: #9ca3af;
  transition: color 0.2s ease;
}

.add-card:hover .add-label {
  color: var(--el-color-primary);
}

/* ============================================================
   Models Editor Dialog
   ============================================================ */
.models-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.models-add-row {
  display: flex;
  gap: 8px;
}

.model-input :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e4e7ed inset;
}

.model-input :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #c0c4cc inset;
}

.input-icon {
  color: #909399;
}

.models-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.models-tag-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.model-chip {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  align-items: center;
  gap: 8px;
  padding: 6px 8px 6px 6px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  font-size: 13px;
  color: #303133;
  font-weight: 500;
  transition: all 0.15s ease;
  cursor: default;
}

.model-chip:hover {
  border-color: #c0c4cc;
  background: #fafbfc;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.chip-index {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 700;
  color: #909399;
  flex-shrink: 0;
}

.chip-name {
  line-height: 1;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  background: transparent;
  color: #c0c4cc;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.12s ease;
  flex-shrink: 0;
}

.chip-remove:hover {
  color: #f56c6c;
  background: #fef0f0;
}

/* chip transition */
.chip-enter-active,
.chip-leave-active {
  transition: all 0.25s ease;
}

.chip-enter-from {
  opacity: 0;
  transform: scale(0.85);
}

.chip-leave-to {
  opacity: 0;
  transform: scale(0.85) translateY(-4px);
}

/* ============================================================
   Models Empty State
   ============================================================ */
.models-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 20px;
  gap: 8px;
  background: #fafbfc;
  border: 1px dashed #e4e7ed;
  border-radius: 10px;
}

.empty-icon {
  color: #dcdfe6;
}

.empty-text {
  font-size: 14px;
  font-weight: 500;
  color: #909399;
}

.empty-hint {
  font-size: 12px;
  color: #c0c4cc;
}

/* ============================================================
   Models Count
   ============================================================ */
.models-count {
  text-align: right;
  font-size: 12px;
  color: #909399;
  padding-top: 4px;
  border-top: 1px solid #f0f2f5;
}

.models-count strong {
  color: #303133;
  font-weight: 600;
}
</style>
