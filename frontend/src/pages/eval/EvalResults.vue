<template>
  <div class="eval-results">
    <PageHeader
      :breadcrumbs="[{ label: '评测中心' }, { label: '评测结果' }]"
    />

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索任务名称..."
        style="width: 220px;"
        clearable
        @clear="loadResults"
        @keyup.enter="loadResults"
        class="search-input"
      >
        <template #prefix><Search /></template>
      </el-input>
      <el-select v-model="filterSuiteId" placeholder="选择评测集" clearable style="width: 180px;" @change="loadResults" class="filter-select">
        <el-option v-for="s in suites" :key="s.id" :label="s.name" :value="s.id" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="执行状态" clearable style="width: 140px;" @change="loadResults" class="filter-select">
        <el-option label="全部" value="" />
        <el-option label="成功" value="completed" />
        <el-option label="失败" value="failed" />
        <el-option label="部分通过" value="partial" />
      </el-select>
    </div>

    <!-- 结果列表 -->
    <div class="results-list">
      <el-table
        v-loading="loading"
        :data="results"
        stripe
        @row-click="handleRowClick"
        class="results-table"
      >
        <el-table-column prop="task_name" label="任务名称" min-width="160" />
        <el-table-column prop="suite_name" label="评测集" min-width="120" />
        <el-table-column label="通过率" width="100" align="center">
          <template #default="{ row }">
            <span class="pass-rate" :class="getRateClass(row.score)">
              {{ row.score != null ? (row.score * 100).toFixed(1) + '%' : '--' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="case_count" label="用例数" width="80" align="center">
          <template #default="{ row }">
            <span class="case-count">{{ row.case_count || 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="120" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress || 0"
              :show-text="false"
              :stroke-width="6"
              :status="row.status === 'failed' ? 'exception' : row.status === 'completed' || row.status === 'success' ? 'success' : undefined"
            />
            <span class="progress-text">{{ row.completed_cases || 0 }}/{{ row.total_cases || 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <span class="status-badge" :class="row.status">{{ getStatusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="comparison_method" label="对比方式" width="100" align="center">
          <template #default="{ row }">
            <span class="method-tag">{{ row.comparison_method || 'exact' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="执行时间" width="160">
          <template #default="{ row }">
            <span class="date-text">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button text size="small" type="primary" @click.stop="router.push(`/eval/task/${row.id}`)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 空状态 -->
      <div v-if="!loading && results.length === 0" class="empty-state">
        <div class="empty-icon-wrap">
          <Trophy style="width: 40px; height: 40px;" />
        </div>
        <p class="empty-title">{{ emptyTitle }}</p>
        <p class="empty-hint">{{ emptyHint }}</p>
        <el-button v-if="!filterStatus && !filterSuiteId && !searchKeyword" type="primary" @click="router.push('/eval/task/create')">
          创建评测任务
        </el-button>
      </div>
    </div>

    <!-- 分页 -->
    <div class="pagination-wrapper" v-if="total > 0">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadResults"
      />
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" title="评测结果详情" size="480px" class="result-drawer">
      <div v-if="selectedResult" class="result-detail">
        <div class="detail-stat-row">
          <div class="detail-stat">
            <span class="stat-label">通过率</span>
            <span class="stat-value pass-rate" :class="getRateClass(selectedResult.score)">
              {{ selectedResult.score != null ? (selectedResult.score * 100).toFixed(1) + '%' : '--' }}
            </span>
          </div>
          <div class="detail-stat">
            <span class="stat-label">用例数</span>
            <span class="stat-value">{{ selectedResult.case_count || 0 }}</span>
          </div>
          <div class="detail-stat">
            <span class="stat-label">对比方式</span>
            <span class="stat-value">{{ selectedResult.comparison_method || 'exact' }}</span>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">任务名称</div>
          <div class="detail-content">{{ selectedResult.task_name }}</div>
        </div>
        <div class="detail-section">
          <div class="detail-label">评测集</div>
          <div class="detail-content">{{ selectedResult.suite_name }}</div>
        </div>
        <div class="detail-section">
          <div class="detail-label">执行时间</div>
          <div class="detail-content">{{ formatDate(selectedResult.created_at) }}</div>
        </div>
        <div class="detail-action">
          <el-button type="primary" @click="router.push(`/eval/task/${selectedResult.id}`); detailVisible = false">
            查看完整详情
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Trophy } from '@element-plus/icons-vue'
import { useSpaceContext } from '@/utils/spaceContext'
import * as evalApi from '@/api/eval'

const router = useRouter()
const { currentSpace, onSpaceChange } = useSpaceContext()

const loading = ref(false)
const results = ref([])
const suites = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const filterSuiteId = ref('')
const filterStatus = ref('')
const detailVisible = ref(false)
const selectedResult = ref(null)
let refreshTimer = null

const emptyTitle = computed(() => {
  if (searchKeyword.value || filterSuiteId.value || filterStatus.value) return '没有匹配的评测结果'
  return '暂无评测结果'
})

const emptyHint = computed(() => {
  if (filterStatus.value === 'running') return '当前没有正在执行的评测任务'
  if (searchKeyword.value || filterSuiteId.value || filterStatus.value) return '调整筛选条件后再试'
  return '创建并执行评测任务后，结果将显示在这里'
})

async function loadResults() {
  if (!currentSpace.value?.id) return
  loading.value = true
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    }
    if (filterSuiteId.value) params.suite_id = filterSuiteId.value
    if (searchKeyword.value) params.keyword = searchKeyword.value
    if (filterStatus.value) params.status = filterStatus.value

    const taskData = await evalApi.getEvalTasks(currentSpace.value.id, params)
    const tasks = taskData.items || taskData || []

    // 加载 suite 信息用于显示名称
    const suiteData = await evalApi.getEvalSuites(currentSpace.value.id, { limit: 1000 })
    const allSuites = (suiteData.items || suiteData || [])

    results.value = tasks.map(t => {
      const suite = allSuites.find(s => s.id === t.suite_id)
      return {
        id: t.id,
        task_name: t.name,
        suite_name: suite?.name || '未知',
        case_count: t.total_cases,
        total_cases: t.total_cases || 0,
        completed_cases: t.completed_cases || 0,
        progress: t.progress || 0,
        is_correct: t.passed_cases === t.total_cases ? true : t.passed_cases > 0 ? null : false,
        score: t.total_cases > 0 ? t.passed_cases / t.total_cases : null,
        status: t.status,
        comparison_method: suite?.default_comparison_method || 'exact',
        created_at: t.completed_at || t.created_at,
      }
    })
    total.value = taskData.total || 0
    syncPolling()
  } catch (e) {
    ElMessage.error('加载评测结果失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function syncPolling() {
  const hasRunning = results.value.some(t => t.status === 'running' || t.status === 'starting')
  if (hasRunning && !refreshTimer) {
    refreshTimer = window.setInterval(loadResults, 3000)
  } else if (!hasRunning && refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

async function loadSuites() {
  if (!currentSpace.value?.id) return
  try {
    const data = await evalApi.getEvalSuites(currentSpace.value.id, { limit: 1000 })
    suites.value = data.items || data || []
  } catch (e) {
    console.error('加载评测集失败:', e)
  }
}

function handleRowClick(row) {
  selectedResult.value = row
  detailVisible.value = true
}

function formatDate(dateStr) {
  if (!dateStr) return '--'
  return new Date(dateStr).toLocaleString('zh-CN')
}

function getRateClass(score) {
  if (score == null) return ''
  if (score >= 0.8) return 'high'
  if (score >= 0.6) return 'medium'
  return 'low'
}

function getStatusLabel(status) {
  return { completed: '已完成', partial: '部分通过', failed: '失败', cancelled: '已取消', running: '运行中' }[status] || status
}

onMounted(() => {
  onSpaceChange(() => {
    currentPage.value = 1
    filterSuiteId.value = ''
    filterStatus.value = ''
    loadSuites()
    loadResults()
  })
})

watch(
  () => currentSpace.value?.id,
  (spaceId) => {
    if (!spaceId) return
    loadSuites()
    loadResults()
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
.eval-results {
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

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.search-input :deep(.el-input__wrapper) {
  border-radius: 8px;
}

.filter-select :deep(.el-input__wrapper) {
  border-radius: 8px;
}

.results-list {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
}

.results-table :deep(.el-table__header th) {
  background: var(--bg-primary) !important;
  font-weight: 600;
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.pass-rate {
  font-weight: 600;
  font-size: 14px;
}

.pass-rate.high {
  color: #67c23a;
}

.pass-rate.medium {
  color: #e6a23c;
}

.pass-rate.low {
  color: #f56c6c;
}

.case-count {
  font-weight: 500;
  color: var(--text-secondary);
}

.progress-text {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-muted);
}

.status-badge {
  display: inline-flex;
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
}

.status-badge.completed {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.status-badge.partial {
  background: rgba(230, 162, 60, 0.1);
  color: #e6a23c;
}

.status-badge.failed {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.status-badge.running {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.method-tag {
  font-size: 11px;
  font-family: 'SF Mono', 'Consolas', monospace;
  padding: 2px 6px;
  background: var(--bg-primary);
  border-radius: 4px;
  color: var(--text-muted);
}

.date-text {
  font-size: 13px;
  color: var(--text-muted);
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
  margin: 0 0 16px 0;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0;
}

/* 详情抽屉 */
.result-detail {
  padding: 0 4px;
}

.detail-stat-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.detail-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 16px;
  background: var(--bg-primary);
  border-radius: 8px;
  text-align: center;
}

.detail-stat .stat-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-stat .stat-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.detail-section {
  margin-bottom: 16px;
}

.detail-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-content {
  font-size: 14px;
  color: var(--text-primary);
  background: var(--bg-primary);
  padding: 10px 14px;
  border-radius: 6px;
}

.detail-action {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.detail-action .el-button {
  width: 100%;
  border-radius: 8px;
}
</style>
