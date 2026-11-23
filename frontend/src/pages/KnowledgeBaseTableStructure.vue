<template>
  <div class="knowledge-base-table-structure">
    <PageHeader
      :breadcrumbs="[{ label: '知识库列表', to: '/knowledge-base' }, { label: `表结构配置 — ${knowledgeBaseName}` }]"
    />
    
    <!-- 表结构列表 - 左右结构 -->
    <el-card shadow="never" v-if="kbTableStructures.length > 0">
      <template #header>
        <div class="card-header">
          <span>已选择的表结构</span>
          <div>
            <el-button :loading="refreshing" @click="getKbTableStructures()">刷新状态</el-button>
            <el-button type="primary" @click="handleSelectTables">
              <el-icon><Select /></el-icon>
              选择表结构
            </el-button>
          </div>
        </div>
      </template>
      
      <el-alert
        v-if="vectorizationStatus === 'failed'"
        title="本次向量化未完成，请在知识库列表重新启动向量化。"
        type="error"
        show-icon
        :closable="false"
        style="margin-bottom: 16px"
      />
      <div class="table-field-container">
        <!-- 左侧表名列表 -->
        <div class="table-list-panel">
          <div class="table-list">
            <div
              v-for="table in paginatedTableStructures"
              :key="table.id"
              class="table-item"
              :class="{ active: selectedTableId === table.id }"
              @click="selectTableForView(table)"
            >
              <div class="table-name">{{ table.table_name }}</div>
              <div class="table-alias">{{ table.table_alias || '无别名' }}</div>
              <div class="table-actions-small">
                <el-button type="danger" size="small" link @click.stop="handleDeleteTable(table)">
                  删除
                </el-button>
              </div>
            </div>
          </div>
          <div class="table-list-pagination" v-if="kbTableStructures.length > 0">
            <el-pagination
              v-model:current-page="currentPage"
              v-model:page-size="pageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="kbTableStructures.length"
              layout="total, sizes, prev, pager, next"
              small
              @size-change="() => { currentPage = 1 }"
            />
          </div>
        </div>

        <!-- 右侧字段清单 -->
        <div class="field-list-panel">
          <div v-if="selectedTable">
            <el-table :data="selectedTable.kb_table_fields" border style="width: 100%">
              <el-table-column prop="field_name" label="字段名" width="200" />
              <el-table-column prop="field_alias" label="字段别名" width="150" />
              <el-table-column prop="field_type" label="字段类型" width="150" />
              <el-table-column prop="is_vectorized" label="是否向量化" width="120">
                <template #default="scope">
                  <el-switch
                    v-model="scope.row.is_vectorized"
                    @change="handleFieldVectorizeChange(scope.row)"
                  />
                </template>
              </el-table-column>
              <el-table-column prop="is_value_vectorized" label="向量化状态" width="120">
                <template #default="scope">
                  <el-tag :type="getFieldStatus(scope.row).type" size="small">
                    {{ getFieldStatus(scope.row).label }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="scope">
                  <el-button type="danger" size="small" link @click="handleDeleteField(scope.row)">
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div v-else>
            <div class="field-list">
              <div class="no-selection">请选择一张表查看字段详情</div>
            </div>
          </div>
        </div>
      </div>
    </el-card>
    
    <el-empty description="暂无表结构" v-else>
      <el-button type="primary" @click="handleSelectTables">
        <el-icon><Select /></el-icon>
        选择表结构
      </el-button>
    </el-empty>
    
    <!-- 选择表结构对话框 -->
    <el-dialog
      v-model="selectDialogVisible"
      title="添加表"
      width="900px"
    >
      <div class="select-table-container">
        <!-- 左侧表列表 -->
        <div class="table-list-panel">
          <div class="search-box">
            <el-input
              v-model="tableSearchText"
              placeholder="请输入表名"
              prefix-icon="Search"
              style="width: 200px"
            />
          </div>
          <div class="table-list">
            <div class="table-count">共 {{ filteredTableStructures.length }} 张表</div>
            <div 
              v-for="table in filteredTableStructures" 
              :key="table.id"
              class="table-item"
              :class="{ active: selectedTableName === table.table_name }"
              @click="selectTable(table)"
            >
              <div class="table-name">{{ table.table_name }}</div>
              <div class="table-alias">{{ table.table_alias }}</div>
            </div>
          </div>
        </div>
        
        <!-- 右侧字段列表 -->
        <div class="field-list-panel">
          <div class="field-header">
            <div class="field-title">
              <span>选择字段</span>
              <span class="table-info">表名: {{ selectedTableName }} </span>
              <span class="table-info" v-if="selectedTableAlias">({{ selectedTableAlias }})</span>
            </div>
            <el-input
              v-model="fieldSearchText"
              placeholder="请输入关键词"
              prefix-icon="Search"
              style="width: 200px"
            />
          </div>
          <div class="field-list">
            <el-table
              ref="fieldTableRef"
              :data="filteredFields"
              border
              style="width: 100%"
              row-key="id"
              @select="handleFieldSelect"
              @select-all="handleFieldSelectAll"
            >
              <el-table-column type="selection" width="55" />
              <el-table-column prop="field_name" label="字段" width="200" />
              <el-table-column prop="field_alias" label="字段描述" />
            </el-table>
          </div>
        </div>
      </div>
      
      <!-- 已选择的字段数量 -->
      <div class="selected-info" v-if="selectedFieldIds.length > 0">
        <span>已选择 {{ selectedFieldIds.length }} 个字段</span>
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="selectDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleConfirmSelect">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Select, Delete } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import knowledgeBaseApi from '@/api/knowledgeBase'
import tableStructureApi from '@/api/tableStructure'

const route = useRoute()
const router = useRouter()

// 知识库ID和名称
const knowledgeBaseId = ref(route.query.knowledgeBaseId)
const knowledgeBaseName = ref(route.query.knowledgeBaseName)

// 知识库表结构列表
const kbTableStructures = ref([])
const vectorizationStatus = ref('pending')
const refreshing = ref(false)
let refreshTimer = null
// 可用的表结构列表
const availableTableStructures = ref([])
// 展开的表结构
const activeNames = ref([])
// 选择对话框
const selectDialogVisible = ref(false)
// 已选择的表ID
const selectedTableIds = ref([])
// 已选择的表字段ID
const selectedFieldIds = ref([])
// 表搜索文本
const tableSearchText = ref('')
// 字段搜索文本
const fieldSearchText = ref('')
// 当前选中的表
const selectedTable = ref(null)
// 当前选中的表名
const selectedTableName = ref('')
// 当前选中的表别名
const selectedTableAlias = ref('')
// 已选择的字段映射，键为表ID，值为字段ID数组
const selectedFieldsMap = ref({})
// 用于左右结构展示的变量
const selectedTableId = ref(null)
// 分页
const currentPage = ref(1)
const pageSize = ref(20)

const paginatedTableStructures = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return kbTableStructures.value.slice(start, start + pageSize.value)
})
// 右侧字段表格引用
const fieldTableRef = ref(null)
// 是否正在恢复选中状态（防止 toggleRowSelection 触发 @select 事件时覆盖 map）
const isRestoringSelection = ref(false)

// 验证知识库ID
if (!knowledgeBaseId.value) {
  ElMessage.error('知识库ID不能为空')
  router.push('/knowledge-base')
}

// 获取知识库表结构
const getFieldStatus = (field) => {
  if (!field.is_enabled || !field.is_vectorized) return { label: '未启用', type: 'info' }
  if (field.is_value_vectorized) return { label: '已完成', type: 'success' }
  if (vectorizationStatus.value === 'failed') return { label: '未完成', type: 'danger' }
  if (['processing', 'cancelling'].includes(vectorizationStatus.value)) return { label: '待完成', type: 'warning' }
  return { label: '未完成', type: 'info' }
}

const getKbTableStructures = async (silent = false) => {
  if (refreshing.value || selectDialogVisible.value) return
  refreshing.value = true
  try {
    const response = await knowledgeBaseApi.getKnowledgeBase(knowledgeBaseId.value)
    vectorizationStatus.value = response.vectorization_status || 'pending'
    kbTableStructures.value = response.kb_table_structures || []
    // 检查每个表是否包含kb_table_fields字段
    kbTableStructures.value.forEach(table => {
      if (!table.kb_table_fields) {
        console.log(`表 ${table.table_name} 缺少kb_table_fields字段`)
        table.kb_table_fields = [] // 确保字段数组存在
      }
    })
    // 刷新进度时保留当前表，避免自动切回第一张表。
    if (!selectDialogVisible.value) {
      const table = kbTableStructures.value.find(item => item.id === selectedTableId.value) || kbTableStructures.value[0]
      selectedTableId.value = table?.id ?? null
      selectedTable.value = table || null
    }
  } catch (error) {
    if (!silent) ElMessage.error('获取知识库表结构失败：' + (error.response?.data?.detail || error.message))
  } finally {
    refreshing.value = false
  }
}

// 选择表用于查看详情
const selectTableForView = async (table) => {
  selectedTableId.value = table.id
  selectedTable.value = table
  
  try {
    // 调用新的API获取单个表结构及其字段数据
    const response = await knowledgeBaseApi.getKbTableStructure(table.id)
    console.log('获取到的表结构及其字段：', response)
    console.log('表字段数量：', response.kb_table_fields?.length || 0)
    selectedTable.value = response
  } catch (error) {
    console.error('获取表字段数据失败：', error)
    // 如果获取失败，保持原有数据
  }
}

// 筛选后的表结构列表
const filteredTableStructures = computed(() => {
  if (!tableSearchText.value) {
    return availableTableStructures.value
  }
  return availableTableStructures.value.filter(table => 
    table.table_name.includes(tableSearchText.value) || 
    table.table_alias.includes(tableSearchText.value)
  )
})

// 筛选后的字段列表
const filteredFields = computed(() => {
  if (!selectedTable.value || !selectedTable.value.table_fields) {
    return []
  }
  // 只显示生效状态为true的字段
  let fields = selectedTable.value.table_fields.filter(field => field.is_enabled)
  if (!fieldSearchText.value) {
    return fields
  }
  return fields.filter(field => 
    field.field_name.includes(fieldSearchText.value) || 
    field.field_alias.includes(fieldSearchText.value) ||
    field.field_type.includes(fieldSearchText.value)
  )
})

// 获取可用的表结构（来自知识接入）
const getAvailableTableStructures = async () => {
  try {
    // 首先获取知识库详情，了解其关联的知识接入ID
    const knowledgeBase = await knowledgeBaseApi.getKnowledgeBase(knowledgeBaseId.value)
    const knowledgeAccessId = knowledgeBase.knowledge_access_id
    
    // 获取该知识接入下的所有表结构
    const response = await tableStructureApi.getTableStructures(knowledgeAccessId)
    
    // 获取每个表结构的字段（只获取生效字段）
    const tableStructuresWithFields = await Promise.all(
      response.map(async (table) => {
        const fields = await tableStructureApi.getTableFields(table.id, true)  // enabledOnly=true
        return { ...table, table_fields: fields }
      })
    )
    
    availableTableStructures.value = tableStructuresWithFields
    
    // 默认选中第一张表
    if (tableStructuresWithFields.length > 0) {
      selectTable(tableStructuresWithFields[0])
    }
  } catch (error) {
    ElMessage.error('获取可用表结构失败：' + (error.response?.data?.detail || error.message))
  }
}

// 选择表
const selectTable = (table) => {
  selectedTable.value = table
  selectedTableName.value = table.table_name
  selectedTableAlias.value = table.table_alias || ''

  // 初始化该表的选中字段
  if (!selectedFieldsMap.value[table.id]) {
    selectedFieldsMap.value[table.id] = []
  }

  // 等待 DOM 更新后恢复该表已勾选的字段
  nextTick(() => {
    if (!fieldTableRef.value) return
    const selectedIds = selectedFieldsMap.value[table.id] || []
    isRestoringSelection.value = true
    filteredFields.value.forEach(field => {
      fieldTableRef.value.toggleRowSelection(field, selectedIds.includes(field.id))
    })
    nextTick(() => {
      isRestoringSelection.value = false
    })
  })
}

// 选择字段
const handleFieldSelect = (selection, row) => {
  if (!selectedTable.value || isRestoringSelection.value) return

  const fieldIds = selection.map(item => item.id)
  selectedFieldsMap.value[selectedTable.value.id] = fieldIds

  updateSelectedCounts()
}

// 全选字段
const handleFieldSelectAll = (selection) => {
  if (!selectedTable.value || isRestoringSelection.value) return

  const fieldIds = selection.map(item => item.id)
  selectedFieldsMap.value[selectedTable.value.id] = fieldIds

  updateSelectedCounts()
}

// 更新已选择的表ID和字段ID总数
const updateSelectedCounts = () => {
  // 过滤掉空数组的条目
  const entries = Object.entries(selectedFieldsMap.value).filter(([, ids]) => ids.length > 0)
  selectedTableIds.value = entries.map(([id]) => parseInt(id))
  selectedFieldIds.value = entries.flatMap(([, ids]) => ids)
}

// 选择表结构
const handleSelectTables = () => {
  // 重置选择状态
  selectedTableIds.value = []
  selectedFieldIds.value = []
  tableSearchText.value = ''
  fieldSearchText.value = ''
  selectedTable.value = null
  selectedTableName.value = ''
  selectedTableAlias.value = ''
  selectedFieldsMap.value = {}
  
  getAvailableTableStructures()
  selectDialogVisible.value = true
}

// 确认选择表结构
const handleConfirmSelect = async () => {
  if (selectedFieldIds.value.length === 0) {
    ElMessage.warning('请至少选择一个字段')
    return
  }
  
  try {
    await knowledgeBaseApi.batchSelectTableStructures(knowledgeBaseId.value, {
      fields: Object.entries(selectedFieldsMap.value).flatMap(([tableId, fieldIds]) => 
        fieldIds.map(fieldId => ({ table_id: parseInt(tableId), field_id: fieldId }))
      )
    })
    ElMessage.success('选择表结构成功')
    selectDialogVisible.value = false
    getKbTableStructures()
  } catch (error) {
    ElMessage.error('选择表结构失败：' + (error.response?.data?.detail || error.message))
  }
}

// 表向量化状态改变
const handleTableVectorizeChange = async (table) => {
  try {
    await knowledgeBaseApi.updateKbTableStructure(table.id, {
      is_vectorized: table.is_vectorized
    })
    ElMessage.success('更新表向量化状态成功')
  } catch (error) {
    ElMessage.error('更新表向量化状态失败：' + (error.response?.data?.detail || error.message))
    // 恢复原始状态
    table.is_vectorized = !table.is_vectorized
  }
}

// 删除表
const handleDeleteTable = async (table) => {
  try {
    await knowledgeBaseApi.deleteKbTableStructure(table.id)
    ElMessage.success('删除表成功')
    getKbTableStructures()
  } catch (error) {
    ElMessage.error('删除表失败：' + (error.response?.data?.detail || error.message))
  }
}

// 字段启用状态改变
const handleFieldEnabledChange = async (field) => {
  try {
    await knowledgeBaseApi.updateKbTableField(field.id, {
      is_enabled: field.is_enabled
    })
    ElMessage.success('更新字段启用状态成功')
  } catch (error) {
    ElMessage.error('更新字段启用状态失败：' + (error.response?.data?.detail || error.message))
    // 恢复原始状态
    field.is_enabled = !field.is_enabled
  }
}

// 字段向量化状态改变
const handleFieldVectorizeChange = async (field) => {
  try {
    await knowledgeBaseApi.updateKbTableField(field.id, {
      is_vectorized: field.is_vectorized
    })
    ElMessage.success('更新字段向量化状态成功')
  } catch (error) {
    ElMessage.error('更新字段向量化状态失败：' + (error.response?.data?.detail || error.message))
    // 恢复原始状态
    field.is_vectorized = !field.is_vectorized
  }
}

// 删除字段
const handleDeleteField = async (field) => {
  try {
    await knowledgeBaseApi.deleteKbTableField(field.id)
    ElMessage.success('删除字段成功')
    getKbTableStructures()
  } catch (error) {
    ElMessage.error('删除字段失败：' + (error.response?.data?.detail || error.message))
  }
}

// 页面加载时获取数据
onMounted(() => {
  getKbTableStructures()
  refreshTimer = setInterval(() => {
    if (['processing', 'cancelling'].includes(vectorizationStatus.value) && !document.hidden) getKbTableStructures(true)
  }, 5000)
})

onUnmounted(() => {
  clearInterval(refreshTimer)
})
</script>

<style scoped>
.knowledge-base-table-structure {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.selected-info {
  padding: 10px;
  text-align: right;
  color: #606266;
}

.dialog-footer {
  text-align: right;
}

/* 选择表结构对话框样式 */
.select-table-container {
  display: flex;
  height: 500px;
  gap: 20px;
}

/* 左侧表列表样式 */
.table-list-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.search-box {
  margin-bottom: 10px;
}

.table-list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.table-count {
  padding: 10px;
  color: #606266;
  border-bottom: 1px solid #e4e7ed;
}

.table-item {
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f5f7fa;
}

.table-item:hover {
  background-color: #f5f7fa;
}

.table-item.active {
  background-color: var(--el-color-primary-light-9);
  border-left: 3px solid var(--el-color-primary);
}

.table-name {
  font-weight: 500;
  color: #303133;
}

.table-alias {
  font-size: 12px;
  color: #606266;
  margin-top: 2px;
}

/* 右侧字段列表样式 */
.field-list-panel {
  flex: 2;
  display: flex;
  flex-direction: column;
}

.field-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.field-title {
  font-weight: 500;
  color: #303133;
}

.table-info {
  font-size: 12px;
  color: #606266;
  margin-left: 10px;
}

.field-list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

/* 左右结构布局样式 */
.table-field-container {
  display: flex;
  gap: 20px;
  height: calc(100vh - 300px);
}

/* 主页面左侧表列表样式（更具体的选择器） */
.table-field-container .table-list-panel {
  flex: none;
  width: 180px;
  border-right: 1px solid #eee;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.table-list-pagination {
  padding: 8px 4px;
  border-top: 1px solid #eee;
  flex-shrink: 0;
}

.table-field-container .field-list-panel {
  flex: 1;
  overflow-y: auto;
}
  
/* 主页面表项样式 */
.table-field-container .table-item {
  padding: 12px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
  transition: background-color 0.3s;
}

.table-field-container .table-item:hover {
  background-color: #f5f7fa;
}

.table-field-container .table-item.active {
  background-color: var(--el-color-primary-light-9);
  border-right: 3px solid var(--el-color-primary);
}

.table-field-container .table-name {
  font-weight: bold;
  margin-bottom: 4px;
}

.table-field-container .table-alias {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}

.table-field-container .table-actions-small {
  display: flex;
  align-items: center;
  gap: 10px;
}

.table-field-container .no-selection {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 200px;
  color: #909399;
  background-color: #f5f7fa;
  border-radius: 4px;
}
</style>
