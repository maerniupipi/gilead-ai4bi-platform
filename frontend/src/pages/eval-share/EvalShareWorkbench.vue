<template>
  <div class="eval-share-page">
    <!-- 顶部导航 -->
    <header class="share-header">
      <div class="header-brand">
        <span class="brand-icon">📊</span>
        <span class="brand-text">评测中心 · 分享</span>
      </div>
    </header>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-state">
      <el-icon class="loading-spin" :size="32"><Loading /></el-icon>
      <span>加载中...</span>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="error-state">
      <el-icon :size="48"><CircleCloseFilled /></el-icon>
      <h3>无法访问</h3>
      <p>{{ error }}</p>
    </div>

    <!-- 主内容 -->
    <div v-else-if="suite" class="share-content">
      <!-- 评测集信息卡片 -->
      <div class="suite-card">
        <div class="suite-info">
          <h2 class="suite-name">{{ suite.name }}</h2>
          <p v-if="suite.description" class="suite-desc">{{ suite.description }}</p>
          <div class="suite-meta">
            <span class="meta-badge version">{{ suite.version }}</span>
            <span class="meta-badge status" :class="suite.status">{{ getStatusLabel(suite.status) }}</span>
            <span class="meta-item">用例数: {{ suite.case_count || 0 }}</span>
            <span v-if="suite.last_pass_rate !== null && suite.last_pass_rate !== undefined" class="meta-item">
              通过率: {{ (suite.last_pass_rate * 100).toFixed(1) }}%
            </span>
          </div>
        </div>
      </div>

      <!-- 标签页 -->
      <div class="detail-tabs">
        <div class="tab-nav">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="tab-item"
            :class="{ 'is-active': activeTab === tab.key }"
            @click="activeTab = tab.key"
          >
            <span>{{ tab.label }}</span>
            <span v-if="tab.count !== undefined" class="tab-count">{{ tab.count }}</span>
          </button>
        </div>

        <div class="tab-content">
          <!-- 用例列表 -->
          <div v-if="activeTab === 'cases'" class="cases-panel" v-loading="loadingCases">
            <div class="cases-toolbar">
              <button class="tool-btn primary" @click="openAddCase">
                <Plus />
                新增用例
              </button>
            </div>
            <div v-if="cases.length === 0" class="empty-state">
              <p>暂无用例</p>
            </div>
            <div v-else class="cases-table-wrap">
              <table class="cases-table">
                <thead>
                  <tr>
                    <th style="width:60px">#</th>
                    <th>问题（输入）</th>
                    <th style="width:100px">类型</th>
                    <th style="width:80px">难度</th>
                    <th style="width:120px">分类</th>
                    <th style="width:180px">备注</th>
                    <th style="width:120px">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(c, idx) in cases" :key="c.id">
                    <td class="cell-id">{{ idx + 1 }}</td>
                    <td class="cell-prompt">{{ c.input_prompt }}</td>
                    <td class="cell-center"><span class="type-badge">{{ getTypeLabel(c.expected_output_type) }}</span></td>
                    <td class="cell-center"><span class="difficulty-badge" :class="c.difficulty">{{ getDifficultyLabel(c.difficulty) }}</span></td>
                    <td>{{ c.category || '-' }}</td>
                    <td>{{ c.remark || '-' }}</td>
                    <td class="cell-center">
                      <div class="op-actions">
                        <button class="op-btn op-btn--edit" @click="openEditCase(c)">编辑</button>
                        <button class="op-btn op-btn--delete" @click="handleDeleteCase(c)">删除</button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="caseTotal > casePageSize" class="pagination-wrap">
              <el-pagination
                v-model:current-page="casePage"
                :page-size="casePageSize"
                :total="caseTotal"
                layout="prev, pager, next"
                @current-change="loadCases"
              />
            </div>
          </div>

          <!-- 任务列表 -->
          <div v-if="activeTab === 'tasks'" class="tasks-panel" v-loading="loadingTasks">
            <div v-if="tasks.length === 0" class="empty-state">
              <p>暂无评测任务</p>
            </div>
            <div v-else class="tasks-grid">
              <div
                v-for="t in tasks"
                :key="t.id"
                class="task-card"
                :class="{ 'is-active': selectedTaskId === t.id }"
                @click="selectTask(t)"
              >
                <div class="task-header">
                  <span class="task-name">{{ t.name }}</span>
                  <span class="task-status" :class="'status-' + t.status">{{ getTaskStatusLabel(t.status) }}</span>
                </div>
                <div class="task-stats">
                  <div class="task-stat">
                    <span class="stat-label">用例</span>
                    <span class="stat-value">{{ t.total_cases }}</span>
                  </div>
                  <div class="task-stat">
                    <span class="stat-label">通过</span>
                    <span class="stat-value pass">{{ t.passed_cases }}</span>
                  </div>
                  <div class="task-stat">
                    <span class="stat-label">失败</span>
                    <span class="stat-value fail">{{ t.failed_cases }}</span>
                  </div>
                  <div class="task-stat">
                    <span class="stat-label">通过率</span>
                    <span class="stat-value" :class="getRateClass(t)">{{ getPassRate(t) }}%</span>
                  </div>
                </div>
                <div class="task-time">{{ formatDate(t.created_at) }}</div>
              </div>
            </div>
          </div>

          <!-- 任务详情（子任务 + 运行记录） -->
          <div v-if="activeTab === 'detail' && selectedTask" class="detail-panel">
            <!-- 任务统计 -->
            <div class="stats-grid" v-if="taskSummary">
              <div class="stat-card success">
                <div class="stat-value">{{ taskSummary.passed || 0 }}</div>
                <div class="stat-label">通过</div>
              </div>
              <div class="stat-card failed">
                <div class="stat-value">{{ taskSummary.failed || 0 }}</div>
                <div class="stat-label">失败</div>
              </div>
              <div class="stat-card total">
                <div class="stat-value">{{ taskSummary.total_cases || 0 }}</div>
                <div class="stat-label">总计</div>
              </div>
              <div class="stat-card rate">
                <div class="stat-value">{{ taskSummary.pass_rate || 0 }}%</div>
                <div class="stat-label">通过率</div>
              </div>
            </div>

            <!-- 子任务列表 -->
            <div class="section-title">子任务列表</div>
            <div v-loading="loadingSubtasks" class="subtasks-wrap">
              <div v-if="subtasks.length === 0" class="empty-state small">
                <p>暂无子任务</p>
              </div>
              <div v-else class="subtasks-grid">
                <div
                  v-for="item in subtasks"
                  :key="item.id"
                  class="subtask-card"
                  :class="{ 'is-passed': item.passed_cases > 0 && item.failed_cases === 0 && item.error_cases === 0, 'is-failed': item.failed_cases > 0 || item.error_cases > 0 }"
                  @click="viewRuns(item)"
                >
                  <div class="subtask-header">
                    <span class="subtask-id">#{{ item.id }}</span>
                    <span class="subtask-status" :class="'status-' + item.status">
                      {{ getTaskStatusLabel(item.status) }}
                    </span>
                  </div>
                  <div class="subtask-body">
                    <div class="subtask-case">
                      <span class="label">目标:</span>
                      <span class="value">{{ item.target_type || '-' }}</span>
                    </div>
                    <div class="subtask-score">
                      <span class="label">通过:</span>
                      <span class="value" :class="{ 'score-pass': item.passed_cases > 0 && item.failed_cases === 0, 'score-fail': item.failed_cases > 0 }">
                        {{ item.passed_cases || 0 }} / {{ item.total_cases || 0 }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 运行记录 -->
            <div v-if="selectedSubTask" class="runs-section">
              <div class="section-title">
                运行记录 · 子任务 #{{ selectedSubTask.id }}
                <button class="close-runs-btn" @click="selectedSubTask = null">关闭</button>
              </div>
              <div v-loading="loadingRuns" class="runs-wrap">
                <div v-if="runs.length === 0" class="empty-state small">
                  <p>暂无运行记录</p>
                </div>
                <div v-else class="runs-table-wrap">
                  <table class="runs-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>流程状态</th>
                        <th>对比结果</th>
                        <th>得分</th>
                        <th>原因分析</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in runs" :key="r.id">
                        <td>#{{ r.id }}</td>
                        <td>
                          <span class="result-tag" :class="r.status === 'success' ? 'pass' : 'fail'">
                            {{ r.status === 'success' ? '通过' : '异常' }}
                          </span>
                        </td>
                        <td>
                          <span class="result-tag" :class="r.comparison_result || 'pending'">
                            {{ r.comparison_result === 'pass' ? '通过' : r.comparison_result === 'fail' ? '失败' : '待定' }}
                          </span>
                        </td>
                        <td>
                          <span :class="{ 'score-pass': r.comparison_score >= 0.8, 'score-fail': r.comparison_score !== null && r.comparison_score < 0.8 }">
                            {{ r.comparison_score !== null && r.comparison_score !== undefined ? (r.comparison_score * 100).toFixed(0) + '%' : '-' }}
                          </span>
                        </td>
                        <td class="reason-cell">{{ r.comparison_reason || '-' }}</td>
                        <td>
                          <button class="action-btn" @click="viewComparison(r)">对比</button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <!-- 对比详情 -->
            <div v-if="comparisonData" class="comparison-section">
              <div class="section-title">
                对比详情 · 运行记录 #{{ comparisonData.run_id }}
                <button class="close-runs-btn" @click="comparisonData = null">关闭</button>
              </div>
              <div class="comparison-grid">
                <div class="comparison-block">
                  <div class="block-label">用例 ID</div>
                  <div class="block-content">#{{ comparisonData.case_id }}</div>
                </div>
                <div class="comparison-block">
                  <div class="block-label">执行耗时</div>
                  <div class="block-content">{{ comparisonData.execution_time_ms ? comparisonData.execution_time_ms + 'ms' : '-' }}</div>
                </div>
                <div class="comparison-block full">
                  <div class="block-label">原始响应</div>
                  <div class="block-content">{{ comparisonData.raw_response }}</div>
                </div>
                <div class="comparison-block full">
                  <div class="block-label">解析结果</div>
                  <div class="block-content">{{ comparisonData.parsed_response }}</div>
                </div>
                <div class="comparison-block full">
                  <div class="block-label">对比结果</div>
                  <div class="block-content">
                    <span class="result-tag" :class="comparisonData.result">
                      {{ comparisonData.result === 'pass' ? '通过' : comparisonData.result === 'fail' ? '失败' : '待定' }}
                    </span>
                    <span v-if="comparisonData.score !== null && comparisonData.score !== undefined" style="margin-left: 8px;">
                      得分: {{ (comparisonData.score * 100).toFixed(1) }}%
                    </span>
                    <span v-if="comparisonData.method" style="margin-left: 8px; color: #999;">
                      方法: {{ comparisonData.method }}
                    </span>
                  </div>
                </div>
                <div v-if="comparisonData.reason" class="comparison-block full">
                  <div class="block-label">原因分析</div>
                  <div class="block-content">{{ comparisonData.reason }}</div>
                </div>
                <div v-if="comparisonData.error_message" class="comparison-block full">
                  <div class="block-label">错误信息</div>
                  <div class="block-content" style="color: #f56c6c;">{{ comparisonData.error_message }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 用例编辑对话框 -->
    <el-dialog v-model="caseDialogVisible" :title="editingCase ? '编辑用例' : '新增用例'" width="90%" style="max-width:580px" destroy-on-close>
      <el-form :model="caseForm" label-position="top" class="case-form">
        <el-form-item label="问题（输入）" required>
          <el-input v-model="caseForm.input_prompt" type="textarea" :rows="3" placeholder="输入测试问题的提示词" />
        </el-form-item>
        <el-form-item label="期望答案">
          <el-input v-model="caseForm.expected_output" type="textarea" :rows="3" placeholder="输入期望的输出答案" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="输出类型" style="flex:1;">
            <el-select v-model="caseForm.expected_output_type" style="width: 100%;">
              <el-option label="文本" value="text" />
              <el-option label="SQL" value="sql" />
              <el-option label="JSON" value="json" />
              <el-option label="数值" value="number" />
              <el-option label="布尔" value="boolean" />
            </el-select>
          </el-form-item>
          <el-form-item label="难度" style="flex:1;">
            <el-select v-model="caseForm.difficulty" style="width: 100%;">
              <el-option label="简单" value="easy" />
              <el-option label="中等" value="medium" />
              <el-option label="困难" value="hard" />
            </el-select>
          </el-form-item>
          <el-form-item label="分类" style="flex:1;">
            <el-input v-model="caseForm.category" placeholder="分类名称" />
          </el-form-item>
          <el-form-item label="备注" style="flex:1;">
            <el-input v-model="caseForm.remark" placeholder="备注信息" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="caseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingCase" @click="handleSaveCase">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { Loading, CircleCloseFilled, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createEvalShareApi } from '@/api/evalShare'

const props = defineProps({
  token: { type: String, required: true },
})

const api = computed(() => createEvalShareApi(props.token))

// 状态
const loading = ref(true)
const error = ref('')
const suite = ref(null)

// 标签页
const activeTab = ref('cases')
const tabs = computed(() => {
  const t = [
    { key: 'cases', label: '用例列表', count: caseTotal.value },
    { key: 'tasks', label: '评测任务', count: tasks.value.length },
  ]
  if (selectedTask.value) {
    t.push({ key: 'detail', label: `任务详情 · ${selectedTask.value.name}` })
  }
  return t
})

// 用例
const cases = ref([])
const loadingCases = ref(false)
const caseTotal = ref(0)
const casePage = ref(1)
const casePageSize = ref(50)

// 用例编辑
const editingCase = ref(null)
const caseDialogVisible = ref(false)
const savingCase = ref(false)
const caseForm = reactive({
  input_prompt: '',
  expected_output: '',
  expected_output_type: 'text',
  difficulty: 'medium',
  category: '',
  remark: '',
})

// 任务
const tasks = ref([])
const loadingTasks = ref(false)
const selectedTaskId = ref(null)
const selectedTask = computed(() => tasks.value.find(t => t.id === selectedTaskId.value) || null)

// 子任务
const subtasks = ref([])
const loadingSubtasks = ref(false)
const taskSummary = ref(null)

// 运行记录
const selectedSubTask = ref(null)
const runs = ref([])
const loadingRuns = ref(false)

// 对比
const comparisonData = ref(null)

// 加载评测集
async function loadSuite() {
  loading.value = true
  error.value = ''
  try {
    suite.value = await api.value.getSuite()
  } catch (e) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// 加载用例
async function loadCases() {
  loadingCases.value = true
  try {
    const data = await api.value.listCases({
      skip: (casePage.value - 1) * casePageSize.value,
      limit: casePageSize.value,
    })
    cases.value = data.items || data || []
    caseTotal.value = data.total || 0
  } catch (e) {
    console.error('加载用例失败:', e)
  } finally {
    loadingCases.value = false
  }
}

// 新增用例
function openAddCase() {
  editingCase.value = null
  caseForm.input_prompt = ''
  caseForm.expected_output = ''
  caseForm.expected_output_type = 'text'
  caseForm.difficulty = 'medium'
  caseForm.category = ''
  caseDialogVisible.value = true
}

// 编辑用例
function openEditCase(row) {
  editingCase.value = row.id
  caseForm.input_prompt = row.input_prompt
  caseForm.expected_output = row.expected_output || ''
  caseForm.expected_output_type = row.expected_output_type || 'text'
  caseForm.difficulty = row.difficulty || 'medium'
  caseForm.category = row.category || ''
  caseForm.remark = row.remark || ''
  caseDialogVisible.value = true
}

async function handleSaveCase() {
  if (!caseForm.input_prompt.trim()) {
    ElMessage.warning('请输入问题内容')
    return
  }
  savingCase.value = true
  try {
    const data = {
      input_prompt: caseForm.input_prompt,
      expected_output: caseForm.expected_output,
      expected_output_type: caseForm.expected_output_type,
      difficulty: caseForm.difficulty,
      category: caseForm.category,
      remark: caseForm.remark,
    }
    if (editingCase.value) {
      await api.value.updateCase(editingCase.value, data)
    } else {
      await api.value.createCase(data)
    }
    ElMessage.success('保存成功')
    caseDialogVisible.value = false
    loadCases()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || e))
  } finally {
    savingCase.value = false
  }
}

async function handleDeleteCase(row) {
  try {
    await ElMessageBox.confirm('确定要删除该用例吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await api.value.deleteCase(row.id)
    ElMessage.success('删除成功')
    loadCases()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e?.response?.data?.detail || e?.message || e))
  }
}

// 加载任务
async function loadTasks() {
  loadingTasks.value = true
  try {
    const data = await api.value.listTasks({ limit: 200 })
    tasks.value = data.items || data || []
  } catch (e) {
    console.error('加载任务失败:', e)
  } finally {
    loadingTasks.value = false
  }
}

// 选择任务
async function selectTask(task) {
  selectedTaskId.value = task.id
  selectedSubTask.value = null
  runs.value = []
  comparisonData.value = null
  activeTab.value = 'detail'
  await loadTaskDetail(task.id)
}

// 加载任务详情
async function loadTaskDetail(taskId) {
  loadingSubtasks.value = true
  try {
    const [subs, summary] = await Promise.all([
      api.value.getTaskSubTasks(taskId),
      api.value.getTaskSummary(taskId),
    ])
    subtasks.value = subs.items || subs || []
    taskSummary.value = summary
  } catch (e) {
    console.error('加载任务详情失败:', e)
  } finally {
    loadingSubtasks.value = false
  }
}

// 查看运行记录
async function viewRuns(subTask) {
  selectedSubTask.value = subTask
  comparisonData.value = null
  loadingRuns.value = true
  try {
    const data = await api.value.listRuns(subTask.id, { limit: 100 })
    runs.value = data.items || data || []
  } catch (e) {
    console.error('加载运行记录失败:', e)
  } finally {
    loadingRuns.value = false
  }
}

// 查看对比
async function viewComparison(run) {
  try {
    const data = await api.value.getRun(run.id)
    const comp = data.comparison || {}
    comparisonData.value = {
      run_id: run.id,
      case_id: data.case_id,
      status: data.status,
      raw_response: data.raw_response || '-',
      parsed_response: data.parsed_response ? JSON.stringify(data.parsed_response, null, 2) : '-',
      error_message: data.error_message || '',
      execution_time_ms: data.execution_time_ms,
      result: comp.is_correct === true ? 'pass' : comp.is_correct === false ? 'fail' : 'pending',
      reason: comp.detail?.reason || run.comparison_reason || '',
      score: comp.score,
      method: comp.method || '',
    }
  } catch (e) {
    console.error('加载对比详情失败:', e)
  }
}

// 辅助函数
function getStatusLabel(s) {
  return { draft: '草稿', active: '已发布', archived: '已归档' }[s] || s || '--'
}

function getTaskStatusLabel(s) {
  return { completed: '已完成', running: '运行中', failed: '失败', cancelled: '已取消', draft: '草稿', pending: '等待中', paused: '已暂停', starting: '启动中' }[s] || s
}

function getTypeLabel(t) {
  return { text: '文本', sql: 'SQL', json: 'JSON', number: '数值', boolean: '布尔' }[t] || t || '--'
}

function getDifficultyLabel(d) {
  return { easy: '简单', medium: '中等', hard: '困难' }[d] || d || '--'
}

function getPassRate(t) {
  const total = t.total_cases || 0
  const passed = t.passed_cases || 0
  return total > 0 ? (passed / total * 100).toFixed(1) : '0.0'
}

function getRateClass(t) {
  const rate = t.total_cases > 0 ? t.passed_cases / t.total_cases : 0
  if (rate >= 0.8) return 'rate-good'
  if (rate >= 0.6) return 'rate-mid'
  return 'rate-bad'
}

function formatDate(d) {
  if (!d) return '--'
  return new Date(d).toLocaleString('zh-CN')
}

onMounted(() => {
  loadSuite()
  loadCases()
  loadTasks()
})
</script>

<style scoped>
.eval-share-page {
  min-height: 100vh;
  background: #f0f2f5;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* 顶部导航 */
.share-header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-icon {
  font-size: 20px;
}

.brand-text {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
}

/* 加载 / 错误 */
.loading-state, .error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: 12px;
  color: #666;
}

.loading-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.error-state h3 {
  margin: 0;
  color: #333;
}

.error-state p {
  margin: 0;
  color: #999;
  font-size: 14px;
}

/* 主内容 */
.share-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px 24px;
}

/* 评测集卡片 */
.suite-card {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

.suite-name {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #1a1a1a;
}

.suite-desc {
  margin: 0 0 12px;
  font-size: 14px;
  color: #666;
  line-height: 1.5;
}

.suite-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.meta-badge {
  display: inline-flex;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 10px;
}

.meta-badge.version {
  background: #e8f4fd;
  color: #1890ff;
}

.meta-badge.status.draft {
  background: #f5f5f5;
  color: #999;
}

.meta-badge.status.active {
  background: #e6f7e6;
  color: #52c41a;
}

.meta-badge.status.archived {
  background: #fff7e6;
  color: #faad14;
}

.meta-item {
  font-size: 13px;
  color: #666;
}

/* 标签页 */
.detail-tabs {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  overflow: hidden;
}

.tab-nav {
  display: flex;
  border-bottom: 1px solid #f0f0f0;
  padding: 0 16px;
}

.tab-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 16px;
  font-size: 14px;
  font-weight: 500;
  color: #666;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-item:hover {
  color: #1fb8cc;
}

.tab-item.is-active {
  color: #1fb8cc;
  border-bottom-color: #1fb8cc;
}

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  background: #f0f2f5;
  border-radius: 10px;
  color: #999;
}

.tab-content {
  padding: 20px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #999;
  font-size: 14px;
}

.empty-state.small {
  padding: 30px 20px;
}

/* 用例工具栏 */
.cases-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tool-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fff;
  color: #333;
  cursor: pointer;
  transition: all 0.2s;
}

.tool-btn:hover {
  border-color: #d0d0d0;
  background: #fafafa;
}

.tool-btn.primary {
  background: #1fb8cc;
  border-color: #1fb8cc;
  color: #fff;
}

.tool-btn.primary:hover {
  background: #3d5fd9;
  border-color: #3d5fd9;
}

/* 用例表格 */
.cases-table-wrap {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  overflow: hidden;
}

.cases-table {
  width: 100%;
  border-collapse: collapse;
}

.cases-table th {
  background: #fafafa;
  font-weight: 600;
  font-size: 13px;
  color: #666;
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid #f0f0f0;
}

.cases-table td {
  padding: 10px 12px;
  font-size: 13px;
  color: #333;
  border-bottom: 1px solid #f5f5f5;
}

.cases-table tr:last-child td {
  border-bottom: none;
}

.cell-id {
  color: #999;
  text-align: center;
}

.cell-prompt {
  max-width: 500px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cell-center {
  text-align: center;
}

.type-badge {
  display: inline-flex;
  padding: 1px 8px;
  font-size: 11px;
  background: #f5f5f5;
  color: #666;
  border-radius: 4px;
  border: 1px solid #e8e8e8;
}

.difficulty-badge {
  display: inline-flex;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 10px;
}

.difficulty-badge.easy {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.difficulty-badge.medium {
  background: rgba(230, 162, 60, 0.1);
  color: #e6a23c;
}

.difficulty-badge.hard {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

/* 任务卡片 */
.tasks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.task-card {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.task-card:hover {
  border-color: #1fb8cc;
  box-shadow: 0 2px 8px rgba(73, 114, 251, 0.1);
}

.task-card.is-active {
  border-color: #1fb8cc;
  background: #f0f4ff;
}

.task-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.task-name {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
}

.task-status {
  display: inline-flex;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
}

.task-status.status-completed {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.task-status.status-running {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.task-status.status-failed {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.task-status.status-draft, .task-status.status-pending {
  background: #f5f5f5;
  color: #999;
}

.task-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
}

.task-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-label {
  font-size: 11px;
  color: #999;
}

.stat-value {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.stat-value.pass {
  color: #67c23a;
}

.stat-value.fail {
  color: #f56c6c;
}

.stat-value.rate-good {
  color: #67c23a;
}

.stat-value.rate-mid {
  color: #e6a23c;
}

.stat-value.rate-bad {
  color: #f56c6c;
}

.task-time {
  font-size: 12px;
  color: #bbb;
}

/* 统计概览 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  background: #fafafa;
  border-radius: 10px;
  padding: 16px;
  text-align: center;
}

.stat-card .stat-value {
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 4px;
}

.stat-card .stat-label {
  font-size: 12px;
  color: #999;
}

.stat-card.success .stat-value {
  color: #67c23a;
}

.stat-card.failed .stat-value {
  color: #f56c6c;
}

.stat-card.total .stat-value {
  color: #333;
}

.stat-card.rate .stat-value {
  color: #1fb8cc;
}

/* 区块标题 */
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 20px 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.close-runs-btn {
  font-size: 12px;
  color: #999;
  background: none;
  border: 1px solid #e8e8e8;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  margin-left: auto;
}

.close-runs-btn:hover {
  color: #666;
  border-color: #d0d0d0;
}

/* 子任务 */
.subtasks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.subtask-card {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.subtask-card:hover {
  border-color: #1fb8cc;
}

.subtask-card.is-passed {
  border-left: 3px solid #67c23a;
}

.subtask-card.is-failed {
  border-left: 3px solid #f56c6c;
}

.subtask-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.subtask-id {
  font-size: 12px;
  font-weight: 600;
  color: #666;
}

.subtask-status {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
}

.subtask-status.status-completed {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.subtask-status.status-running {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.subtask-status.status-failed {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.subtask-body {
  display: flex;
  gap: 16px;
}

.subtask-case, .subtask-score {
  display: flex;
  gap: 4px;
  font-size: 12px;
}

.label {
  color: #999;
}

.value {
  color: #333;
  font-weight: 500;
}

.score-pass {
  color: #67c23a;
}

.score-fail {
  color: #f56c6c;
}

/* 运行记录表格 */
.runs-table-wrap {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  overflow: hidden;
}

.runs-table {
  width: 100%;
  border-collapse: collapse;
}

.runs-table th {
  background: #fafafa;
  font-weight: 600;
  font-size: 13px;
  color: #666;
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid #f0f0f0;
}

.runs-table td {
  padding: 10px 12px;
  font-size: 13px;
  color: #333;
  border-bottom: 1px solid #f5f5f5;
}

.runs-table tr:last-child td {
  border-bottom: none;
}

.result-tag {
  display: inline-flex;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 8px;
}

.result-tag.pass {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.result-tag.fail {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.result-tag.pending {
  background: #f5f5f5;
  color: #999;
}

.reason-cell {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-btn {
  font-size: 12px;
  color: #1fb8cc;
  background: none;
  border: 1px solid #1fb8cc;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
}

.action-btn:hover {
  background: #1fb8cc;
  color: #fff;
}

/* 对比详情 */
.comparison-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.comparison-block {
  background: #fafafa;
  border-radius: 8px;
  padding: 14px;
}

.comparison-block.full {
  grid-column: 1 / -1;
}

.block-label {
  font-size: 12px;
  font-weight: 600;
  color: #999;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.block-content {
  font-size: 13px;
  color: #333;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.block-content.expected {
  color: #1890ff;
}

.block-content.actual.is-pass {
  color: #67c23a;
}

.block-content.actual.is-fail {
  color: #f56c6c;
}

/* 操作按钮 */
.op-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.op-btn {
  border: none;
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  transition: background-color 0.2s, color 0.2s, transform 0.15s;
}

.op-btn:active {
  transform: translateY(1px);
}

.op-btn--edit {
  color: #1fb8cc;
  background: rgba(73, 114, 251, 0.08);
}

.op-btn--edit:hover {
  color: #fff;
  background: #1fb8cc;
}

.op-btn--delete {
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.08);
}

.op-btn--delete:hover {
  color: #fff;
  background: #f56c6c;
}

/* 用例表单 */
.case-form :deep(.el-form-item__label) {
  font-weight: 500;
  font-size: 13px;
}

.case-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.form-row {
  display: flex;
  gap: 8px;
}

.form-row :deep(.el-form-item__label) {
  font-size: 13px;
}

/* 响应式 */
@media (max-width: 768px) {
  .share-content {
    padding: 12px;
  }

  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .tasks-grid {
    grid-template-columns: 1fr;
  }

  .subtasks-grid {
    grid-template-columns: 1fr;
  }

  .comparison-grid {
    grid-template-columns: 1fr;
  }

  .form-row {
    flex-direction: column;
    gap: 0;
  }
}
</style>
