<template>
  <div class="audit-log-page">
    <PageHeader
      :breadcrumbs="[{ label: '管理中心' }, { label: '审计日志' }]"
    />

    <!-- 筛选条件 -->
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" size="default">
        <el-form-item label="用户ID">
          <el-input v-model="filters.user_id" placeholder="用户ID" clearable style="width:120px" />
        </el-form-item>
        <el-form-item label="操作类型">
          <el-select v-model="filters.action" placeholder="全部" clearable style="width:120px">
            <el-option label="登录" value="login" />
            <el-option label="创建" value="create" />
            <el-option label="更新" value="update" />
            <el-option label="删除" value="delete" />
            <el-option label="导出" value="export" />
          </el-select>
        </el-form-item>
        <el-form-item label="资源类型">
          <el-select v-model="filters.resource_type" placeholder="全部" clearable style="width:140px">
            <el-option label="用户" value="user" />
            <el-option label="空间" value="space" />
            <el-option label="知识库" value="knowledge_base" />
            <el-option label="工作流" value="agent_app" />
            <el-option label="AutoBI" value="autobi" />
            <el-option label="数据源" value="data_source" />
          </el-select>
        </el-form-item>
        <el-form-item label="空间ID">
          <el-input v-model="filters.space_id" placeholder="空间ID" clearable style="width:100px" />
        </el-form-item>
        <el-form-item label="状态码">
          <el-input v-model="filters.status_code" placeholder="例: 200/404/500" clearable style="width:130px" />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width:360px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadLogs">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 日志列表 -->
    <el-card shadow="never" class="table-card" v-loading="loading">
      <el-table :data="logList" stripe style="width: 100%" @row-click="showDetail">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户" width="100">
          <template #default="scope">
            {{ scope.row.username || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="method" label="方法" width="70">
          <template #default="scope">
            <el-tag :type="getMethodTagType(scope.row.method)" size="small">
              {{ scope.row.method }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="path" label="请求路径" min-width="280" show-overflow-tooltip />
        <el-table-column prop="action" label="操作" width="80">
          <template #default="scope">
            <el-tag v-if="scope.row.action" size="small" type="info">{{ scope.row.action }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="资源类型" width="100">
          <template #default="scope">
            {{ scope.row.resource_type || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="status_code" label="状态码" width="80">
          <template #default="scope">
            <el-tag :type="getStatusTagType(scope.row.status_code)" size="small">
              {{ scope.row.status_code || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP地址" width="130">
          <template #default="scope">
            {{ scope.row.ip_address || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时(ms)" width="90">
          <template #default="scope">
            {{ scope.row.duration_ms ?? '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadLogs"
          @current-change="loadLogs"
        />
      </div>
    </el-card>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="日志详情" width="700px" destroy-on-close>
      <el-descriptions :column="2" border v-if="currentLog">
        <el-descriptions-item label="ID">{{ currentLog.id }}</el-descriptions-item>
        <el-descriptions-item label="用户">{{ currentLog.username || '-' }} (ID: {{ currentLog.user_id || '-' }})</el-descriptions-item>
        <el-descriptions-item label="方法">{{ currentLog.method }}</el-descriptions-item>
        <el-descriptions-item label="状态码">{{ currentLog.status_code || '-' }}</el-descriptions-item>
        <el-descriptions-item label="请求路径" :span="2">{{ currentLog.path }}</el-descriptions-item>
        <el-descriptions-item label="操作类型">{{ currentLog.action || '-' }}</el-descriptions-item>
        <el-descriptions-item label="资源类型">{{ currentLog.resource_type || '-' }}</el-descriptions-item>
        <el-descriptions-item label="资源ID">{{ currentLog.resource_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="资源名称">{{ currentLog.resource_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="空间ID">{{ currentLog.space_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="IP地址">{{ currentLog.ip_address || '-' }}</el-descriptions-item>
        <el-descriptions-item label="耗时">{{ currentLog.duration_ms ?? '-' }} ms</el-descriptions-item>
        <el-descriptions-item label="时间">{{ formatDate(currentLog.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="请求体" :span="2">
          <pre class="log-pre">{{ formatJson(currentLog.request_body) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="响应体" :span="2">
          <pre class="log-pre">{{ formatJson(currentLog.response_body) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="错误信息" :span="2" v-if="currentLog.error_message">
          <pre class="log-pre error">{{ currentLog.error_message }}</pre>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Document, Search } from '@element-plus/icons-vue'
import { getAuditLogs, getAuditLog } from '@/api/auditLog'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const logList = ref([])
const detailVisible = ref(false)
const currentLog = ref(null)

const filters = reactive({
  user_id: '',
  action: '',
  resource_type: '',
  space_id: '',
  status_code: '',
  timeRange: null,
})

const pagination = reactive({
  page: 1,
  pageSize: 50,
  total: 0,
})

async function loadLogs() {
  loading.value = true
  try {
    const params = {
      skip: (pagination.page - 1) * pagination.pageSize,
      limit: pagination.pageSize,
    }
    if (filters.user_id) params.user_id = parseInt(filters.user_id)
    if (filters.action) params.action = filters.action
    if (filters.resource_type) params.resource_type = filters.resource_type
    if (filters.space_id) params.space_id = parseInt(filters.space_id)
    if (filters.status_code) params.status_code = parseInt(filters.status_code)
    if (filters.timeRange && filters.timeRange.length === 2) {
      params.start_time = filters.timeRange[0]
      params.end_time = filters.timeRange[1]
    }

    const res = await getAuditLogs(params)
    logList.value = res.logs || []
    pagination.total = res.total || 0
  } catch (e) {
    ElMessage.error('加载审计日志失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.user_id = ''
  filters.action = ''
  filters.resource_type = ''
  filters.space_id = ''
  filters.status_code = ''
  filters.timeRange = null
  pagination.page = 1
  loadLogs()
}

async function showDetail(row) {
  try {
    const detail = await getAuditLog(row.id)
    currentLog.value = detail
    detailVisible.value = true
  } catch {
    currentLog.value = row
    detailVisible.value = true
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function formatJson(str) {
  if (!str) return '-'
  try {
    return JSON.stringify(JSON.parse(str), null, 2)
  } catch {
    return str
  }
}

function getMethodTagType(method) {
  const map = { GET: 'info', POST: 'success', PUT: 'warning', DELETE: 'danger', PATCH: 'warning' }
  return map[method] || 'info'
}

function getStatusTagType(code) {
  if (!code) return 'info'
  if (code >= 200 && code < 300) return 'success'
  if (code >= 400 && code < 500) return 'warning'
  if (code >= 500) return 'danger'
  return 'info'
}

onMounted(() => {
  loadLogs()
})
</script>

<style scoped>
.audit-log-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.filter-card :deep(.el-card__body) {
  padding: 16px 16px 0;
}

.table-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.table-card :deep(.el-card__body) {
  flex: 1;
  overflow: auto;
  padding: 0;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  padding: 16px;
}

.log-pre {
  margin: 0;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-pre.error {
  background: #fef0f0;
  color: #f56c6c;
}

:deep(.el-table) {
  cursor: pointer;
}
</style>
