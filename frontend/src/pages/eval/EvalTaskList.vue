<template>
  <div class="eval-task-list">
    <PageHeader
      :breadcrumbs="[{ label: '评测中心' }, { label: '任务管理' }]"
    >
      <template #actions>
        <el-button type="primary" @click="handleCreateTask">
          <Plus />
          创建任务
        </el-button>
      </template>
    </PageHeader>

    <!-- 统计概览 -->
    <div class="stats-row">
      <div class="stat-item">
        <span class="stat-value">{{ totalTasks }}</span>
        <span class="stat-label">总任务</span>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-value running">{{ runningTasks }}</span>
        <span class="stat-label">运行中</span>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-value success">{{ completedTasks }}</span>
        <span class="stat-label">已完成</span>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <span class="stat-value danger">{{ failedTasks }}</span>
        <span class="stat-label">失败</span>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filters-bar">
      <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 140px;" @change="loadTasks" class="filter-select">
        <el-option label="全部" value="" />
        <el-option label="草稿" value="draft" />
        <el-option label="待执行" value="scheduled" />
        <el-option label="待启动" value="pending" />
        <el-option label="启动中" value="starting" />
        <el-option label="运行中" value="running" />
        <el-option label="已完成" value="completed" />
        <el-option label="成功" value="success" />
        <el-option label="失败" value="failed" />
        <el-option label="已取消" value="cancelled" />
      </el-select>
      <el-select v-model="suiteFilter" placeholder="选择评测集" clearable style="width: 180px;" @change="loadTasks" class="filter-select">
        <el-option v-for="suite in suites" :key="suite.id" :label="suite.name" :value="suite.id" />
      </el-select>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading && tasks.length === 0" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>加载中...</span>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!loading && tasks.length === 0" class="empty-state">
      <div class="empty-icon-wrap">
        <List style="width: 40px; height: 40px;" />
      </div>
      <p class="empty-title">暂无任务</p>
      <p class="empty-hint">点击「创建任务」开始您的第一个评测</p>
    </div>

    <!-- 任务列表 -->
    <div v-else class="task-list">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="task-card"
        :class="{ running: task.status === 'running' }"
        @click="handleTaskClick(task)"
      >
        <div class="task-header">
          <div class="task-info">
            <h3 class="task-name">{{ task.name }}</h3>
            <div class="task-meta">
              <span v-if="task.description" class="meta-tag desc">{{ task.description }}</span>
              <span class="meta-tag time">
                <Clock style="width: 12px; height: 12px;" />
                {{ formatDateTime(task.created_at) }}
              </span>
              <span v-if="task.scheduled_at && task.status === 'scheduled'" class="meta-tag scheduled">
                <Clock style="width: 12px; height: 12px;" />
                定时: {{ formatDateTime(task.scheduled_at) }}
              </span>
              <span v-if="task.status === 'running' && task.phase" class="meta-tag phase">
                {{ task.phase === 'target' ? '执行任务中' : '评测中' }}
              </span>
              <span v-if="task.status === 'running' && (task.estimated_target_seconds || task.estimated_judge_seconds)" class="meta-tag eta">
                <Clock style="width: 12px; height: 12px;" />
                预计剩余: {{ formatDuration((task.estimated_target_seconds || 0) + (task.estimated_judge_seconds || 0)) }}
              </span>
            </div>
          </div>
          <span class="status-badge" :class="task.status">{{ getStatusLabel(task.status) }}</span>
        </div>

        <div class="task-progress-section" v-if="task.status === 'running' || task.progress > 0">
          <div class="progress-header">
            <span class="progress-label">执行进度</span>
            <span class="progress-value">{{ task.progress || 0 }}%</span>
          </div>
          <div class="progress-bar">
            <div
              class="progress-fill"
              :class="task.status"
              :style="{ width: (task.progress || 0) + '%' }"
            ></div>
          </div>
          <div class="progress-stats">
            <span class="stat pass">
              <el-icon><SuccessFilled /></el-icon>
              {{ task.passed || 0 }} 通过
            </span>
            <span class="stat fail">
              <el-icon><CircleCloseFilled /></el-icon>
              {{ task.failed || 0 }} 失败
            </span>
          </div>
        </div>

        <div class="task-footer">
          <div class="task-pass-rate" v-if="task.total > 0">
            <span class="pass-rate-value" :class="getPassRateClass(task.pass_rate)">
              {{ task.pass_rate || 0 }}%
            </span>
            <span class="pass-rate-label">通过率</span>
          </div>
          <div class="task-actions" @click.stop>
            <el-button
              v-if="task.status === 'draft' || task.status === 'pending' || task.status === 'scheduled' || isTaskStarting(task)"
              type="primary"
              size="small"
              :loading="isTaskStarting(task)"
              :disabled="isTaskStarting(task)"
              @click="handleStartTask(task)"
              class="action-btn start"
            >
              <VideoPlay v-if="!isTaskStarting(task)" style="width: 13px; height: 13px;" />
              {{ isTaskStarting(task) ? '启动中' : '启动' }}
            </el-button>
            <el-button
              v-if="task.status === 'running'"
              type="danger"
              size="small"
              @click="handleCancelTask(task)"
              class="action-btn cancel"
            >
              <Close style="width: 13px; height: 13px;" />
              取消
            </el-button>
            <el-button
              v-if="task.status === 'completed' || task.status === 'success' || task.status === 'failed'"
              size="small"
              @click="handleViewTask(task)"
              class="action-btn"
            >
              <View style="width: 13px; height: 13px;" />
              查看
            </el-button>
            <el-button
              v-if="task.status === 'failed'"
              size="small"
              @click="handleRetryTask(task)"
              class="action-btn retry"
            >
              <RefreshRight style="width: 13px; height: 13px;" />
              重试
            </el-button>
            <el-button
              v-if="task.status === 'cancelled'"
              size="small"
              @click="handleViewTask(task)"
              class="action-btn"
            >
              <View style="width: 13px; height: 13px;" />
              查看
            </el-button>
            <el-button
              v-if="task.status === 'cancelled'"
              type="primary"
              size="small"
              :loading="isTaskStarting(task)"
              :disabled="isTaskStarting(task)"
              @click="handleStartTask(task)"
              class="action-btn start"
            >
              <VideoPlay v-if="!isTaskStarting(task)" style="width: 13px; height: 13px;" />
              {{ isTaskStarting(task) ? '启动中' : '重新执行' }}
            </el-button>
            <el-button
              v-if="task.status !== 'running' && task.status !== 'starting'"
              size="small"
              @click="handleEditTask(task)"
              class="action-btn"
            >
              <Edit style="width: 13px; height: 13px;" />
              编辑
            </el-button>
            <el-button
              v-if="task.status !== 'running' && task.status !== 'starting'"
              size="small"
              type="danger"
              @click="handleDeleteTask(task)"
              class="action-btn delete"
            >
              <Delete style="width: 13px; height: 13px;" />
              删除
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination" v-if="total > pageSize">
      <span class="pagination-info">
        显示 {{ (currentPage - 1) * pageSize + 1 }}-{{ Math.min(currentPage * pageSize, total) }}，共 {{ total }} 条
      </span>
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="loadTasks"
      />
    </div>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      title="编辑任务"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="任务名称" required>
          <el-input
            v-model="editForm.name"
            placeholder="任务名称"
            maxlength="200"
          />
        </el-form-item>
        <el-form-item label="任务描述">
          <el-input
            v-model="editForm.description"
            type="textarea"
            :rows="3"
            placeholder="任务描述（可选）"
          />
        </el-form-item>
        <el-form-item label="定时执行">
          <el-switch v-model="editForm.scheduleEnabled" @change="onScheduleToggle" />
        </el-form-item>
        <template v-if="editForm.scheduleEnabled">
          <div class="schedule-presets">
            <div class="presets-label">快捷选择</div>
            <div class="presets-grid">
              <div
                v-for="p in schedulePresets"
                :key="p.label"
                class="preset-chip"
                :class="{ active: editSelectedPreset === p.label }"
                @click="selectEditPreset(p)"
              >
                {{ p.label }}
              </div>
            </div>
          </div>
          <div class="schedule-custom">
            <div class="custom-label">或自定义时间</div>
            <el-time-picker
              v-model="editCustomTime"
              placeholder="选择时分"
              format="HH:mm"
              value-format="HH:mm"
              style="width: 100%"
              @change="onEditCustomTimeChange"
            />
            <div class="field-tip">仅支持选择未来 24 小时内的时间</div>
          </div>
          <div v-if="editForm.scheduled_at" class="schedule-preview">
            将在 <strong>{{ formatScheduledAt(editForm.scheduled_at) }}</strong> 自动执行
          </div>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSaveEdit" :loading="editSaving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Clock, List, Loading, VideoPlay, Close,
  View, RefreshRight, SuccessFilled, CircleCloseFilled, Edit, Delete
} from '@element-plus/icons-vue'
import { useSpaceContext } from '@/utils/spaceContext'
import * as evalApi from '@/api/eval'

const router = useRouter()
const { currentSpace, onSpaceChange } = useSpaceContext()

const loading = ref(false)
const tasks = ref([])
const suites = ref([])

const totalTasks = ref(0)
const runningTasks = ref(0)
const completedTasks = ref(0)
const failedTasks = ref(0)

const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)

const statusFilter = ref('')
const suiteFilter = ref('')
const startingTaskIds = ref(new Set())
let refreshTimer = null

// 编辑相关
const editDialogVisible = ref(false)
const editSaving = ref(false)
const editTaskId = ref(null)
const editForm = ref({ name: '', description: '', scheduleEnabled: false, scheduled_at: null })
const editSelectedPreset = ref(null)
const editCustomTime = ref(null)

const schedulePresets = [
  { label: '30 分钟后', minutes: 30 },
  { label: '1 小时后', minutes: 60 },
  { label: '2 小时后', minutes: 120 },
  { label: '4 小时后', minutes: 240 },
  { label: '明天 9:00', minutes: -1 },
]

async function loadTasks(silent = false) {
  if (!currentSpace.value?.id) return
  const shouldShowLoading = !silent && tasks.value.length === 0
  if (shouldShowLoading) loading.value = true
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value
    }
    if (statusFilter.value) params.status = statusFilter.value
    if (suiteFilter.value) params.suite_id = suiteFilter.value

    const data = await evalApi.getEvalTasks(currentSpace.value.id, params)
    tasks.value = data.items || []
    total.value = data.total || 0
    syncPolling()
  } catch (e) {
    ElMessage.error('加载任务失败: ' + e.message)
  } finally {
    if (shouldShowLoading) loading.value = false
  }
}

function syncPolling() {
  const hasRunning = tasks.value.some(t => t.status === 'running' || t.status === 'starting')
  if (hasRunning && !refreshTimer) {
    refreshTimer = window.setInterval(() => {
      loadTasks(true)
      loadStats()
    }, 3000)
  } else if (!hasRunning && refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

async function loadStats() {
  if (!currentSpace.value?.id) return
  try {
    const suiteId = suiteFilter.value || undefined
    const data = await evalApi.getEvalTaskStats(currentSpace.value.id, { suite_id: suiteId })
    totalTasks.value = data.total || 0
    runningTasks.value = data.running || 0
    completedTasks.value = data.completed || 0
    failedTasks.value = data.failed || 0
  } catch (e) {
    console.error('加载统计失败:', e)
  }
}

async function loadSuites() {
  if (!currentSpace.value?.id) return
  try {
    const data = await evalApi.getEvalSuites(currentSpace.value.id, { limit: 1000 })
    suites.value = data.items || []
  } catch (e) {
    console.error('加载评测集失败:', e)
  }
}

function handleCreateTask() {
  router.push('/eval/task/create')
}

function handleTaskClick(task) {
  router.push(`/eval/task/${task.id}`)
}

function handleViewTask(task) {
  router.push(`/eval/task/${task.id}`)
}

function isTaskStarting(task) {
  return task?.status === 'starting' || startingTaskIds.value.has(task?.id)
}

function setTaskStarting(taskId, starting) {
  const next = new Set(startingTaskIds.value)
  if (starting) {
    next.add(taskId)
  } else {
    next.delete(taskId)
  }
  startingTaskIds.value = next
}

async function handleStartTask(task) {
  if (!task?.id || isTaskStarting(task)) return
  const previousStatus = task.status
  setTaskStarting(task.id, true)
  task.status = 'starting'
  syncPolling()
  try {
    await evalApi.startEvalTask(task.id, currentSpace.value.id)
    ElMessage.success('任务已启动')
    loadTasks()
    loadStats()
  } catch (e) {
    task.status = previousStatus
    ElMessage.error('启动失败: ' + e.message)
  } finally {
    setTaskStarting(task.id, false)
  }
}

async function handleCancelTask(task) {
  try {
    await ElMessageBox.confirm('确定要取消该任务吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await evalApi.cancelEvalTask(task.id, currentSpace.value.id)
    ElMessage.success('任务已取消')
    loadTasks()
    loadStats()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('取消失败: ' + e.message)
  }
}

async function handleRetryTask(task) {
  try {
    await evalApi.retryFailedEvalTask(task.id, currentSpace.value.id)
    ElMessage.success('重试请求已发送')
  } catch (e) {
    ElMessage.error('重试失败: ' + e.message)
  }
}

function handleEditTask(task) {
  editTaskId.value = task.id
  editForm.value = {
    name: task.name,
    description: task.description || '',
    scheduleEnabled: task.status === 'scheduled' && !!task.scheduled_at,
    scheduled_at: task.scheduled_at || null,
  }
  editSelectedPreset.value = null
  editCustomTime.value = null
  editDialogVisible.value = true
}

function onScheduleToggle(enabled) {
  if (!enabled) {
    editForm.value.scheduled_at = null
    editSelectedPreset.value = null
    editCustomTime.value = null
  }
}

function selectEditPreset(preset) {
  editSelectedPreset.value = preset.label
  editCustomTime.value = null
  const now = new Date()
  if (preset.minutes === -1) {
    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)
    tomorrow.setHours(9, 0, 0, 0)
    editForm.value.scheduled_at = formatForApi(tomorrow)
  } else {
    const target = new Date(now.getTime() + preset.minutes * 60 * 1000)
    editForm.value.scheduled_at = formatForApi(target)
  }
}

function onEditCustomTimeChange(val) {
  if (!val) return
  editSelectedPreset.value = null
  const [h, m] = val.split(':').map(Number)
  const now = new Date()
  const target = new Date(now)
  target.setHours(h, m, 0, 0)
  if (target <= now) target.setDate(target.getDate() + 1)
  const max = new Date(now.getTime() + 24 * 60 * 60 * 1000)
  if (target > max) {
    ElMessage.warning('时间不能超过 24 小时后')
    editCustomTime.value = null
    editForm.value.scheduled_at = null
    return
  }
  editForm.value.scheduled_at = formatForApi(target)
}

function formatForApi(date) {
  const y = date.getFullYear()
  const mo = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const mi = String(date.getMinutes()).padStart(2, '0')
  return `${y}-${mo}-${d}T${h}:${mi}:00`
}

function formatScheduledAt(val) {
  if (!val) return ''
  return new Date(val).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

async function handleSaveEdit() {
  if (!editForm.value.name.trim()) {
    ElMessage.warning('任务名称不能为空')
    return
  }
  if (editForm.value.scheduleEnabled && !editForm.value.scheduled_at) {
    ElMessage.warning('请选择定时执行时间')
    return
  }
  editSaving.value = true
  try {
    const payload = {
      name: editForm.value.name.trim(),
      description: editForm.value.description,
    }
    if (editForm.value.scheduleEnabled && editForm.value.scheduled_at) {
      payload.scheduled_at = editForm.value.scheduled_at
    } else if (!editForm.value.scheduleEnabled) {
      payload.scheduled_at = null
    }
    await evalApi.updateEvalTask(editTaskId.value, currentSpace.value.id, payload)
    ElMessage.success('修改成功')
    editDialogVisible.value = false
    loadTasks()
  } catch (e) {
    ElMessage.error('修改失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    editSaving.value = false
  }
}

async function handleDeleteTask(task) {
  try {
    await ElMessageBox.confirm(
      `确定要删除任务「${task.name}」吗？此操作不可恢复。`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )
    await evalApi.deleteEvalTask(task.id, currentSpace.value.id)
    ElMessage.success('已删除')
    loadTasks()
    loadStats()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

function getStatusLabel(status) {
  const map = {
    draft: '草稿',
    scheduled: '待执行',
    pending: '待启动',
    starting: '启动中',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    success: '成功',
    failed: '失败',
    cancelled: '已取消',
    partial: '部分失败'
  }
  return map[status] || status
}

function getPassRateClass(rate) {
  if (rate >= 80) return 'high'
  if (rate >= 60) return 'medium'
  return 'low'
}

function formatDateTime(dateStr) {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '--'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}min`
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return `${h}h ${m}min`
}

onMounted(() => {
  onSpaceChange(() => {
    currentPage.value = 1
    statusFilter.value = ''
    suiteFilter.value = ''
    loadTasks()
    loadStats()
    loadSuites()
  })
})

watch(
  () => currentSpace.value?.id,
  (spaceId) => {
    if (!spaceId) return
    loadTasks()
    loadStats()
    loadSuites()
  },
  { immediate: true }
)

onUnmounted(() => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.eval-task-list {
  padding: 20px 24px;
  background: var(--bg-primary);
}

.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.create-btn {
  border-radius: 8px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 统计概览 */
.stats-row {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 16px 24px;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  margin-bottom: 16px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 0 24px;
}

.stat-item:first-child {
  padding-left: 0;
}

.stat-divider {
  width: 1px;
  height: 36px;
  background: var(--border-color);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-value.running { color: #409eff; }
.stat-value.success { color: #67c23a; }
.stat-value.danger { color: #f56c6c; }

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

/* 筛选栏 */
.filters-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.filter-select :deep(.el-input__wrapper) {
  border-radius: 8px;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 80px;
  color: var(--text-muted);
}

.loading-state .el-icon {
  font-size: 32px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
}

.empty-icon-wrap {
  width: 80px;
  height: 80px;
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-color-primary);
  margin-bottom: 16px;
}

.empty-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

/* 任务列表 */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 18px 20px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.task-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
}

.task-card.running {
  border-left: 3px solid #409eff;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}

.task-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.meta-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 11px;
  background: var(--bg-primary);
  border-radius: 4px;
  color: var(--text-muted);
}

.meta-tag.scheduled {
  color: #e6a23c;
  background: rgba(230, 162, 60, 0.08);
}

.meta-tag.phase {
  color: #409eff;
  background: rgba(64, 158, 255, 0.08);
  font-weight: 500;
}

.meta-tag.eta {
  color: #67c23a;
  background: rgba(103, 194, 58, 0.08);
}

.meta-tag.desc {
  color: var(--text-secondary);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-badge {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
}

.status-badge.draft,
.status-badge.pending {
  background: var(--bg-primary);
  color: var(--text-muted);
}

.status-badge.scheduled {
  background: rgba(230, 162, 60, 0.1);
  color: #e6a23c;
}

.status-badge.starting {
  background: rgba(144, 147, 153, 0.1);
  color: #909399;
}

.status-badge.running {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.status-badge.completed {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.status-badge.success {
  background: rgba(103, 194, 58, 0.15);
  color: #529b2e;
}

.status-badge.failed {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.status-badge.cancelled {
  background: rgba(144, 147, 153, 0.1);
  color: #909399;
}

/* 进度 */
.task-progress-section {
  margin-bottom: 14px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.progress-label {
  font-size: 12px;
  color: var(--text-muted);
}

.progress-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.progress-bar {
  height: 6px;
  background: var(--bg-primary);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 10px;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-fill.running {
  background: linear-gradient(90deg, #409eff 0%, #67c23a 100%);
}

.progress-fill.completed,
.progress-fill.success {
  background: #67c23a;
}

.progress-fill.failed {
  background: #f56c6c;
}

.progress-stats {
  display: flex;
  gap: 20px;
}

.progress-stats .stat {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.progress-stats .stat.pass { color: #67c23a; }
.progress-stats .stat.fail { color: #f56c6c; }

/* 底部 */
.task-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 14px;
  border-top: 1px solid var(--border-color);
}

.task-pass-rate {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.pass-rate-value {
  font-size: 20px;
  font-weight: 700;
}

.pass-rate-value.high { color: #67c23a; }
.pass-rate-value.medium { color: #e6a23c; }
.pass-rate-value.low { color: #f56c6c; }

.pass-rate-label {
  font-size: 12px;
  color: var(--text-muted);
}

.task-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.action-btn {
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}

.action-btn.start {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}

.action-btn.cancel {
  background: #f56c6c;
  border-color: #f56c6c;
  color: #fff;
}

.action-btn.retry {
  color: #e6a23c;
}

.action-btn.delete {
  color: #fff;
}

/* 分页 */
.pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}

.pagination-info {
  font-size: 13px;
  color: var(--text-muted);
}

.field-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-warning);
  line-height: 1.5;
}

/* ── Schedule presets ── */
.schedule-presets {
  margin-bottom: 16px;
}

.presets-label,
.custom-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.presets-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preset-chip {
  padding: 5px 12px;
  font-size: 12px;
  border: 1px solid var(--border-color);
  border-radius: 14px;
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
  margin-bottom: 12px;
}

.schedule-preview {
  padding: 8px 12px;
  background: var(--el-color-primary-light-9);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.schedule-preview strong {
  color: var(--el-color-primary);
  font-weight: 600;
}
</style>
