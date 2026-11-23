<template>
  <div class="task-detail-page">
    <!-- 面包屑导航 -->
    <PageHeader :breadcrumbs="breadcrumbs">
      <template #actions>
        <button class="back-btn" @click="handleBack">
          <ArrowLeft />
          <span>返回</span>
        </button>
      </template>
    </PageHeader>

    <!-- 汇总卡片 -->
    <div class="summary-card" v-if="task">
      <div class="summary-row">
        <div class="summary-left">
          <span class="top-task-name">{{ task.name }}</span>
          <span class="meta-tag" :class="'status-' + task.status">
            <span class="status-dot"></span>
            {{ getStatusLabel(task.status) }}
          </span>
          <span class="top-meta">{{ task.suite_name }}</span>
        </div>
        <div class="summary-stats" v-if="summary">
          <div class="stat-item">
            <CheckCircle2 :size="14" />
            <span class="stat-num success">{{ manualAdjustedStats.passed }}</span>
            <span class="stat-lbl">通过</span>
          </div>
          <div class="stat-item">
            <XCircle :size="14" />
            <span class="stat-num danger">{{ manualAdjustedStats.failed }}</span>
            <span class="stat-lbl">失败</span>
          </div>
          <div class="stat-item">
            <ListChecks :size="14" />
            <span class="stat-num">{{ summary.total || 0 }}</span>
            <span class="stat-lbl">总计</span>
          </div>
          <div class="stat-item">
            <Percent :size="14" />
            <span class="stat-num" :class="getRateClass">{{ adjustedPassRate }}%</span>
            <span class="stat-lbl">通过率</span>
          </div>
        </div>
        <div class="header-actions">
          <button v-if="task.status === 'running'" class="btn-sm btn-danger" @click="handleCancelTask">
            <CloseBold /> 取消
          </button>
          <button v-if="task.status === 'failed'" class="btn-sm btn-outline" @click="handleRetryFailed">
            <Refresh /> 重试
          </button>
          <button v-if="task.status === 'cancelled'" class="btn-sm btn-outline" @click="handleRestartTask">
            <VideoPlay /> 重跑
          </button>
          <button class="btn-sm btn-outline" :disabled="!canExport" :title="canExport ? '导出结果' : '全部执行完成后才可导出'" @click="handleExport">
            <Download /> 导出
          </button>
          <button class="btn-sm btn-outline" :disabled="!canExport" title="将失败用例归档为新评测集" @click="handleArchiveFailed">
            <Archive /> 失败归档
          </button>
        </div>
      </div>
      <!-- 实时进度条 -->
      <div class="progress-inline" v-if="task.status === 'running'">
        <div class="progress-bar">
          <div class="progress-fill running" :style="{ width: (task.progress || 0) + '%' }"></div>
        </div>
        <span class="progress-text">{{ task.progress || 0 }}%</span>
        <span v-if="task.phase" class="phase-tag" :class="task.phase">
          {{ task.phase === 'target' ? '执行任务中' : '评测中' }}
        </span>
      </div>
    </div>

    <!-- 结果表格 -->
    <div class="result-table-section">
      <div class="table-toolbar">
        <span class="table-title">
          <List :size="16" />
          评测结果明细
        </span>
        <div class="toolbar-right">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索问题或答案..."
            style="width: 220px;"
            clearable
            class="search-input"
          >
            <template #prefix><Search /></template>
          </el-input>
          <el-select v-model="filterResult" placeholder="评判结果" clearable style="width: 120px;">
            <el-option label="通过" value="pass" />
            <el-option label="失败" value="fail" />
            <el-option label="待定" value="pending" />
          </el-select>
          <el-select v-model="filterStatus" placeholder="执行状态" clearable style="width: 120px;">
            <el-option label="已执行" value="completed" />
            <el-option label="执行中" value="running" />
            <el-option label="待执行" value="pending" />
          </el-select>
          <el-select v-model="filterDifficulty" placeholder="难度" clearable style="width: 110px;">
            <el-option v-for="item in difficultyOptions" :key="item" :label="item" :value="item" />
          </el-select>
          <el-select v-model="filterCategory" placeholder="分类" clearable filterable style="width: 120px;">
            <el-option v-for="item in categoryOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </div>
      </div>

      <div class="cases-table-wrap">
        <el-table
          v-loading="loadingTable"
          :data="paginatedRows"
          stripe
          class="result-table"
          row-key="id"
          :row-class-name="getResultRowClassName"
          style="width: 100%; table-layout: fixed;"
        >
          <el-table-column prop="difficulty" label="难度" width="90">
            <template #default="{ row }">
              <span class="difficulty-badge" :class="row.difficulty || 'unknown'">
                {{ getDifficultyLabel(row.difficulty) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="category" label="分类" width="110">
            <template #default="{ row }">
              <span class="cell-single">{{ row.category || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="case_input" label="问题（输入）" min-width="200">
            <template #default="{ row }">
              <el-tooltip v-if="row.case_input" :content="row.case_input" placement="top" :show-after="300">
                <span class="cell-multi">{{ row.case_input }}</span>
              </el-tooltip>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="expected_output" label="期望答案" min-width="160">
            <template #default="{ row }">
              <el-tooltip v-if="row.expected_output && row.expected_output !== '-'" :content="row.expected_output" placement="top" :show-after="300">
                <span class="cell-multi">{{ row.expected_output }}</span>
              </el-tooltip>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="actual_output" label="实际答案" min-width="160">
            <template #default="{ row }">
              <el-tooltip v-if="row.actual_output && row.actual_output !== '-'" :content="row.actual_output" placement="top" :show-after="300">
                <span class="cell-multi">{{ row.actual_output }}</span>
              </el-tooltip>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="comparison_result" label="评判结果" width="90" align="center">
            <template #default="{ row }">
              <span
                class="result-tag"
                :class="{
                  pass: row.comparison_result === 'pass',
                  fail: row.comparison_result === 'fail',
                  pending: row.comparison_result === 'pending'
                }"
              >
                {{ row.comparison_result === 'pass' ? '通过' : row.comparison_result === 'fail' ? '失败' : '待定' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="comparison_reason" label="评判小结" min-width="200">
            <template #default="{ row }">
              <el-tooltip
                v-if="row.comparison_reason && row.comparison_reason !== '-'"
                :content="row.comparison_reason"
                placement="top"
                :show-after="300"
              >
                <span class="cell-multi">{{ row.comparison_reason }}</span>
              </el-tooltip>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="160">
            <template #default="{ row }">
              <el-tooltip v-if="row.remark" :content="row.remark" placement="top" :show-after="300">
                <span class="cell-multi">{{ row.remark }}</span>
              </el-tooltip>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="manual_note" label="修改人备注" min-width="160">
            <template #default="{ row }">
              <el-tooltip v-if="row.manual_note" :content="row.manual_note" placement="top" :show-after="300">
                <span class="cell-multi">{{ row.manual_note }}</span>
              </el-tooltip>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="人工校验" width="72" align="center" fixed="right">
            <template #default="{ row }">
              <button
                v-if="row.status === 'completed'"
                class="icon-state-btn"
                :class="getManualVerified(row) ? 'ok' : 'bad'"
                :title="getManualVerified(row) ? '人工校验：正确' : '人工校验：错误'"
                @click="handleManualVerifyChange(row, !getManualVerified(row))"
              >
                <CheckCircle2 v-if="getManualVerified(row)" />
                <XCircle v-else />
              </button>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="修复状态" width="72" align="center" fixed="right">
            <template #default="{ row }">
              <button
                v-if="row.comparison_result === 'fail'"
                class="icon-state-btn"
                :class="fixedStatus[row.run_id] ? 'fixed' : 'muted'"
                :title="fixedStatus[row.run_id] ? '已修复' : '未修复'"
                @click="handleFixStatusChange(row, !fixedStatus[row.run_id])"
              >
                <CheckCircle2 v-if="fixedStatus[row.run_id]" />
                <Refresh v-else />
              </button>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="64" align="center" fixed="right">
            <template #default="{ row }">
              <span class="status-icon" :class="'st-' + row.status" :title="getExecStatusLabel(row)">
                <CheckCircle2 v-if="row.status === 'completed'" />
                <Refresh v-else-if="row.status === 'running'" />
                <XCircle v-else-if="row.status === 'failed'" />
                <ListChecks v-else />
              </span>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="!loadingTable && filteredRows.length === 0" class="empty-table">
          <div class="empty-icon-wrap">
            <List />
          </div>
          <p>暂无评测结果</p>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination-wrap" v-if="filteredRows.length > 0">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="filteredRows.length"
          layout="total, sizes, prev, pager, next"
          @current-change="currentPage = 1"
          @size-change="(val) => { pageSize = val; currentPage = 1; }"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, VideoPlay, CloseBold, Refresh, Download } from '@element-plus/icons-vue'
import {
  ArrowLeft, List, Archive,
  CheckCircle2, XCircle, Percent, ListChecks
} from 'lucide-vue-next'
import { useSpaceContext } from '@/utils/spaceContext'
import * as evalApi from '@/api/eval'

const route = useRoute()
const router = useRouter()
const { currentSpace, onSpaceChange } = useSpaceContext()

const taskId = computed(() => parseInt(route.params.id))

const breadcrumbs = computed(() => {
  const items = [{ label: '评测中心', to: '/eval/tasks' }]
  if (task.value?.suite_name) {
    items.push({ label: task.value.suite_name })
  }
  items.push({ label: task.value?.name || '加载中...' })
  return items
})

// 数据
const task = ref(null)
const summary = ref(null)
const subtasks = ref([])
const runs = ref([])
const cases = ref([]) // 评测集用例
const manualVerifications = ref({}) // { runId: boolean }
const fixedStatus = ref({}) // { runId: boolean } 修复状态

// 加载状态
const loadingTable = ref(false)

// SSE连接
let progressEventSource = null

// 搜索和筛选
const searchKeyword = ref('')
const filterResult = ref('')
const filterStatus = ref('')
const filterDifficulty = ref('')
const filterCategory = ref('')

// 分页
const currentPage = ref(1)
const pageSize = ref(20)

// 用例 Map，方便按 case_id 查找（统一用字符串 key 避免类型不匹配）
const caseMap = computed(() => {
  const map = {}
  for (const c of cases.value) {
    map[String(c.id)] = c
  }
  return map
})

// 每个 case_id 对应的所有 run（按 sub_task_id + case_id 分组，取最新一条）
const caseRunsMap = computed(() => {
  const map = {}
  for (const run of runs.value) {
    const key = String(run.case_id)
    // 同一个 case 可能有多次 run（重试），保留最新的
    if (!map[key] || run.id > map[key].id) {
      map[key] = run
    }
  }
  return map
})

const difficultyOptions = computed(() => {
  return [...new Set(cases.value.map(c => c.difficulty).filter(Boolean))]
})

const categoryOptions = computed(() => {
  return [...new Set(cases.value.map(c => c.category).filter(Boolean))]
})

// 合并后的表格数据：每个评测用例一行（基于 run 记录）
const tableRows = computed(() => {
  const rows = []
  const seenCaseIds = new Set()

  // 以 run 记录为基础构建行（一个 case 一条，取最新 run）
  for (const run of runs.value) {
    const caseId = String(run.case_id)
    if (seenCaseIds.has(caseId)) continue
    seenCaseIds.add(caseId)

    const latestRun = caseRunsMap.value[caseId]
    const evalCase = caseMap.value[caseId] || null

    // 重试次数：同一 case_id 的 run 数量 - 1
    const allCaseRuns = runs.value.filter(r => String(r.case_id) === caseId)
    const retryCount = Math.max(0, allCaseRuns.length - 1)

    // 状态：取最新 run 所属 sub_task 的状态
    const sub = subtasks.value.find(s => s.id === latestRun.sub_task_id)
    let status = sub?.status || latestRun.status || 'completed'
    // 如果 run 已完成但 sub_task 状态可能还在 running，以 run 为准
    if (latestRun.status === 'success' || latestRun.status === 'error') {
      status = 'completed'
    }

    rows.push({
      id: latestRun.id,
      case_id: run.case_id,
      case_input: evalCase?.input_prompt || latestRun.case_input || `用例 #${run.case_id}`,
      expected_output: evalCase?.expected_output || latestRun.expected_output || '-',
      difficulty: evalCase?.difficulty || '',
      category: evalCase?.category || '',
      remark: evalCase?.remark || '',
      actual_output: latestRun.actual_output || '-',
      comparison_result: latestRun.comparison_result || 'pending',
      comparison_reason: latestRun.comparison_reason || '-',
      comparison_score: latestRun.comparison_score ?? null,
      trace_id: latestRun.trace_id || '',
      llm_judge_raw_output: latestRun.llm_judge_raw_output || '',
      manual_note: latestRun.manual_note || '',
      fixer_username: latestRun.fixer_username || '',
      run_id: latestRun.id,
      status,
      retry_count: retryCount,
    })
  }

  // 如果没有 run 记录但有 subtasks，用 subtask 数据兜底
  if (rows.length === 0 && subtasks.value.length > 0) {
    for (const sub of subtasks.value) {
      rows.push({
        id: sub.id,
        case_id: sub.case_id,
        case_input: `用例 #${sub.case_id || sub.id}`,
        expected_output: '-',
        difficulty: '',
        category: '',
        remark: '',
        actual_output: '-',
        comparison_result: 'pending',
        comparison_reason: '-',
        comparison_score: null,
        trace_id: '',
        llm_judge_raw_output: '',
        manual_note: '',
        fixer_username: '',
        run_id: null,
        status: sub.status,
        retry_count: 0,
      })
    }
  }

  return rows
})

// 筛选后的数据
const filteredRows = computed(() => {
  let rows = tableRows.value

  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    rows = rows.filter(r =>
      (r.case_input || '').toLowerCase().includes(kw) ||
      (r.expected_output || '').toLowerCase().includes(kw) ||
      (r.actual_output || '').toLowerCase().includes(kw)
    )
  }

  if (filterResult.value) {
    rows = rows.filter(r => r.comparison_result === filterResult.value)
  }

  if (filterStatus.value) {
    rows = rows.filter(r => r.status === filterStatus.value)
  }
  if (filterDifficulty.value) {
    rows = rows.filter(r => r.difficulty === filterDifficulty.value)
  }
  if (filterCategory.value) {
    rows = rows.filter(r => r.category === filterCategory.value)
  }

  return rows
})

// 分页后的数据
const paginatedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredRows.value.slice(start, start + pageSize.value)
})

// 是否可以导出
const canExport = computed(() => {
  if (!task.value) return false
  return task.value.status === 'completed'
})

// 获取人工校验状态：优先使用人工标注，否则默认取系统评判结果
function getManualVerified(row) {
  if (manualVerifications.value.hasOwnProperty(row.run_id)) {
    return manualVerifications.value[row.run_id]
  }
  // 默认：comparison_result === 'pass' 视为正确
  return row.comparison_result === 'pass'
}

// 人工校验调整后的统计
const manualAdjustedStats = computed(() => {
  let passed = 0
  let failed = 0

  for (const row of tableRows.value) {
    if (row.status !== 'completed') continue

    const verified = getManualVerified(row)
    if (verified) {
      passed++
    } else {
      failed++
    }
  }

  return { passed, failed }
})

// 调整后的通过率
const adjustedPassRate = computed(() => {
  const total = summary.value?.total || 0
  if (total === 0) return '0.0'
  return ((manualAdjustedStats.value.passed / total) * 100).toFixed(1)
})

// 通过率样式
const getRateClass = computed(() => {
  const rate = parseFloat(adjustedPassRate.value)
  if (rate >= 80) return 'rate-high'
  if (rate >= 60) return 'rate-medium'
  return 'rate-low'
})

// 人工校验切换
async function handleManualVerifyChange(row, val) {
  if (!row.run_id) {
    ElMessage.warning('该条目暂无运行记录，无法标注')
    return
  }
  try {
    await evalApi.manualCorrectRun(row.run_id, {
      is_correct: val,
      note: val ? '人工校验：正确' : '人工校验：错误'
    })
    manualVerifications.value[row.run_id] = val
    if (val) {
      fixedStatus.value[row.run_id] = true
    }
    ElMessage.success(val ? '已标记为正确' : '已标记为错误')
    await loadRuns()
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  }
}

// 修复状态切换
async function handleFixStatusChange(row, val) {
  if (!row.run_id) {
    ElMessage.warning('该条目暂无运行记录，无法修改修复状态')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt(
      val ? '请填写修改人备注，说明修复内容' : '请填写修改人备注，说明退回原因',
      val ? '标记为已修复' : '标记为未修复',
      {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputValue: row.manual_note || '',
        inputPlaceholder: '请输入修改人备注',
        inputValidator: (v) => !!String(v || '').trim() || '请填写修改人备注',
      }
    )
    const note = String(value || '').trim()
    await evalApi.manualCorrectRun(row.run_id, {
      is_correct: val,
      note,
    })
    fixedStatus.value[row.run_id] = val
    manualVerifications.value[row.run_id] = val
    ElMessage.success(val ? '已标记为已修复' : '已标记为未修复')
    await loadRuns()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('保存失败: ' + (e.message || e))
  }
}

// 执行状态标签
function getExecStatusLabel(row) {
  if (row.status === 'completed') return '已执行'
  if (row.status === 'running') return '执行中'
  if (row.status === 'pending') return '待执行'
  if (row.status === 'failed') {
    if (row.retry_count > 0) return `重试${row.retry_count}次`
    return '失败'
  }
  if (row.status === 'cancelled') return '已取消'
  return row.status || '-'
}

function getDifficultyLabel(difficulty) {
  return { easy: '简单', medium: '中等', hard: '困难' }[difficulty] || difficulty || '-'
}

function getResultRowClassName({ row }) {
  if (row.comparison_result === 'pass') return 'eval-row-pass'
  if (row.comparison_result === 'fail') return 'eval-row-fail'
  return 'eval-row-pending'
}

// 加载任务详情
async function loadTask() {
  if (!taskId.value || !currentSpace.value?.id) return
  try {
    const data = await evalApi.getEvalTask(taskId.value, currentSpace.value.id)
    data.progress = data.total_cases > 0
      ? Math.round(data.completed_cases / data.total_cases * 100)
      : 0
    task.value = data
    await loadSummary(data)

    if (task.value?.status === 'running' && !progressEventSource) {
      startProgressListener()
    }
  } catch (e) {
    ElMessage.error('加载任务失败: ' + e.message)
  }
}

async function loadSummary(fallbackTask = task.value) {
  if (!taskId.value || !currentSpace.value?.id) return
  try {
    const data = await evalApi.getEvalTaskSummary(taskId.value, currentSpace.value.id)
    summary.value = {
      total: data.total_cases || 0,
      completed: (data.passed || 0) + (data.failed || 0) + (data.error || 0),
      passed: data.passed || 0,
      failed: data.failed || 0,
      error: data.error || 0,
    }
  } catch (e) {
    if (!fallbackTask) throw e
    summary.value = {
      total: fallbackTask.total_cases || 0,
      completed: fallbackTask.completed_cases || 0,
      passed: fallbackTask.passed_cases || 0,
      failed: fallbackTask.failed_cases || 0,
      error: fallbackTask.error_cases || 0,
    }
  }
}

// 加载子任务列表
async function loadSubtasks() {
  if (!taskId.value || !currentSpace.value?.id) return
  try {
    subtasks.value = await evalApi.getEvalTaskSubTasks(taskId.value, currentSpace.value?.id)
  } catch (e) {
    ElMessage.error('加载子任务失败: ' + e.message)
  }
}

// 加载运行记录
async function loadRuns() {
  if (!subtasks.value.length) return
  try {
    const allRuns = []
    const results = await Promise.allSettled(
      subtasks.value.map(sub =>
        evalApi.getSubTaskRuns(sub.id, { limit: 100 })
          .then(data => ({ sub, data }))
      )
    )
    for (const result of results) {
      if (result.status === 'fulfilled') {
        const { sub, data } = result.value
        const items = data.items || data || []
        items.forEach(r => { r.sub_task_id = sub.id; r.target_type = sub.target_type })
        allRuns.push(...items)
      }
    }
    runs.value = allRuns

    // 初始化人工校验映射
    for (const run of allRuns) {
      if (run.manual_is_correct !== null && run.manual_is_correct !== undefined) {
        manualVerifications.value[run.id] = run.manual_is_correct
      }
      if (run.fix_status) {
        fixedStatus.value[run.id] = run.fix_status === '已修复'
      }
    }
  } catch (e) {
    ElMessage.error('加载运行记录失败: ' + e.message)
  }
}

// 启动SSE进度监听
function startProgressListener() {
  if (!currentSpace.value?.id) return
  if (progressEventSource) {
    progressEventSource.close()
  }

  const eventSource = new EventSource(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/eval/tasks/${taskId.value}/progress?space_id=${currentSpace.value.id}`)
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'progress') {
        task.value = {
          ...task.value,
          completed_cases: data.completed,
          passed_cases: data.passed,
          failed_cases: data.failed,
          error_cases: data.error,
          total_cases: data.total,
          progress: data.percentage,
          phase: data.phase || null,
        }
        summary.value = {
          ...summary.value,
          completed: data.completed,
          passed: data.passed,
          failed: data.failed,
          error: data.error,
          total: data.total,
        }
      } else if (data.type === 'done') {
        if (data.status === 'completed') {
          ElMessage.success('任务已完成')
        }
        eventSource.close()
        progressEventSource = null
        refreshAll()
      } else if (data.type === 'error') {
        ElMessage.error('任务执行出错: ' + data.message)
        eventSource.close()
        progressEventSource = null
      }
    } catch (e) {
      console.error('解析进度消息失败:', e)
    }
  }
  eventSource.onerror = () => {
    eventSource.close()
    progressEventSource = null
  }
  progressEventSource = eventSource
}

// 返回
function handleBack() {
  router.push('/eval/tasks')
}

// 任务控制
async function handleCancelTask() {
  try {
    await ElMessageBox.confirm('确定要取消该任务吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await evalApi.cancelEvalTask(taskId.value, currentSpace.value.id)
    ElMessage.success('任务已取消')
    loadTask()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('取消失败: ' + e.message)
  }
}

async function handleRetryFailed() {
  try {
    await ElMessageBox.confirm('确定要重试所有失败的用例吗？', '提示', {
      confirmButtonText: '确定重试',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await evalApi.retryFailedEvalTask(taskId.value, currentSpace.value.id)
    ElMessage.success('重试请求已发送')
    loadTask()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('重试失败: ' + e.message)
  }
}

async function handleRestartTask() {
  try {
    await ElMessageBox.confirm('确定要重新执行该任务吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await evalApi.startEvalTask(taskId.value, currentSpace.value.id)
    ElMessage.success('任务已重新启动')
    loadTask()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('启动失败: ' + e.message)
  }
}

async function handleArchiveFailed() {
  if (!canExport.value) {
    ElMessage.warning('任务全部执行完成后才可归档')
    return
  }
  try {
    await ElMessageBox.confirm('将所有失败用例复制到一个新的评测集中，确定继续吗？', '失败归档', {
      confirmButtonText: '确定归档',
      cancelButtonText: '取消',
      type: 'warning'
    })
    const res = await evalApi.archiveFailedEvalTask(taskId.value, currentSpace.value.id)
    ElMessage.success(`已归档 ${res.case_count || 0} 条失败用例`)
    if (res.suite_id) {
      router.push(`/eval/suite/${res.suite_id}`)
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('归档失败: ' + (e.message || e))
  }
}

// 导出结果（xlsx）
async function handleExport() {
  if (!canExport.value) {
    ElMessage.warning('任务全部执行完成后才可导出')
    return
  }
  try {
    const { default: ExcelJS } = await import('exceljs')
    const wb = new ExcelJS.Workbook()
    const ws = wb.addWorksheet('评测结果')

    // 表头
    ws.columns = [
      { header: '问题（输入）', key: 'case_input', width: 40 },
      { header: '期望答案', key: 'expected_output', width: 30 },
      { header: '实际答案', key: 'actual_output', width: 30 },
      { header: '难度', key: 'difficulty', width: 12 },
      { header: '分类', key: 'category', width: 16 },
      { header: '备注', key: 'remark', width: 28 },
      { header: 'TraceID', key: 'trace_id', width: 26 },
      { header: 'LLM响应', key: 'llm_response', width: 40 },
      { header: '评判结果', key: 'comparison_result', width: 12 },
      { header: '评判小结', key: 'comparison_reason', width: 50 },
      { header: '人工校验', key: 'manual_verify', width: 12 },
      { header: '修复状态', key: 'fix_status', width: 12 },
      { header: '修复人', key: 'fixer_username', width: 16 },
      { header: '修改人备注', key: 'manual_note', width: 28 },
      { header: '状态', key: 'status', width: 12 },
    ]

    // 表头样式
    ws.getRow(1).eachCell(cell => {
      cell.font = { bold: true, color: { argb: 'FFFFFFFF' } }
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF4972FB' } }
      cell.alignment = { vertical: 'middle', horizontal: 'center' }
    })

    const resultFill = {
      通过: 'FF67C23A',
      失败: 'FFF56C6C',
      待定: 'FF409EFF'
    }
    const manualFill = {
      正确: 'FF67C23A',
      错误: 'FFF56C6C'
    }
    const fixFill = {
      已修复: 'FF67C23A',
      未修复: 'FF909399'
    }
    const statusFill = {
      已执行: 'FF67C23A',
      执行中: 'FF409EFF',
      待执行: 'FF909399',
      失败: 'FFF56C6C',
      已取消: 'FFE6A23C'
    }
    const setTagStyle = (cell, color) => {
      if (!color) return
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: color } }
      cell.font = { color: { argb: 'FFFFFFFF' }, bold: true }
      cell.alignment = { vertical: 'middle', horizontal: 'center' }
    }

    // 数据
    for (const row of tableRows.value) {
      const resultLabel = row.comparison_result === 'pass' ? '通过' : row.comparison_result === 'fail' ? '失败' : '待定'
      const manualVal = getManualVerified(row) ? '正确' : '错误'
      const fixVal = row.fixer_username ? '已修复' : (fixedStatus.value[row.run_id] ? '已修复' : '未修复')
      const statusLabel = getExecStatusLabel(row)
      const exportStatusLabel = /^重试\d+次$/.test(statusLabel) ? '失败' : statusLabel
      const llmResponse = row.llm_judge_raw_output || ''

      const excelRow = ws.addRow({
        case_input: row.case_input || '',
        expected_output: row.expected_output || '',
        actual_output: row.actual_output || '',
        difficulty: row.difficulty || '',
        category: row.category || '',
        remark: row.remark || '',
        trace_id: row.trace_id || '',
        llm_response: llmResponse,
        comparison_result: resultLabel,
        comparison_reason: row.comparison_reason || '',
        manual_verify: manualVal,
        fix_status: row.comparison_result === 'fail' ? fixVal : '未修复',
        fixer_username: row.fixer_username || '',
        manual_note: row.manual_note || '',
        status: exportStatusLabel,
      })

      const rowNo = excelRow.number
      ws.getCell(`I${rowNo}`).dataValidation = {
        type: 'list',
        allowBlank: false,
        formulae: ['"通过,失败,待定"'],
      }
      ws.getCell(`K${rowNo}`).dataValidation = {
        type: 'list',
        allowBlank: false,
        formulae: ['"正确,错误"'],
      }
      ws.getCell(`L${rowNo}`).dataValidation = {
        type: 'list',
        allowBlank: false,
        formulae: ['"已修复,未修复"'],
      }
      ws.getCell(`O${rowNo}`).dataValidation = {
        type: 'list',
        allowBlank: false,
        formulae: ['"已执行,执行中,待执行,失败,已取消"'],
      }

      setTagStyle(ws.getCell(`I${rowNo}`), resultFill[resultLabel])
      setTagStyle(ws.getCell(`K${rowNo}`), manualFill[manualVal])
      setTagStyle(ws.getCell(`L${rowNo}`), fixFill[row.comparison_result === 'fail' ? fixVal : '未修复'])
      setTagStyle(ws.getCell(`O${rowNo}`), statusFill[exportStatusLabel] || 'FF909399')
    }

    const buffer = await wb.xlsx.writeBuffer()
    const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${task.value?.name || 'task'}_results.xlsx`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败: ' + e.message)
  }
}

// 状态转换
function getStatusLabel(status) {
  const map = {
    pending: '等待中',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return map[status] || status
}

// 初始化
// 加载评测集用例
async function loadCases() {
  if (!task.value?.suite_id) return
  try {
    const data = await evalApi.getEvalCases(task.value.suite_id, { page_size: 9999 })
    cases.value = (data.items || data || []).map(c => ({
      ...c,
      expected_output: c.ground_truths?.[0]?.ground_truth || c.expected_output || '',
      difficulty: c.difficulty || '',
      category: c.category || '',
      remark: c.remark || '',
    }))
  } catch (e) {
    console.error('加载评测集用例失败:', e)
  }
}

async function refreshAll() {
  loadingTable.value = true
  try {
    await loadTask()
    await loadCases()
    await loadSubtasks()
    await loadRuns()
  } finally {
    loadingTable.value = false
  }
}

onMounted(() => {
  refreshAll()
  onSpaceChange(() => {
    router.push('/eval/tasks')
  })
})

onUnmounted(() => {
  if (progressEventSource) {
    progressEventSource.close()
  }
})
</script>

<style scoped>
.task-detail-page {
  padding: 24px;
  width: 100%;
  box-sizing: border-box;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.back-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.back-btn :deep(svg) { width: 16px; height: 16px; }

/* 汇总卡片 */
.summary-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
  margin-bottom: 16px;
}

.summary-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.summary-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.top-task-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.top-meta {
  font-size: 12px;
  color: var(--text-muted);
}

.summary-stats {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-left: auto;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: var(--text-muted);
}

.stat-item :deep(svg) { opacity: 0.6; }

.stat-num {
  font-weight: 700;
  font-size: 16px;
  color: var(--text-primary);
}

.stat-num.success { color: var(--success); }
.stat-num.danger { color: var(--danger); }
.stat-num.rate-high { color: var(--success); }
.stat-num.rate-medium { color: var(--warning); }
.stat-num.rate-low { color: var(--danger); }

.stat-lbl {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 2px;
}

.progress-inline {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.progress-inline .progress-bar { flex: 1; }

.progress-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  min-width: 36px;
  text-align: right;
}

.phase-tag {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
  margin-left: 8px;
}

.phase-tag.target {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.phase-tag.judge {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.meta-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 20px;
  background: var(--bg-tertiary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}

.meta-tag.status-pending .status-dot { background: var(--text-muted); }
.meta-tag.status-running .status-dot { background: var(--accent); animation: pulse 1.5s infinite; }
.meta-tag.status-paused .status-dot { background: var(--warning); }
.meta-tag.status-completed .status-dot { background: var(--success); }
.meta-tag.status-failed .status-dot { background: var(--danger); }

.meta-tag.status-running { background: var(--accent)22; color: var(--accent); }
.meta-tag.status-completed { background: var(--success)22; color: var(--success); }
.meta-tag.status-failed { background: var(--danger)22; color: var(--danger); }

.header-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  margin-left: 16px;
}

.btn-sm {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  font-size: 12px;
  font-weight: 500;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-sm :deep(svg) { width: 13px; height: 13px; }

.btn-sm.btn-danger { background: var(--danger); color: #fff; }
.btn-danger:hover { background: #d94040; }

.btn-sm.btn-outline {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.btn-sm.btn-outline:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.btn-sm.btn-outline:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-sm.btn-outline:disabled:hover {
  border-color: var(--border);
  color: var(--text-secondary);
}

.progress-bar {
  height: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.progress-fill.running {
  background: linear-gradient(90deg, var(--accent) 0%, var(--cyan) 100%);
  animation: progress-shine 2s linear infinite;
  background-size: 200% 100%;
}

@keyframes progress-shine {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* 结果表格区域 */
.result-table-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow-x: auto;
}

.table-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.table-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.table-title :deep(svg) { color: var(--accent); }

.toolbar-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.cases-table-wrap {
  min-height: 200px;
  overflow: auto;
}

.result-table {
  width: 100%;
}

.result-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--bg-primary) !important;
  padding: 8px 10px;
}

.result-table :deep(.el-table__body td) {
  font-size: 13px;
  color: var(--text-primary);
  padding: 8px 10px;
}

/* 多行文本截断 */
.cell-multi {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
  word-break: break-all;
  width: 100%;
  max-width: 100%;
}

.cell-single {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.difficulty-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
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

.difficulty-badge.unknown {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.result-tag {
  display: inline-flex;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
}

.result-tag.pass {
  background: var(--success)22;
  color: var(--success);
}

.result-tag.fail {
  background: var(--danger)22;
  color: var(--danger);
}

.result-tag.pending {
  background: var(--warning)22;
  color: var(--warning);
}

.status-badge-tag {
  display: inline-flex;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.status-badge-tag.st-completed {
  background: var(--success)22;
  color: var(--success);
}

.status-badge-tag.st-running {
  background: var(--accent)22;
  color: var(--accent);
}

.status-badge-tag.st-pending {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.status-badge-tag.st-failed {
  background: var(--danger)22;
  color: var(--danger);
}

.status-badge-tag.st-cancelled {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.icon-state-btn,
.status-icon {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.icon-state-btn {
  border: 1px solid var(--border);
  background: var(--bg-primary);
  cursor: pointer;
}

.icon-state-btn :deep(svg),
.status-icon :deep(svg) {
  width: 15px;
  height: 15px;
  stroke: currentColor;
  stroke-width: 2.4;
}

.icon-state-btn.ok,
.status-icon.st-completed {
  color: #67c23a;
  background: rgba(103, 194, 58, 0.14);
  border-color: rgba(103, 194, 58, 0.22);
}

.icon-state-btn.bad,
.status-icon.st-failed {
  color: #f56c6c;
  background: rgba(245, 108, 108, 0.14);
  border-color: rgba(245, 108, 108, 0.22);
}

.icon-state-btn.fixed,
.status-icon.st-running {
  color: #409eff;
  background: rgba(64, 158, 255, 0.14);
  border-color: rgba(64, 158, 255, 0.22);
}

.icon-state-btn.muted,
.status-icon.st-pending,
.status-icon.st-cancelled {
  color: #909399;
  background: rgba(144, 147, 153, 0.12);
  border-color: rgba(144, 147, 153, 0.18);
}

.result-table :deep(.el-table__body tr.eval-row-pass > td) {
  background: rgba(103, 194, 58, 0.055) !important;
}

.result-table :deep(.el-table__body tr.eval-row-fail > td) {
  background: rgba(245, 108, 108, 0.055) !important;
}

.result-table :deep(.el-table__body tr.eval-row-pending > td) {
  background: rgba(144, 147, 153, 0.045) !important;
}

.result-table :deep(.el-table__body tr:hover > td) {
  background: rgba(64, 158, 255, 0.08) !important;
}

.result-table :deep(.el-table__cell.is-hidden > *) {
  visibility: hidden;
}

.result-table :deep(.el-table-fixed-column--right),
.result-table :deep(.el-table__cell.is-fixed-right) {
  z-index: 12 !important;
  background-clip: padding-box;
  box-shadow: -8px 0 14px -14px rgba(15, 23, 42, 0.35);
}

.result-table :deep(.el-table__header .el-table-fixed-column--right),
.result-table :deep(.el-table__header .el-table__cell.is-fixed-right) {
  z-index: 18 !important;
  background: var(--bg-primary) !important;
}

.result-table :deep(.el-table__body tr.eval-row-pass > td.el-table-fixed-column--right),
.result-table :deep(.el-table__body tr.eval-row-pass > td.is-fixed-right) {
  background: rgb(247, 253, 244) !important;
}

.result-table :deep(.el-table__body tr.eval-row-fail > td.el-table-fixed-column--right),
.result-table :deep(.el-table__body tr.eval-row-fail > td.is-fixed-right) {
  background: rgb(255, 248, 248) !important;
}

.result-table :deep(.el-table__body tr.eval-row-pending > td.el-table-fixed-column--right),
.result-table :deep(.el-table__body tr.eval-row-pending > td.is-fixed-right) {
  background: rgb(250, 250, 251) !important;
}

.result-table :deep(.el-table__body tr:hover > td.el-table-fixed-column--right),
.result-table :deep(.el-table__body tr:hover > td.is-fixed-right) {
  background: rgb(244, 249, 255) !important;
}

.text-muted {
  font-size: 12px;
  color: var(--text-muted);
}

/* 空状态 */
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

.empty-icon-wrap :deep(svg) { width: 28px; height: 28px; opacity: 0.5; }

.empty-table p {
  font-size: 14px;
  margin: 0;
}

/* 分页 */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
