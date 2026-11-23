<template>
  <div class="knowledge-access-list">
    <PageHeader
      :breadcrumbs="[{ label: '知识引擎' }]"
    >
      <template #actions>
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          新建数据集
        </el-button>
        <el-button @click="getKnowledgeAccessList">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </template>
    </PageHeader>

    <div class="card-grid" v-loading="loading" element-loading-text="加载中...">
      <div
        v-for="(item, idx) in knowledgeAccessList"
        :key="item.id"
        class="asset-card ka-card"
        :style="{ animationDelay: `${idx * 60}ms` }"
      >
        <div class="card-accent" />
        <div class="card-body">
          <div class="card-top">
            <div class="card-icon-wrap">
              <svg class="ka-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
            </div>
            <el-button type="danger" size="small" link class="card-delete-btn" @click="handleDelete(item)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>

          <h3 class="card-title" :title="item.name">{{ item.name }}</h3>

          <div class="card-meta">
            <span class="meta-badge" v-if="item.data_source_name">
              <span class="badge-dot" />
              {{ item.data_source_name }}
            </span>
          </div>

          <p class="card-desc" v-if="item.description">{{ item.description }}</p>
          <p class="card-desc card-desc-empty" v-else>暂无描述</p>

          <div class="card-actions">
            <el-button size="small" class="action-btn" @click="handleTableStructure(item)">
              表结构配置
            </el-button>
            <el-button size="small" class="action-btn" @click="handleKnowledgeTerm(item)">
              知识词条
            </el-button>
            <el-button size="small" class="action-btn" @click="handleSampleLibrary(item)">
              样例库
            </el-button>
          </div>

          <div class="card-footer-row">
            <span class="card-time" v-if="item.updated_at">
              <el-icon class="time-icon"><Clock /></el-icon>
              {{ formatDate(item.updated_at) }}
            </span>
            <span class="card-id">#{{ item.id }}</span>
          </div>
        </div>
      </div>

      <div v-if="knowledgeAccessList.length === 0 && !loading" class="empty-state">
        <div class="empty-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <p class="empty-text">暂无数据集</p>
        <p class="empty-hint">创建数据集，将数据源连接到知识系统</p>
      </div>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'create' ? '新建数据集' : '编辑数据集'"
      width="500px"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="80px"
      >
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入数据集名称" />
        </el-form-item>
        <el-form-item label="数据源" prop="data_source_id">
          <el-select
            v-model="form.data_source_id"
            placeholder="请选择数据源"
            style="width: 100%"
          >
            <el-option
              v-for="item in dataSourceList"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            placeholder="请输入描述信息"
            :rows="3"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Delete, Clock } from '@element-plus/icons-vue'
import knowledgeAccessApi from '@/api/knowledgeAccess'
import dataSourceApi from '@/api/dataSource'

const router = useRouter()

const knowledgeAccessList = ref([])
const loading = ref(false)
const dataSourceList = ref([])
const dialogVisible = ref(false)
const dialogType = ref('create')
const formRef = ref()
const form = ref({
  name: '',
  description: '',
  data_source_id: null
})
const rules = {
  name: [
    { required: true, message: '请输入数据集名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  data_source_id: [
    { required: true, message: '请选择数据源', trigger: 'change' }
  ]
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}

const getKnowledgeAccessList = async () => {
  loading.value = true
  const startTime = Date.now()
  try {
    const response = await knowledgeAccessApi.getKnowledgeAccessList()
    knowledgeAccessList.value = response
  } catch (error) {
    ElMessage.error('获取数据集列表失败：' + (error.response?.data?.detail || error.message))
  } finally {
    const elapsedTime = Date.now() - startTime
    const remainingTime = Math.max(0, 1000 - elapsedTime)
    setTimeout(() => { loading.value = false }, remainingTime)
  }
}

const handleCreate = () => {
  dialogType.value = 'create'
  form.value = { name: '', description: '', data_source_id: null }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    if (dialogType.value === 'create') {
      await knowledgeAccessApi.createKnowledgeAccess(form.value)
      ElMessage.success('创建成功')
    } else {
      await knowledgeAccessApi.updateKnowledgeAccess(form.value.id, form.value)
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    getKnowledgeAccessList()
  } catch (error) {
    if (error.name !== 'Error') return
    ElMessage.error('操作失败：' + (error.response?.data?.detail || error.message))
  }
}

const handleTableStructure = (row) => {
  router.push({ name: 'TableStructureConfig', params: { id: row.id } })
}

const handleKnowledgeTerm = (row) => {
  router.push({ name: 'KnowledgeTerm', params: { id: row.id } })
}

const handleSampleLibrary = (row) => {
  router.push({ name: 'SampleLibrary', params: { id: row.id } })
}

const handleDelete = async (row) => {
  try {
    const checkResult = await knowledgeAccessApi.checkKbRefs(row.id)
    if (!checkResult.can_delete) {
      const kbInfo = checkResult.knowledge_bases.map(kb => {
        const desc = kb.description ? ` (${kb.description})` : ''
        return `<strong>${kb.name}</strong>${desc}`
      }).join('<br/>')
      ElMessageBox.alert(
        `该数据集被以下知识库引用，无法删除：<br/><br/>${kbInfo}`,
        '无法删除',
        { confirmButtonText: '确定', type: 'error', dangerouslyUseHTMLString: true }
      )
      return
    }
    ElMessageBox.confirm('确定要删除该数据集吗？删除后将不可恢复。', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async () => {
      try {
        await knowledgeAccessApi.deleteKnowledgeAccess(row.id)
        ElMessage.success('删除成功')
        getKnowledgeAccessList()
      } catch (error) {
        ElMessage.error('删除失败：' + (error.response?.data?.detail || error.message))
      }
    }).catch(() => {})
  } catch (error) {
    ElMessage.error('检查引用关系失败：' + (error.response?.data?.detail || error.message))
  }
}

const getDataSourceList = async () => {
  try {
    const response = await dataSourceApi.getDataSourceList()
    dataSourceList.value = response
  } catch (error) {
    ElMessage.error('获取数据源列表失败：' + (error.response?.data?.detail || error.message))
  }
}

onMounted(() => {
  getKnowledgeAccessList()
  getDataSourceList()
})
</script>

<style scoped>
.knowledge-access-list {
  max-width: 1440px;
}

.create-btn {
  border-radius: var(--radius-sm);
  font-weight: 600;
  padding: 8px 20px;
  height: 38px;
}

.refresh-btn {
  border-radius: var(--radius-sm);
  padding: 8px 12px;
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

.ka-card .card-accent {
  background: linear-gradient(180deg, var(--color-cyan) 0%, #22d3ee 100%);
}

.card-body {
  padding: 20px 20px 16px 24px;
}

/* Top row */
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--color-cyan-bg);
}

.ka-icon {
  color: var(--color-cyan);
}

.card-delete-btn {
  opacity: 0;
  transition: opacity 0.2s ease;
  padding: 4px;
}

.asset-card:hover .card-delete-btn {
  opacity: 1;
}

/* Card title */
.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
}

/* Metadata badges */
.card-meta {
  margin-bottom: 10px;
}

.meta-badge {
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

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-cyan);
  flex-shrink: 0;
}

/* Description */
.card-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 14px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-desc-empty {
  color: var(--text-muted);
  font-style: italic;
}

/* Action buttons */
.card-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.action-btn {
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  padding: 5px 14px;
  height: 30px;
  border: 1px solid var(--border-color);
  background: var(--bg-surface);
  color: var(--text-secondary);
  transition: all 0.2s ease;
}

.action-btn:hover {
  color: var(--color-cyan);
  border-color: var(--color-cyan-border);
  background: var(--color-cyan-bg);
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
