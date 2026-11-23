<template>
  <div class="knowledge-base-list">
    <PageHeader
      :breadcrumbs="[{ label: '知识中心' }]"
    >
      <template #actions>
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          新建知识库
        </el-button>
        <el-button @click="getKnowledgeBaseList">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </template>
    </PageHeader>

    <div class="card-grid" v-loading="loading" element-loading-text="加载中...">
      <div
        v-for="(item, idx) in knowledgeBaseList"
        :key="item.id"
        class="asset-card kb-card"
        :class="{ 'is-processing': isProcessing(item) }"
        :style="{ animationDelay: `${idx * 60}ms` }"
      >
        <div class="card-accent" />
        <div class="card-body">
          <!-- Top row: icon + status switch + status tag -->
          <div class="card-top">
            <div class="card-icon-wrap">
              <svg class="kb-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                <line x1="12" y1="22.08" x2="12" y2="12"/>
              </svg>
            </div>
            <div class="card-top-right">
              <el-tag
                :type="getVectorizationStatusType(item.vectorization_status)"
                size="small"
                class="status-tag"
                effect="light"
              >
                {{ getVectorizationStatusText(item.vectorization_status) }}
              </el-tag>
              <el-switch
                v-model="item.status"
                size="small"
                @change="handleStatusChange(item)"
                :disabled="isProcessing(item)"
              />
            </div>
          </div>

          <!-- Name -->
          <div class="card-title-row">
            <h3 class="card-title" :title="item.name">{{ item.name }}</h3>
            <el-tooltip
              v-if="item.knowledge_term_dirty || item.sample_library_dirty"
              content="数据已变更，需要重新向量化"
              placement="top"
            >
              <el-icon class="dirty-icon"><Warning /></el-icon>
            </el-tooltip>
          </div>

          <!-- Knowledge access badge -->
          <div class="card-meta">
            <span class="meta-badge" v-if="item.knowledge_access_name">
              <span class="badge-dot" />
              {{ item.knowledge_access_name }}
            </span>
          </div>

          <!-- Description -->
          <p class="card-desc" v-if="item.description">{{ item.description }}</p>
          <p class="card-desc card-desc-empty" v-else>暂无描述</p>

          <!-- Vectorization progress -->
          <div class="card-progress-section" v-if="isProcessing(item)">
            <div class="progress-step-label">{{ getCurrentStepText(item) }}</div>
            <div class="progress-bar-wrap">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="{ width: `${item.vector_progress || 0}%` }"
                />
              </div>
              <span class="progress-pct">{{ item.vector_progress || 0 }}%</span>
            </div>
          </div>
          <div class="card-progress-section completed" v-else-if="item.vectorization_status === 'completed'">
            <el-icon class="completed-check"><CircleCheckFilled /></el-icon>
            <span class="completed-text">{{ getVectorizeStepsDisplay(item) || '向量化完成' }}</span>
          </div>
          <div class="card-progress-section cancelled" v-else-if="item.vectorization_status === 'cancelled'">
            <span class="idle-text">已结束向量化</span>
          </div>
          <div class="card-progress-section failed" v-else-if="item.vectorization_status === 'failed'">
            <span class="failed-text">向量化失败</span>
          </div>
          <div class="card-progress-section idle" v-else>
            <span class="idle-text">待向量化</span>
          </div>

          <!-- Actions -->
          <div class="card-actions">
            <el-button
              v-if="isProcessing(item)"
              size="small"
              class="action-btn action-btn-stop action-grid-main"
              @click="handleCancelVectorization(item)"
              :loading="isCancelling(item)"
            >
              <el-icon><CircleCloseFilled /></el-icon>
              {{ item.vectorization_status === 'cancelling' ? '结束中' : '结束' }}
            </el-button>
            <el-button
              v-else
              size="small"
              class="action-btn action-btn-primary action-grid-main"
              @click="handleVectorize(item)"
            >
              向量化
            </el-button>
            <el-button size="small" class="action-btn action-btn-structure" @click="handleTableStructure(item)" :disabled="isProcessing(item)">
              表结构
            </el-button>
            <el-button size="small" class="action-btn action-btn-structure" @click="handleKnowledgeTerms(item)" :disabled="isProcessing(item)">
              词条
            </el-button>
            <el-button size="small" class="action-btn action-btn-manage" @click="handleEdit(item)" :disabled="isProcessing(item)">
              编辑
            </el-button>
            <el-button size="small" class="action-btn action-btn-danger" @click="handleDelete(item)" :disabled="isProcessing(item)">
              删除
            </el-button>

            <span class="action-grid-placeholder" />
            <el-button size="small" class="action-btn action-btn-structure" @click="handleNer(item)" :disabled="isProcessing(item)">
              NER
            </el-button>
            <el-button size="small" class="action-btn action-btn-structure" @click="handleSampleLibrary(item)" :disabled="isProcessing(item)">
              样例库
            </el-button>
            <el-button size="small" class="action-btn action-btn-manage" @click="handleClone(item)" :disabled="isProcessing(item)">
              克隆
            </el-button>
            <span class="action-grid-placeholder" />
          </div>
        </div>
      </div>

      <div v-if="knowledgeBaseList.length === 0 && !loading" class="empty-state">
        <div class="empty-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          </svg>
        </div>
        <p class="empty-text">暂无知识库</p>
        <p class="empty-hint">创建知识库，将知识接入转化为可搜索的知识资产</p>
      </div>
    </div>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'create' ? '新建知识库' : '编辑知识库'"
      width="600px"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
      >
        <el-form-item label="知识库名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入知识库名称" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="form.description"
            placeholder="请输入知识库描述"
            type="textarea"
            :rows="3"
          />
        </el-form-item>
        <el-form-item label="数据集" prop="knowledge_access_id">
          <el-select v-model="form.knowledge_access_id" placeholder="请选择数据集">
            <el-option
              v-for="item in knowledgeAccessList"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-switch v-model="form.status" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmit">确定</el-button>
        </span>
      </template>
    </el-dialog>

    <!-- 向量化步骤选择对话框 -->
    <el-dialog
      v-model="vectorizeDialogVisible"
      title="选择向量化步骤"
      width="520px"
    >
      <div class="vectorize-select-all">
        <el-checkbox
          v-model="isAllSelected"
          :indeterminate="isIndeterminate"
          @change="handleSelectAll"
        >
          全选
        </el-checkbox>
      </div>
      <div class="vectorize-mode">
        <span class="vectorize-mode-label">向量化方式</span>
        <el-radio-group v-model="vectorizeMode">
          <el-radio-button label="incremental">增量</el-radio-button>
          <el-radio-button label="full">全量</el-radio-button>
        </el-radio-group>
      </div>
      <el-divider style="margin: 0 0 12px 0;" />
      <el-checkbox-group v-model="selectedVectorizeSteps" class="vectorize-step-list">
        <div
          v-for="step in vectorizeSteps"
          :key="step.value"
          class="vectorize-step-item"
          :class="{ 'is-checked': selectedVectorizeSteps.includes(step.value) }"
          @click="toggleStep(step.value)"
        >
          <el-checkbox :label="step.value" @click.stop>
            <span class="step-index">{{ step.index }}.</span>
            {{ step.label }}
          </el-checkbox>
          <el-tooltip
            v-if="step.dirtyKey && currentVectorizeKnowledgeBase?.[step.dirtyKey]"
            content="已变更，需要重新向量化"
            placement="top"
          >
            <el-icon class="vectorize-step-warning"><Warning /></el-icon>
          </el-tooltip>
        </div>
      </el-checkbox-group>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="vectorizeDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmVectorize">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Warning, Refresh, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import knowledgeBaseApi from '@/api/knowledgeBase'
import knowledgeAccessApi from '@/api/knowledgeAccess'

const router = useRouter()

const knowledgeBaseList = ref([])
const loading = ref(false)
let refreshInterval = null
const cancellingVectorizationIds = ref(new Set())
const knowledgeAccessList = ref([])
const dialogVisible = ref(false)
const dialogType = ref('create')
const formRef = ref()
const form = ref({
  name: '',
  description: '',
  knowledge_access_id: null,
  status: true
})
const rules = {
  name: [
    { required: true, message: '请输入知识库名称', trigger: 'blur' },
    { min: 2, max: 100, message: '长度在 2 到 100 个字符', trigger: 'blur' }
  ],
  knowledge_access_id: [
    { required: true, message: '请选择数据集', trigger: 'change' }
  ]
}

const vectorizeDialogVisible = ref(false)
const selectedVectorizeSteps = ref([])
const currentVectorizeKnowledgeBase = ref(null)
const vectorizeMode = ref('incremental')

const stepNameMap = {
  'field_vectorization': '字段向量化',
  'value_vectorization': '值向量化',
  'table_field_to_es': '值存ES',
  'knowledge_term_to_es': '知识词存ES',
  'sample_library_to_es': '样例库向量化'
}

const vectorizeSteps = [
  { value: 'field_vectorization', label: '字段向量化', index: 1 },
  { value: 'value_vectorization', label: '值向量化', index: 2 },
  { value: 'table_field_to_es', label: '值存ES', index: 3 },
  { value: 'knowledge_term_to_es', label: '知识词存ES', index: 4, dirtyKey: 'knowledge_term_dirty' },
  { value: 'sample_library_to_es', label: '样例库向量化', index: 5, dirtyKey: 'sample_library_dirty' },
]

const allStepValues = vectorizeSteps.map(s => s.value)

const isAllSelected = computed({
  get: () => selectedVectorizeSteps.value.length === allStepValues.length,
  set: () => {},
})

const isIndeterminate = computed(() => {
  const count = selectedVectorizeSteps.value.length
  return count > 0 && count < allStepValues.length
})

const handleSelectAll = (val) => {
  selectedVectorizeSteps.value = val ? [...allStepValues] : []
}

const toggleStep = (stepValue) => {
  const idx = selectedVectorizeSteps.value.indexOf(stepValue)
  if (idx >= 0) selectedVectorizeSteps.value.splice(idx, 1)
  else selectedVectorizeSteps.value.push(stepValue)
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}

const getProgressColor = (progress) => {
  if (progress < 30) return '#ff4d4f'
  if (progress < 70) return '#faad14'
  return '#52c41a'
}

const getVectorizationStatusText = (status) => {
  const statusMap = {
    'pending': '待处理',
    'processing': '处理中',
    'cancelling': '结束中',
    'completed': '已完成',
    'failed': '失败',
    'cancelled': '已结束'
  }
  return statusMap[status] || status
}

const getVectorizationStatusType = (status) => {
  const typeMap = {
    'pending': 'info',
    'processing': 'warning',
    'cancelling': 'warning',
    'completed': 'success',
    'failed': 'danger',
    'cancelled': 'info'
  }
  return typeMap[status] || 'info'
}

const isProcessing = (row) => {
  return ['processing', 'cancelling'].includes(row.vectorization_status)
}

const isCancelling = (row) => {
  return row.vectorization_status === 'cancelling' || cancellingVectorizationIds.value.has(row.id)
}

const setCancelling = (id, active) => {
  const next = new Set(cancellingVectorizationIds.value)
  if (active) next.add(id)
  else next.delete(id)
  cancellingVectorizationIds.value = next
}

const handleStatusChange = async (row) => {
  const newStatus = row.status
  const actionText = newStatus ? '启用' : '禁用'

  ElMessageBox.confirm(
    `确定要${actionText}知识库「${row.name}」吗？`,
    '提示',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(async () => {
    try {
      await knowledgeBaseApi.updateKnowledgeBase(row.id, { status: newStatus })
      ElMessage.success(`已${actionText}`)
    } catch (error) {
      row.status = !newStatus
      ElMessage.error('状态更新失败：' + (error.response?.data?.detail || error.message))
    }
  }).catch(() => {
    row.status = !newStatus
  })
}

const getKnowledgeBaseList = async (silent = false) => {
  if (!silent) {
    loading.value = true
  }
  const startTime = Date.now()
  try {
    const [knowledgeBaseResponse, knowledgeAccessResponse] = await Promise.all([
      knowledgeBaseApi.getKnowledgeBaseList(),
      knowledgeAccessApi.getKnowledgeAccessList()
    ])

    const knowledgeAccessMap = new Map()
    knowledgeAccessResponse.forEach(item => {
      knowledgeAccessMap.set(item.id, item.name)
    })

    const knowledgeBasesWithName = knowledgeBaseResponse.map(item => ({
      ...item,
      knowledge_access_name: knowledgeAccessMap.get(item.knowledge_access_id) || '未知'
    }))

    knowledgeBaseList.value = knowledgeBasesWithName
    if (knowledgeBasesWithName.some(isProcessing)) startProgressRefresh()
  } catch (error) {
    ElMessage.error('获取知识库列表失败：' + (error.response?.data?.detail || error.message))
  } finally {
    if (!silent) {
      const elapsedTime = Date.now() - startTime
      const remainingTime = Math.max(0, 1000 - elapsedTime)
      setTimeout(() => { loading.value = false }, remainingTime)
    }
  }
}

const getKnowledgeAccessList = async () => {
  try {
    const response = await knowledgeAccessApi.getKnowledgeAccessList()
    knowledgeAccessList.value = response
  } catch (error) {
    ElMessage.error('获取数据集列表失败：' + (error.response?.data?.detail || error.message))
  }
}

const handleCreate = async () => {
  dialogType.value = 'create'
  form.value = { name: '', description: '', knowledge_access_id: null, status: true }
  if (knowledgeAccessList.value.length === 0) {
    await getKnowledgeAccessList()
  }
  dialogVisible.value = true
}

const handleEdit = (row) => {
  dialogType.value = 'edit'
  form.value = { ...row }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    if (dialogType.value === 'create') {
      await knowledgeBaseApi.createKnowledgeBase(form.value)
      ElMessage.success('创建成功')
    } else {
      await knowledgeBaseApi.updateKnowledgeBase(form.value.id, form.value)
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    getKnowledgeBaseList()
  } catch (error) {
    if (error.name !== 'Error') return
    ElMessage.error('操作失败：' + (error.response?.data?.detail || error.message))
  }
}

const handleDelete = async (row) => {
  try {
    const checkResult = await knowledgeBaseApi.checkAutobiRefs(row.id)
    if (!checkResult.can_delete) {
      const projectNames = checkResult.autobi_projects.map(p => p.name).join('、')
      ElMessageBox.alert(
        `该知识库被以下实验中心项目引用，无法删除：<br/><br/><strong>${projectNames}</strong>`,
        '无法删除',
        { confirmButtonText: '确定', type: 'error', dangerouslyUseHTMLString: true }
      )
      return
    }
    ElMessageBox.confirm('确定要删除该知识库吗？删除后将不可恢复。', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async () => {
      try {
        await knowledgeBaseApi.deleteKnowledgeBase(row.id)
        ElMessage.success('删除成功')
        getKnowledgeBaseList()
      } catch (error) {
        ElMessage.error('删除失败：' + (error.response?.data?.detail || error.message))
      }
    }).catch(() => {})
  } catch (error) {
    ElMessage.error('检查引用关系失败：' + (error.response?.data?.detail || error.message))
  }
}

const handleTableStructure = (row) => {
  router.push({
    path: '/knowledge-base/table-structure',
    query: { knowledgeBaseId: row.id, knowledgeBaseName: row.name }
  })
}

const handleKnowledgeTerms = (row) => {
  router.push({
    path: '/knowledge-base/knowledge-terms',
    query: { knowledgeBaseId: row.id, knowledgeBaseName: row.name }
  })
}


const handleSampleLibrary = (row) => {
  router.push({
    path: '/knowledge-base/sample-library',
    query: { knowledgeBaseId: row.id, knowledgeBaseName: row.name }
  })
}

const handleNer = (row) => {
  router.push({
    path: '/knowledge-base/ner',
    query: { knowledgeBaseId: row.id, knowledgeBaseName: row.name }
  })
}

const handleVectorize = (row) => {
  currentVectorizeKnowledgeBase.value = row
  selectedVectorizeSteps.value = []
  vectorizeMode.value = 'incremental'
  vectorizeDialogVisible.value = true
}

const confirmVectorize = async () => {
  if (selectedVectorizeSteps.value.length === 0) {
    ElMessage.warning('请至少选择一个向量化步骤')
    return
  }

  vectorizeDialogVisible.value = false

  const row = currentVectorizeKnowledgeBase.value
  const steps = {
    field_vectorization: selectedVectorizeSteps.value.includes('field_vectorization'),
    value_vectorization: selectedVectorizeSteps.value.includes('value_vectorization'),
    table_field_to_es: selectedVectorizeSteps.value.includes('table_field_to_es'),
    knowledge_term_to_es: selectedVectorizeSteps.value.includes('knowledge_term_to_es'),
    sample_library_to_es: selectedVectorizeSteps.value.includes('sample_library_to_es')
  }

  try {
    await knowledgeBaseApi.vectorizeKnowledgeBase(row.id, steps, vectorizeMode.value)
    row.vectorization_status = 'processing'
    row.vector_progress = 0
    row.current_vectorization_step = null
    ElMessage.success('向量化任务已开始')
    await getKnowledgeBaseList()
    startProgressRefresh()
  } catch (error) {
    ElMessage.error('向量化失败：' + (error.response?.data?.detail || error.message))
  }
}

const handleCancelVectorization = (row) => {
  ElMessageBox.confirm(
    `确定要结束知识库「${row.name}」当前向量化任务吗？已写入的数据会保留，任务会在下一个检查点停止。`,
    '结束向量化',
    {
      confirmButtonText: '结束任务',
      cancelButtonText: '继续等待',
      type: 'warning'
    }
  ).then(async () => {
    setCancelling(row.id, true)
    try {
      const response = await knowledgeBaseApi.cancelVectorization(row.id)
      row.vectorization_status = response.status || 'cancelling'
      ElMessage.success('已发送结束指令')
      await getKnowledgeBaseList(true)
      startProgressRefresh()
    } catch (error) {
      ElMessage.error('结束向量化失败：' + (error.response?.data?.detail || error.message))
    } finally {
      setCancelling(row.id, false)
    }
  }).catch(() => {})
}

const getCurrentStepText = (row) => {
  if (row.vectorization_status === 'cancelling') return '正在结束，等待当前操作完成'
  if (row.vectorization_status !== 'processing' || !row.current_vectorization_step) {
    return ''
  }
  return stepNameMap[row.current_vectorization_step] || row.current_vectorization_step
}

const getVectorizeStepsDisplay = (row) => {
  if (!row.vectorization_steps) return ''
  try {
    const parsed = typeof row.vectorization_steps === 'string'
      ? JSON.parse(row.vectorization_steps)
      : row.vectorization_steps
    const steps = parsed?.steps && typeof parsed.steps === 'object'
      ? parsed.steps
      : parsed
    if (!steps || typeof steps !== 'object') return ''
    const enabledSteps = vectorizeSteps
      .filter(step => steps[step.value])
      .map(step => step.label)
    return enabledSteps.join(' / ')
  } catch {
    return ''
  }
}

const startProgressRefresh = () => {
  if (refreshInterval) return

  refreshInterval = setInterval(() => {
    const hasProcessing = knowledgeBaseList.value.some(
      item => isProcessing(item)
    )

    if (hasProcessing) {
      getKnowledgeBaseList(true)
    } else {
      stopProgressRefresh()
    }
  }, 3000)
}

const stopProgressRefresh = () => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

const handleClone = (row) => {
  ElMessageBox.confirm('确定要克隆该知识库吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'info'
  }).then(async () => {
    try {
      await knowledgeBaseApi.cloneKnowledgeBase(row.id)
      ElMessage.success('克隆成功')
      getKnowledgeBaseList()
    } catch (error) {
      ElMessage.error('克隆失败：' + (error.response?.data?.detail || error.message))
    }
  }).catch(() => {})
}

onMounted(async () => {
  await Promise.all([getKnowledgeBaseList(), getKnowledgeAccessList()])
  startProgressRefresh()
})

onUnmounted(() => {
  stopProgressRefresh()
})
</script>

<style scoped>
.knowledge-base-list {
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

.asset-card.is-processing {
  box-shadow: var(--card-shadow-active), 0 0 0 1px rgba(31, 184, 204, 0.15);
}

.card-accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
}

.kb-card .card-accent {
  background: linear-gradient(180deg, var(--el-color-primary) 0%, var(--el-color-primary-light-3) 100%);
}

.kb-card.is-processing .card-accent {
  background: linear-gradient(180deg, var(--el-color-primary) 0%, var(--el-color-primary-light-3) 50%, var(--el-color-primary) 100%);
  background-size: 100% 200%;
  animation: shimmer 2s ease infinite;
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

.card-top-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}

.kb-icon {
  color: var(--el-color-primary);
}

.status-tag {
  font-size: 11px;
  font-weight: 600;
}

/* Title */
.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
  flex: 1;
}

.dirty-icon {
  color: #e6a23c;
  font-size: 16px;
  flex-shrink: 0;
}

/* Metadata */
.card-meta {
  margin-bottom: 10px;
}

.meta-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 20px;
  font-size: 12px;
  color: var(--el-color-primary);
  font-weight: 500;
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-primary);
  flex-shrink: 0;
}

/* Description */
.card-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0 0 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-desc-empty {
  color: var(--text-muted);
  font-style: italic;
}

/* Progress section */
.card-progress-section {
  margin-bottom: 14px;
  padding: 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
}

.card-progress-section.completed {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
}

.card-progress-section.idle {
  background: var(--bg-primary);
  border: 1px dashed var(--border-color);
  text-align: center;
}

.progress-step-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary);
  margin-bottom: 8px;
}

.progress-bar-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--el-color-primary), var(--el-color-primary-light-3));
  border-radius: 3px;
  transition: width 0.6s ease;
}

.progress-pct {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.completed-check {
  color: var(--el-color-primary);
  font-size: 16px;
}

.completed-text {
  font-size: 12px;
  color: var(--el-color-primary-dark-2);
  font-weight: 500;
}

.idle-text {
  font-size: 12px;
  color: var(--text-muted);
}

/* Action buttons */
.card-actions {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  padding: 4px;
  border: 1px solid var(--border-color-light);
  border-radius: var(--radius-sm);
  background: var(--bg-primary);
}

.action-grid-main {
  font-weight: 600;
}

.action-grid-placeholder {
  min-height: 30px;
}

.action-btn {
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  padding: 5px 0;
  width: 100%;
  height: 30px;
  border: 1px solid var(--border-color);
  background: var(--bg-surface);
  color: var(--text-secondary);
  transition: all 0.2s ease;
  text-align: center;
}

:deep(.card-actions .el-button + .el-button) {
  margin-left: 0;
}

.action-btn:hover:not(:disabled) {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
}

.action-btn-primary {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
}

.action-btn-primary:hover:not(:disabled) {
  background: var(--el-color-primary);
  color: #fff;
  border-color: var(--el-color-primary);
}

.action-btn-structure {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
}

.action-btn-structure:hover:not(:disabled) {
  color: var(--el-color-primary-dark-2);
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-8);
}

.action-btn-manage {
  color: var(--el-color-primary-dark-2);
  border-color: var(--el-color-primary-light-7);
  background: var(--el-color-primary-light-9);
}

.action-btn-manage:hover:not(:disabled) {
  color: var(--el-color-primary-dark-2);
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-8);
}

.failed-text {
  font-size: 12px;
  color: #dc2626;
  font-weight: 500;
}

.action-btn-danger:hover:not(:disabled) {
  color: #dc2626;
  border-color: #fecaca;
  background: #fef2f2;
}

.action-btn-stop {
  color: #dc2626;
  border-color: #fecaca;
  background: #fff7f7;
  font-weight: 600;
}

.action-btn-stop:hover:not(:disabled) {
  color: #fff;
  border-color: #dc2626;
  background: #dc2626;
}

@media (max-width: 680px) {
  .card-actions {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .action-grid-placeholder {
    display: none;
  }
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

@keyframes shimmer {
  0%   { background-position: 0% 0%; }
  50%  { background-position: 0% 100%; }
  100% { background-position: 0% 0%; }
}

/* Vectorize dialog styles */
.vectorize-select-all {
  display: flex;
  align-items: center;
  padding-bottom: 8px;
}

.vectorize-mode {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0 12px;
}

.vectorize-mode-label {
  color: var(--text-secondary);
  font-size: 14px;
}

.vectorize-step-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.vectorize-step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: #fafafa;
  cursor: pointer;
  transition: all 0.2s;
}

.vectorize-step-item:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.vectorize-step-item.is-checked {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.step-index {
  font-weight: 600;
  color: var(--el-color-primary);
  margin-right: 2px;
}

.vectorize-step-warning {
  color: #e6a23c;
  font-size: 16px;
  margin-left: auto;
}

.dialog-footer {
  text-align: right;
}
</style>
