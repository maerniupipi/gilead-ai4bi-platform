<template>
  <div class="template-list-page">
    <div class="page-header-row">
      <h2 class="page-title">评测模板</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>
        新建模板
      </el-button>
    </div>
    <p class="page-desc">管理评测对比的提示词模板。模板中的占位符（{question}、{expected}、{generated_sql}）由系统自动填充，用户可自定义提示词内容和判定规则。</p>

    <div class="template-table-wrap" v-loading="loading">
      <el-table :data="templates" stripe class="template-table">
        <el-table-column prop="name" label="模板名称" min-width="160">
          <template #default="{ row }">
            <span>{{ row.name }}</span>
            <el-tag v-if="row.is_system" type="warning" size="small" class="system-tag">系统</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="comparison_method" label="对比方式" width="120" align="center">
          <template #default="{ row }">
            <span class="method-tag">{{ getMethodLabel(row.comparison_method) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_default" label="默认" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <div class="op-actions">
              <button v-if="!row.is_system" type="button" class="op-btn op-btn--primary" @click.stop="openEdit(row)">编辑</button>
              <button v-if="!row.is_default" type="button" class="op-btn op-btn--success" @click.stop="handleSetDefault(row)">默认</button>
              <button type="button" class="op-btn op-btn--primary" @click.stop="handleClone(row)">克隆</button>
              <button v-if="!row.is_system" type="button" class="op-btn op-btn--delete" @click.stop="handleDelete(row)">删除</button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && templates.length === 0" class="empty-table">
        <div class="empty-icon-wrap">
          <el-icon><Document /></el-icon>
        </div>
        <p>暂无模板，点击「新建模板」创建</p>
      </div>
    </div>

    <!-- 编辑/创建对话框 - 分步表单 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑模板' : '新建模板'"
      width="720px"
      destroy-on-close
      class="template-dialog"
    >
      <el-steps :active="currentStep" finish-status="success" class="template-steps">
        <el-step title="基本信息" />
        <el-step title="提示词配置" />
        <el-step title="确认输出" />
      </el-steps>

      <div class="step-content">
        <!-- Step 1: 基本信息 -->
        <div v-show="currentStep === 0">
          <el-form :model="form" label-position="top" class="template-form">
            <div class="form-row">
              <el-form-item label="模板名称" required style="flex: 1">
                <el-input v-model="form.name" placeholder="如：SQL逻辑对比-严格模式" />
              </el-form-item>
              <el-form-item label="对比方式" style="width: 160px">
                <el-select v-model="form.comparison_method" style="width: 100%" disabled>
                  <el-option label="LLM 评判" value="llm_judge" />
                </el-select>
              </el-form-item>
            </div>
            <el-form-item label="描述">
              <el-input v-model="form.description" placeholder="模板用途说明（可选）" />
            </el-form-item>
          </el-form>
        </div>

        <!-- Step 2: 提示词配置 -->
        <div v-show="currentStep === 1">
          <el-form :model="form" label-position="top" class="template-form prompt-form">
            <el-form-item label="系统提示词" required class="prompt-field">
              <template #label>
                <span class="prompt-label">
                  <span class="prompt-label__icon">&#x25C9;</span>
                  系统提示词
                  <span class="prompt-label__hint">System Prompt</span>
                </span>
              </template>
              <el-input
                v-model="form.system_prompt"
                type="textarea"
                :rows="6"
                placeholder="定义 AI 的角色和基本行为，如：你是一个 SQL 逻辑对比专家..."
                class="prompt-textarea"
              />
              <div class="prompt-char-count">{{ form.system_prompt.length }} 字符</div>
            </el-form-item>
            <el-form-item label="用户提示词模板" required class="prompt-field">
              <template #label>
                <span class="prompt-label">
                  <span class="prompt-label__icon">&#x25CB;</span>
                  用户提示词模板
                  <span class="prompt-label__hint">User Prompt Template</span>
                </span>
              </template>
              <el-input
                v-model="form.user_prompt"
                type="textarea"
                :rows="10"
                placeholder="提示词正文。可用占位符：{question}、{expected}、{generated_sql}"
                class="prompt-textarea"
              />
              <div class="field-tip">
                <span class="field-tip__badge">可用占位符</span>
                <code>{`{question}`}</code> 问题
                <span class="field-tip__sep">|</span>
                <code>{`{expected}`}</code> 参考答案
                <span class="field-tip__sep">|</span>
                <code>{`{generated_sql}`}</code> 生成的 SQL
              </div>
              <div class="prompt-char-count">{{ form.user_prompt.length }} 字符</div>
            </el-form-item>
          </el-form>
        </div>

        <!-- Step 3: 确认输出 -->
        <div v-show="currentStep === 2">
          <div class="preview-section">
            <h4 class="preview-label">基本信息</h4>
            <div class="preview-item">
              <span class="preview-key">模板名称：</span>
              <span class="preview-value">{{ form.name || '-' }}</span>
            </div>
            <div class="preview-item">
              <span class="preview-key">对比方式：</span>
              <span class="preview-value">{{ getMethodLabel(form.comparison_method) }}</span>
            </div>
            <div class="preview-item">
              <span class="preview-key">描述：</span>
              <span class="preview-value">{{ form.description || '-' }}</span>
            </div>
          </div>

          <div class="preview-section">
            <h4 class="preview-label">系统提示词</h4>
            <div class="preview-text">{{ form.system_prompt || '-' }}</div>
          </div>

          <div class="preview-section">
            <h4 class="preview-label">用户提示词模板</h4>
            <div class="preview-text">{{ form.user_prompt || '-' }}</div>
          </div>

          <div class="preview-section">
            <h4 class="preview-label">输出格式（固定）</h4>
            <div class="output-format-preview">
              <pre>{{ outputFormatPreview }}</pre>
            </div>
            <div class="field-tip">输出格式由系统固定，AI 返回的 JSON 必须包含 result、score、reason 三个字段（reason 最多 50 字）</div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <div class="footer-left">
            <el-button v-if="currentStep > 0" @click="currentStep--" class="prev-btn">
              上一步
            </el-button>
          </div>
          <div class="footer-right">
            <el-button @click="dialogVisible = false">取消</el-button>
            <el-button
              v-if="currentStep < 2"
              type="primary"
              @click="handleNext"
              :disabled="!canNext"
              class="next-btn"
            >
              下一步
            </el-button>
            <el-button
              v-else
              type="primary"
              @click="handleSave"
              :loading="saving"
              class="next-btn"
            >
              {{ editingId ? '保存' : '创建' }}
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Document } from '@element-plus/icons-vue'
import { useSpaceContext } from '@/utils/spaceContext'
import * as evalApi from '@/api/eval'

const { currentSpace, onSpaceChange } = useSpaceContext()

const templates = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const currentStep = ref(0)

const form = reactive({
  name: '',
  description: '',
  system_prompt: '',
  user_prompt: '',
  comparison_method: 'llm_judge',
})

const outputFormatPreview = `{
  "result": "pass" | "fail" | "pending",
  "score": 0.0 ~ 1.0,
  "reason": "判定理由（50字内）"
}`

const DEFAULT_SYSTEM_PROMPT = `你是企业级 SQL 评测仲裁专家（Senior SQL Evaluation Arbiter）。
你的任务不是“看起来像”，而是严格判断“业务语义是否等价”。

评审原则（必须遵守）：
1) 语义优先：优先判断业务目标与统计口径，而非仅比较语法表面。
2) 保守裁决：证据不足时返回 pending，禁止猜测性 pass。
3) 误差敏感：任何会改变业务结论的差异（过滤、连接、时间边界、聚合口径、去重）都应判为 fail。
4) 可复核：结论必须可被他人复现理解，理由简洁但指向核心差异。
5) 输出合规：仅返回 JSON，不得输出解释性前后缀、Markdown 或代码块。`
const DEFAULT_USER_PROMPT = `## 评测输入
### 问题
{question}

### 参考答案（期望结果描述）
{expected}

### 实验室生成的 SQL
{generated_sql}

## 审查流程（按顺序执行）
1. 提取目标：识别参考答案的业务意图（对象、指标、时间范围、约束条件）。
2. 结构对齐：比较主表/子查询/连接键/连接类型，识别是否引入漏算或重复计数风险。
3. 条件核验：逐项核验 where/having/时间边界/状态枚举/null 处理。
4. 口径核验：核验聚合函数、group by 粒度、distinct 去重策略。
5. 结果影响评估：判断差异是否会改变最终业务结论。

## 裁决标准（严格执行）
- pass：与参考答案业务语义等价；即使写法不同，业务结论不变。
- fail：存在会影响业务结论的实质差异（任一项成立即可）。
- pending：参考答案信息不足、问题定义歧义或上下文缺失，无法确定。

## score 标尺（0~1）
- 0.90~1.00：高度确定等价（pass）
- 0.00~0.30：高度确定不等价（fail）
- 0.40~0.80：信息不足或部分一致（pending）

## 输出协议（必须严格遵守）
仅返回如下 JSON 对象，不得输出其它内容：
{
  "result": "pass" | "fail" | "pending",
  "score": 0.0 ~ 1.0,
  "reason": "一句话结论，最多50字"
}`

const canNext = computed(() => {
  if (currentStep.value === 0) {
    return form.name.trim()
  }
  if (currentStep.value === 1) {
    return form.system_prompt.trim() && form.user_prompt.trim()
  }
  return true
})

function getMethodLabel(method) {
  const map = { llm_judge: 'LLM 评判' }
  return map[method] || method
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

async function loadTemplates() {
  if (!currentSpace.value?.id) return
  loading.value = true
  try {
    const data = await evalApi.getComparisonTemplates(currentSpace.value.id, { limit: 100 })
    templates.value = data.items || []
  } catch (e) {
    ElMessage.error('加载模板失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  currentStep.value = 0
  form.name = ''
  form.description = ''
  form.system_prompt = DEFAULT_SYSTEM_PROMPT
  form.user_prompt = DEFAULT_USER_PROMPT
  form.comparison_method = 'llm_judge'
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  currentStep.value = 0
  form.name = row.name
  form.description = row.description || ''
  form.system_prompt = row.system_prompt
  form.user_prompt = row.user_prompt
  form.comparison_method = row.comparison_method
  dialogVisible.value = true
}

function handleNext() {
  if (!canNext.value) return
  currentStep.value++
}

async function handleSave() {
  if (!form.name.trim()) { ElMessage.warning('请输入模板名称'); return }
  if (!form.system_prompt.trim()) { ElMessage.warning('请输入系统提示词'); return }
  if (!form.user_prompt.trim()) { ElMessage.warning('请输入用户提示词'); return }
  saving.value = true
  try {
    if (editingId.value) {
      await evalApi.updateComparisonTemplate(currentSpace.value.id, editingId.value, { ...form })
      ElMessage.success('保存成功')
    } else {
      await evalApi.createComparisonTemplate(currentSpace.value.id, { ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadTemplates()
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  } finally {
    saving.value = false
  }
}

async function handleSetDefault(row) {
  try {
    // 先取消所有默认
    const defaults = templates.value.filter(t => t.is_default && t.id !== row.id)
    await Promise.all(
      defaults.map(t => evalApi.updateComparisonTemplate(currentSpace.value.id, t.id, { is_default: false }))
    )
    await evalApi.updateComparisonTemplate(currentSpace.value.id, row.id, { is_default: true })
    ElMessage.success('已设为默认')
    loadTemplates()
  } catch (e) {
    ElMessage.error('操作失败: ' + e.message)
  }
}

async function handleClone(row) {
  try {
    await evalApi.cloneComparisonTemplate(currentSpace.value.id, row.id)
    ElMessage.success('克隆成功')
    loadTemplates()
  } catch (e) {
    ElMessage.error('克隆失败: ' + e.message)
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除模板「${row.name}」吗？`, '提示', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    await evalApi.deleteComparisonTemplate(currentSpace.value.id, row.id)
    ElMessage.success('已删除')
    await loadTemplates()
    // 如果删除的是默认模板，自动把第一个设为默认
    if (row.is_default && templates.value.length > 0) {
      const first = templates.value[0]
      await evalApi.updateComparisonTemplate(currentSpace.value.id, first.id, { is_default: true })
      loadTemplates()
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + e.message)
  }
}

onMounted(() => {
  loadTemplates()
  onSpaceChange(() => loadTemplates())
})
</script>

<style scoped>
.template-list-page {
  padding: 32px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.page-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0 0 24px;
}

.template-table-wrap {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.template-table {
  width: 100%;
}

.system-tag {
  margin-left: 6px;
  vertical-align: middle;
}

.method-tag {
  display: inline-flex;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
  background: var(--accent)22;
  color: var(--accent);
}

.text-muted {
  font-size: 12px;
  color: var(--text-muted);
}

.op-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.op-btn {
  border: none;
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  transition:
    background-color 0.2s,
    color 0.2s,
    transform 0.15s;
}

.op-btn:active {
  transform: translateY(1px);
}

.op-btn--primary {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.op-btn--primary:hover {
  color: #fff;
  background: var(--el-color-primary);
}

.op-btn--success {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

.op-btn--success:hover {
  color: #fff;
  background: var(--el-color-success);
}

.op-btn--delete {
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.op-btn--delete:hover {
  color: #fff;
  background: var(--el-color-danger);
}

.empty-table {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px;
  color: var(--text-muted);
}

.empty-icon-wrap {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border-radius: 50%;
}

.empty-icon-wrap .el-icon { font-size: 28px; opacity: 0.5; }
.empty-table p { font-size: 14px; margin: 0; }

/* ── Steps ── */
.template-steps {
  margin-bottom: 28px;
}

.step-content {
  min-height: 200px;
  max-height: 55vh;
  overflow-y: auto;
  padding-right: 4px;
}

.template-form {
  padding: 0;
}

.form-row {
  display: flex;
  gap: 16px;
}

/* ── Prompt Form Fields (Step 2) ── */
.prompt-form :deep(.el-form-item__label) {
  margin-bottom: 6px;
}

.prompt-field {
  margin-bottom: 28px;
}

.prompt-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.prompt-label__icon {
  font-size: 10px;
  color: var(--accent);
  line-height: 1;
}

.prompt-label__hint {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-muted);
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

/* ── Prompt Textareas ── */
.prompt-textarea {
  --prompt-bg: var(--bg-primary);
  --prompt-border: var(--border);
  --prompt-accent: var(--accent);
  --prompt-text: var(--text-primary);
  --prompt-placeholder: var(--text-muted);
}

.prompt-textarea :deep(.el-textarea__inner) {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.75;
  background: var(--prompt-bg);
  border: 1px solid var(--prompt-border);
  border-left: 3px solid var(--prompt-accent);
  border-radius: 8px;
  padding: 14px 16px;
  color: var(--prompt-text);
  resize: none;
  transition:
    border-color 0.25s ease,
    box-shadow 0.25s ease,
    background 0.25s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  min-height: 120px;
  max-height: 22vh;
}

.prompt-textarea :deep(.el-textarea__inner):hover {
  border-color: var(--prompt-accent);
  background: var(--bg-secondary);
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.06);
}

.prompt-textarea :deep(.el-textarea__inner):focus {
  border-color: var(--prompt-accent);
  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--prompt-accent) 12%, transparent),
    0 2px 8px rgba(0, 0, 0, 0.06);
  background: var(--bg-primary);
}

.prompt-textarea :deep(.el-textarea__inner)::placeholder {
  color: var(--prompt-placeholder);
  opacity: 0.55;
  font-style: italic;
  font-family: inherit;
}

/* ── Character Count ── */
.prompt-char-count {
  font-size: 11px;
  color: var(--text-muted);
  text-align: right;
  margin-top: 4px;
  font-feature-settings: 'tnum';
  font-variant-numeric: tabular-nums;
}

/* ── Field Tip ── */
.field-tip {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.field-tip__badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  border-radius: 4px;
  background: var(--accent)15;
  color: var(--accent);
  margin-right: 2px;
}

.field-tip__sep {
  color: var(--border);
  font-size: 10px;
  margin: 0 2px;
}

.field-tip code {
  padding: 1px 5px;
  font-size: 11px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  color: var(--accent);
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}

/* ── Preview (Step 3) ── */
.preview-section {
  margin-bottom: 20px;
}

.preview-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.preview-item {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.preview-key {
  font-weight: 500;
  color: var(--text-muted);
}

.preview-text {
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  white-space: pre-wrap;
  line-height: 1.6;
  max-height: 16vh;
  overflow-y: auto;
}

.output-format-preview {
  width: 100%;
  padding: 14px 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 13px;
}

.output-format-preview pre {
  margin: 0;
  font-family: 'Fira Code', 'Consolas', monospace;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

/* ── Dialog Footer ── */
.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
  font-size: 13px;
}

.next-btn {
  font-size: 13px;
}
</style>
