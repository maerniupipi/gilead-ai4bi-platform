<template>
  <div class="trace-lookup-page">
    <header class="trace-lookup-head">
      <h2 class="trace-lookup-title">运行日志</h2>
      <p class="trace-lookup-desc">
        查看工作流与实验室的执行历史。输入 trace_id 直接跳转详情，或通过下方列表搜索过滤。
      </p>
    </header>

    <!-- 快速查找 -->
    <el-card shadow="never" class="trace-lookup-card">
      <div class="trace-lookup-input-row">
        <el-input
          v-model="traceIdInput"
          placeholder="粘贴 trace_id，例如 550e8400-e29b-41d4-a716-446655440000"
          clearable
          class="trace-lookup-input"
          @keyup.enter="goView"
        />
        <el-button type="primary" @click="goView">查看详情</el-button>
      </div>
    </el-card>

    <!-- 搜索与筛选 -->
    <el-card shadow="never" class="trace-lookup-card">
      <div class="trace-filter-row">
        <el-input
          v-model="filters.keyword"
          placeholder="搜索 trace_id / 应用名"
          clearable
          style="width: 240px"
          @keyup.enter="search"
        />
        <el-select
          v-model="filters.status"
          placeholder="状态"
          clearable
          style="width: 120px"
          @change="search"
        >
          <el-option label="运行中" value="running" />
          <el-option label="已完成" value="done" />
          <el-option label="失败" value="error" />
        </el-select>
        <el-date-picker
          v-model="filters.dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          style="width: 260px"
          @change="search"
        />
        <el-button type="primary" @click="search">搜索</el-button>
      </div>

      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
        class="trace-table"
        empty-text="暂无运行记录"
      >
        <el-table-column label="Trace ID" min-width="200">
          <template #default="{ row }">
            <code class="trace-id-cell">{{ row.trace_id }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="app_name" label="应用名" min-width="140" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">
            <span v-if="row.elapsed_ms != null">{{ row.elapsed_ms }}ms</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">
            <span class="time-cell">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="goViewId(row.trace_id)">
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="trace-pagination">
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.limit"
          :total="pagination.total"
          layout="prev, pager, next"
          @current-change="loadList"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listTraces } from '../../api/workflowTrace'

const router = useRouter()
const traceIdInput = ref('')
const loading = ref(false)
const tableData = ref([])

const filters = reactive({
  keyword: '',
  status: '',
  dateRange: null
})

const pagination = reactive({
  page: 1,
  limit: 20,
  total: 0
})

function goView() {
  const id = traceIdInput.value.trim()
  if (!id) {
    ElMessage.warning('请输入追踪 ID')
    return
  }
  router.push({ name: 'AgentTraceView', params: { traceId: id } })
}

function goViewId(id) {
  router.push({ name: 'AgentTraceView', params: { traceId: id } })
}

function statusTag(s) {
  if (s === 'done') return 'success'
  if (s === 'error') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}

function statusText(s) {
  if (s === 'done') return '已完成'
  if (s === 'error') return '失败'
  if (s === 'running') return '运行中'
  return s || '-'
}

function formatTime(ms) {
  if (ms == null) return ''
  const d = new Date(ms)
  return d.toLocaleString()
}

function search() {
  pagination.page = 1
  loadList()
}

async function loadList() {
  loading.value = true
  try {
    const params = {
      skip: (pagination.page - 1) * pagination.limit,
      limit: pagination.limit
    }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.status) params.status = filters.status
    if (filters.dateRange && filters.dateRange.length === 2) {
      params.date_from = filters.dateRange[0]
      params.date_to = filters.dateRange[1]
    }
    const res = await listTraces(params)
    tableData.value = res.items || []
    pagination.total = res.total || 0
  } catch (e) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

loadList()
</script>

<style scoped>
.trace-lookup-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  padding: 20px 24px;
}

.trace-lookup-head {
  margin-bottom: 4px;
}

.trace-lookup-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.trace-lookup-desc {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.trace-lookup-card {
  border-radius: 8px;
}

.trace-lookup-input-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.trace-lookup-input {
  max-width: 480px;
  flex: 1;
}

.trace-filter-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.trace-table {
  margin-bottom: 12px;
}

.trace-id-cell {
  font-size: 12px;
  word-break: break-all;
}

.time-cell {
  font-size: 12px;
  color: #909399;
}

.trace-pagination {
  display: flex;
  justify-content: flex-end;
}
</style>
