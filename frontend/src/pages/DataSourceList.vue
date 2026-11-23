<template>
  <div class="data-source-list">
    <PageHeader
      :breadcrumbs="[{ label: '数据中心' }]"
    >
      <template #actions>
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          新建数据源
        </el-button>
      </template>
    </PageHeader>

    <div class="card-grid" v-loading="false">
      <div
        v-for="(item, idx) in dataSourceList"
        :key="item.id"
        class="asset-card ds-card"
        :style="{ animationDelay: `${idx * 60}ms` }"
      >
        <div class="card-accent" />
        <div class="card-body">
          <div class="card-top">
            <div class="card-type-badge" :class="`type-${item.database_type}`">
              <span class="type-icon">{{ getDbTypeIcon(item.database_type) }}</span>
              <span class="type-label">{{ item.database_type || 'DB' }}</span>
            </div>
            <div class="card-actions-top">
              <el-button type="primary" size="small" link @click="handleEdit(item)">编辑</el-button>
              <el-button type="danger" size="small" link @click="handleDelete(item)">删除</el-button>
            </div>
          </div>

          <h3 class="card-title" :title="item.name">{{ item.name }}</h3>

          <div class="card-meta">
            <span class="meta-pill" v-if="item.host">
              <span class="pill-dot host-dot" />
              {{ item.host }}:{{ item.port }}
            </span>
            <span class="meta-pill" v-if="item.username">
              <span class="pill-icon">@</span>
              {{ item.username }}
            </span>
            <span class="meta-pill" v-if="item.default_database">
              <span class="pill-icon">DB</span>
              {{ item.default_database }}
            </span>
          </div>

          <div class="card-footer-row">
            <span class="card-time" v-if="item.created_at">
              <el-icon class="time-icon"><Calendar /></el-icon>
              {{ formatDate(item.created_at) }}
            </span>
            <el-button type="primary" link @click="querySource = item; queryVisible = true">数据查询</el-button>
            <span class="card-id">#{{ item.id }}</span>
          </div>
        </div>
      </div>

      <div v-if="dataSourceList.length === 0" class="empty-state">
        <div class="empty-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
            <ellipse cx="12" cy="6" rx="8" ry="3"/>
            <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6"/>
            <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/>
          </svg>
        </div>
        <p class="empty-text">暂无数据源</p>
        <p class="empty-hint">点击上方按钮创建第一个数据库连接</p>
      </div>
    </div>

    <DataSourceQueryDialog v-model="queryVisible" :source="querySource" />

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'create' ? '新建数据源' : '编辑数据源'"
      width="600px"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-form-item label="数据源名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入数据源名称" />
        </el-form-item>
        <el-form-item label="数据库类型" prop="database_type">
          <el-select v-model="form.database_type" placeholder="请选择数据库类型">
            <el-option label="MySQL" value="mysql" />
            <el-option label="PostgreSQL" value="postgresql" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据库地址" prop="host">
          <el-input v-model="form.host" placeholder="请输入数据库地址" />
        </el-form-item>
        <el-form-item label="端口号" prop="port">
          <el-input-number
            v-model="form.port"
            :min="1"
            :max="65535"
            :step="1"
            placeholder="请输入端口号"
          />
        </el-form-item>
        <el-form-item label="账号" prop="username">
          <el-input v-model="form.username" placeholder="请输入数据库账号" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入数据库密码"
            :show-password="showPasswordToggle"
            :style="!showPasswordToggle ? 'user-select:none' : ''"
            @copy="!showPasswordToggle ? $event.preventDefault() : null"
          />
        </el-form-item>
        <el-form-item label="默认数据库" prop="default_database">
          <el-input v-model="form.default_database" placeholder="请输入默认数据库名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button :loading="testingConnection" @click="handleTestConnection">测试连接</el-button>
          <el-button type="primary" @click="handleSubmit">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Calendar } from '@element-plus/icons-vue'
import dataSourceApi from '@/api/dataSource'
import DataSourceQueryDialog from '@/components/DataSourceQueryDialog.vue'
import { isAuthenticated } from '@/utils/auth'
import { decryptPassword } from '@/utils/crypto'

const dataSourceList = ref([])
const querySource = ref(null), queryVisible = ref(false)
const dialogVisible = ref(false)
const dialogType = ref('create')
const formRef = ref()
const testingConnection = ref(false)
const form = ref({
  name: '',
  database_type: '',
  host: '',
  port: null,
  username: '',
  password: '',
  default_database: ''
})
const rules = {
  name: [
    { required: true, message: '请输入数据源名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  database_type: [
    { required: true, message: '请选择数据库类型', trigger: 'change' }
  ],
  host: [
    { required: true, message: '请输入数据库地址', trigger: 'blur' }
  ],
  port: [
    { required: true, message: '请输入端口号', trigger: 'blur' },
    { type: 'number', min: 1, max: 65535, message: '端口号范围在 1 到 65535', trigger: 'blur' }
  ],
  username: [
    { required: true, message: '请输入数据库账号', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入数据库密码', trigger: 'blur' }
  ],
  default_database: [
    { required: true, message: '请输入默认数据库名称', trigger: 'blur' }
  ]
}

const dbTypeIcons = {
  mysql: 'MY',
  postgresql: 'PG',
  sqlserver: 'MS',
  oracle: 'OR',
  mongodb: 'MG',
  redis: 'RD'
}

const getDbTypeIcon = (type) => dbTypeIcons[type] || 'DB'

const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}

const getDataSourceList = async () => {
  try {
    const response = await dataSourceApi.getDataSourceList()
    dataSourceList.value = response
  } catch (error) {
    ElMessage.error('获取数据源列表失败：' + (error.response?.data?.detail || error.message))
  }
}

const showPasswordToggle = computed(() => {
  return isAuthenticated() && dialogType.value === 'edit'
})

const handleCreate = () => {
  dialogType.value = 'create'
  form.value = {
    name: '',
    database_type: '',
    host: '',
    port: null,
    username: '',
    password: '',
    default_database: ''
  }
  dialogVisible.value = true
}

const handleEdit = async (row) => {
  dialogType.value = 'edit'
  form.value = { ...row, password: '' }
  dialogVisible.value = true
  if (isAuthenticated() && row.password) {
    try {
      form.value.password = await decryptPassword(row.password)
    } catch {}
  }
}

const handleTestConnection = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  testingConnection.value = true
  try {
    const res = await dataSourceApi.testConnection(form.value)
    if (res.success) {
      ElMessage.success(res.message || '连接成功')
    } else {
      ElMessage.error(res.message || '连接失败')
    }
  } catch (error) {
    ElMessage.error('测试失败：' + (error.response?.data?.detail || error.message))
  } finally {
    testingConnection.value = false
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    if (dialogType.value === 'create') {
      await dataSourceApi.createDataSource(form.value)
      ElMessage.success('创建成功')
    } else {
      await dataSourceApi.updateDataSource(form.value.id, form.value)
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    getDataSourceList()
  } catch (error) {
    if (error.name !== 'Error') return
    ElMessage.error('操作失败：' + (error.response?.data?.detail || error.message))
  }
}

const handleDelete = async (row) => {
  try {
    const checkResult = await dataSourceApi.checkKaRefs(row.id)
    if (!checkResult.can_delete) {
      const kaInfo = checkResult.knowledge_accesses.map(ka => {
        const desc = ka.description ? ` (${ka.description})` : ''
        return `<strong>${ka.name}</strong>${desc}`
      }).join('<br/>')
      ElMessageBox.alert(
        `该数据源被以下知识接入引用，无法删除：<br/><br/>${kaInfo}`,
        '无法删除',
        { confirmButtonText: '确定', type: 'error', dangerouslyUseHTMLString: true }
      )
      return
    }
    ElMessageBox.confirm('确定要删除该数据源吗？删除后将不可恢复。', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async () => {
      try {
        await dataSourceApi.deleteDataSource(row.id)
        ElMessage.success('删除成功')
        getDataSourceList()
      } catch (error) {
        ElMessage.error('删除失败：' + (error.response?.data?.detail || error.message))
      }
    }).catch(() => {})
  } catch (error) {
    ElMessage.error('检查引用关系失败：' + (error.response?.data?.detail || error.message))
  }
}

onMounted(() => {
  getDataSourceList()
})
</script>

<style scoped>
.data-source-list {
  max-width: 1440px;
}

.create-btn {
  border-radius: var(--radius-sm);
  font-weight: 600;
  padding: 8px 20px;
  height: 38px;
}

/* Card grid */
.card-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

@media (min-width: 1500px) {
  .card-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 900px) {
  .card-grid { grid-template-columns: 1fr; }
}

/* Asset card */
.asset-card {
  position: relative;
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  box-shadow: var(--card-shadow);
  overflow: hidden;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
  animation: cardFadeIn 0.4s ease both;
  cursor: default;
}

.asset-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--card-shadow-hover);
}

.card-accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
}

.ds-card .card-accent {
  background: linear-gradient(180deg, var(--color-amber) 0%, #f59e0b 100%);
}

.card-body {
  padding: 20px 20px 16px 24px;
}

/* Top row: type badge + actions */
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-type-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  background: var(--color-cyan-bg);
  border: 1px solid var(--color-cyan-border);
  border-radius: 20px;
  font-size: 12px;
  color: var(--color-cyan);
  font-weight: 500;
}

.type-icon {
  font-size: 12px;
}

.card-actions-top {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.asset-card:hover .card-actions-top {
  opacity: 1;
}

/* Card title */
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
}

/* Metadata pills */
.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}

.meta-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  background: var(--color-cyan-bg);
  border: 1px solid var(--color-cyan-border);
  border-radius: 20px;
  font-size: 12px;
  color: var(--color-cyan);
  font-weight: 500;
  white-space: nowrap;
}

.pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-cyan);
  flex-shrink: 0;
}

.host-dot {
  background: var(--color-cyan);
  box-shadow: 0 0 0 2px rgba(8, 145, 178, 0.2);
}

.pill-icon {
  font-size: 9px;
  font-weight: 700;
  color: var(--color-cyan);
  text-transform: uppercase;
}

/* Footer */
.card-footer-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-time {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-muted);
}

.time-icon {
  font-size: 13px;
}

.card-id {
  font-size: 11px;
  color: var(--text-muted);
  font-family: 'SF Mono', 'Fira Code', monospace;
}

/* Empty state */
.empty-state {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 20px;
  color: var(--text-muted);
}

.empty-icon {
  margin-bottom: 16px;
  opacity: 0.3;
}

.empty-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0 0 6px;
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

/* Animations */
@keyframes cardFadeIn {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}

.dialog-footer {
  text-align: right;
}
</style>
