<template>
  <div class="table-structure-config">
    <PageHeader
      :breadcrumbs="[{ label: '数据集', to: '/knowledge-access' }, { label: '表结构配置' }]"
    />
    
    <el-card shadow="never" class="mt-20">
      <div class="card-header">
        <h3>表结构列表</h3>
        <div class="header-buttons">
          <el-button type="primary" size="small" @click="handleCreateTable">
            <el-icon><Plus /></el-icon>
            新建表结构
          </el-button>
          <el-button type="primary" size="small" @click="handleImportTables">
            <el-icon><Upload /></el-icon>
            导入表结构
          </el-button>
        </div>
      </div>
      
      <el-tabs v-model="activeTab">
        <el-tab-pane
          v-for="table in tableStructures"
          :key="table.id"
          :name="table.id.toString()"
        >
          <template #label>
            <div class="tab-label-content">
              <span class="tab-name">{{ table.table_name }}</span>
              <span class="tab-alias">({{ table.table_alias || '未设置中文名称' }})</span>
              <el-button
                type="primary"
                size="small"
                link
                @click.stop="handleEditTable(table)"
                class="tab-btn"
              >
                <el-icon><Edit /></el-icon>
              </el-button>
              <el-button
                type="danger"
                size="small"
                link
                @click.stop="handleDeleteTable(table)"
                class="tab-btn"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </template>
          <div class="field-list-header">
            <span>字段列表</span>
            <el-button type="primary" size="small" @click="handleCreateField(table)">
              <el-icon><Plus /></el-icon>
              新建字段
            </el-button>
          </div>
          
          <el-table :data="getTableFields(table.id)" stripe style="width: 100%; margin-top: 10px;">
            <el-table-column prop="field_name" label="字段名" />
            <el-table-column prop="field_alias" label="字段中文名">
              <template #default="scope">
                <el-input
                  v-model="scope.row.field_alias"
                  placeholder="请输入字段中文名"
                  size="small"
                  @change="handleUpdateField(scope.row)"
                />
              </template>
            </el-table-column>
            <el-table-column prop="field_type" label="字段类型" />
            <el-table-column prop="is_enabled" label="生效状态">
              <template #default="scope">
                <el-switch
                  v-model="scope.row.is_enabled"
                  @change="handleUpdateField(scope.row)"
                />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
    
    <!-- 新建/编辑表结构对话框 -->
    <el-dialog
      v-model="tableDialogVisible"
      :title="tableDialogType === 'create' ? '新建表结构' : '编辑表结构'"
      width="400px"
    >
      <el-form
        ref="tableFormRef"
        :model="tableForm"
        :rules="tableRules"
        label-width="80px"
      >
        <el-form-item label="表名" prop="table_name">
          <el-input v-model="tableForm.table_name" placeholder="请输入表名" />
        </el-form-item>
        <el-form-item label="中文名称" prop="table_alias">
          <el-input v-model="tableForm.table_alias" placeholder="请输入表中文名" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="tableDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmitTable">确定</el-button>
        </span>
      </template>
    </el-dialog>
    
    <!-- 新建字段对话框 -->
    <el-dialog
      v-model="fieldDialogVisible"
      title="新建字段"
      width="400px"
    >
      <el-form
        ref="fieldFormRef"
        :model="fieldForm"
        :rules="fieldRules"
        label-width="80px"
      >
        <el-form-item label="字段名" prop="field_name">
          <el-input v-model="fieldForm.field_name" placeholder="请输入字段名" />
        </el-form-item>
        <el-form-item label="中文名称" prop="field_alias">
          <el-input v-model="fieldForm.field_alias" placeholder="请输入字段中文名" />
        </el-form-item>
        <el-form-item label="字段类型" prop="field_type">
          <el-select v-model="fieldForm.field_type" placeholder="请选择字段类型">
            <el-option label="字符串" value="varchar" />
            <el-option label="整数" value="int" />
            <el-option label="浮点数" value="float" />
            <el-option label="日期" value="date" />
            <el-option label="时间" value="datetime" />
            <el-option label="文本" value="text" />
          </el-select>
        </el-form-item>
        <el-form-item label="生效状态" prop="is_enabled">
          <el-switch v-model="fieldForm.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="fieldDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSubmitField">确定</el-button>
        </span>
      </template>
    </el-dialog>
    
    <!-- 导入表结构对话框 -->
    <el-dialog
      v-model="importDialogVisible"
      title="导入表结构"
      width="700px"
    >
      <div class="import-dialog-content">
        <div class="dialog-toolbar">
          <el-input
            v-model="importSearchText"
            placeholder="搜索表名"
            prefix-icon="Search"
            clearable
            style="width: 200px"
          />
          <div class="selection-buttons">
            <el-button size="small" @click="handleSelectAll">全选</el-button>
            <el-button size="small" @click="handleDeselectAll">反选</el-button>
          </div>
        </div>
        
        <el-table
          ref="importTableRef"
          :data="filteredImportTables"
          stripe
          style="width: 100%"
          max-height="400px"
          @selection-change="handleImportSelectionChange"
        >
          <el-table-column type="selection" width="55" :selectable="checkImportable" />
          <el-table-column prop="table_name" label="表名" width="200" />
          <el-table-column prop="table_comment" label="表备注">
            <template #default="scope">
              {{ scope.row.table_comment || '-' }}
            </template>
          </el-table-column>
          <el-table-column prop="is_imported" label="状态" width="100">
            <template #default="scope">
              <el-tag v-if="scope.row.is_imported" type="info" size="small">已导入</el-tag>
              <el-tag v-else type="success" size="small">可导入</el-tag>
            </template>
          </el-table-column>
        </el-table>
        
        <div class="selection-info">
          已选择 {{ selectedImportTables.length }} 张表
        </div>
      </div>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="importDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleConfirmImport" :loading="importLoading">确定导入</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, Edit, Delete } from '@element-plus/icons-vue'
import tableStructureApi from '@/api/tableStructure'

const route = useRoute()
const knowledgeAccessId = computed(() => parseInt(route.params.id))

// 表结构列表
const tableStructures = ref([])
// 所有字段数据，按表结构ID分组
const allFields = ref({})
// 当前激活的标签页
const activeTab = ref('')

// 新建/编辑表结构对话框
const tableDialogVisible = ref(false)
const tableDialogType = ref('create')
const tableFormRef = ref()
const tableForm = ref({
  table_name: '',
  table_alias: ''
})
const tableRules = {
  table_name: [
    { required: true, message: '请输入表名', trigger: 'blur' },
    { min: 1, max: 50, message: '长度在 1 到 50 个字符', trigger: 'blur' }
  ]
}

// 新建字段对话框
const fieldDialogVisible = ref(false)
const currentTableId = ref(null)
const fieldFormRef = ref()
const fieldForm = ref({
  field_name: '',
  field_alias: '',
  field_type: 'varchar',
  is_enabled: true
})
const fieldRules = {
  field_name: [
    { required: true, message: '请输入字段名', trigger: 'blur' },
    { min: 1, max: 50, message: '长度在 1 到 50 个字符', trigger: 'blur' }
  ],
  field_type: [
    { required: true, message: '请选择字段类型', trigger: 'change' }
  ]
}

// 获取表结构列表
const getTableStructures = async () => {
  try {
    const response = await tableStructureApi.getTableStructures(knowledgeAccessId.value)
    tableStructures.value = response
    if (response.length > 0) {
      activeTab.value = response[0].id.toString()
      // 获取每个表的字段
      for (const table of response) {
        await getTableFieldsData(table.id)
      }
    }
  } catch (error) {
    ElMessage.error('获取表结构列表失败：' + (error.response?.data?.detail || error.message))
  }
}

// 获取表的字段数据
const getTableFieldsData = async (tableStructureId) => {
  try {
    const response = await tableStructureApi.getTableFields(tableStructureId)
    allFields.value[tableStructureId] = response
  } catch (error) {
    ElMessage.error('获取字段列表失败：' + (error.response?.data?.detail || error.message))
  }
}

// 根据表ID获取字段列表
const getTableFields = (tableId) => {
  return allFields.value[tableId] || []
}

// 新建表结构
const handleCreateTable = () => {
  tableDialogType.value = 'create'
  tableForm.value = {
    table_name: '',
    table_alias: ''
  }
  tableDialogVisible.value = true
}

// 编辑表结构
const handleEditTable = (table) => {
  tableDialogType.value = 'edit'
  tableForm.value = {
    id: table.id,
    table_name: table.table_name,
    table_alias: table.table_alias || ''
  }
  tableDialogVisible.value = true
}

// 删除表结构
const handleDeleteTable = async (table) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除表结构 "${table.table_name}" 吗？删除后将同时删除该表的所有字段配置。`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await tableStructureApi.deleteTableStructure(table.id)
    ElMessage.success('表结构删除成功')
    
    // 刷新表结构列表
    await getTableStructures()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除表结构失败：' + (error.response?.data?.detail || error.message))
    }
  }
}

// 提交表结构表单
const handleSubmitTable = async () => {
  if (!tableFormRef.value) return
  try {
    await tableFormRef.value.validate()
    
    if (tableDialogType.value === 'create') {
      // 创建新表
      const response = await tableStructureApi.createTableStructure(
        knowledgeAccessId.value,
        tableForm.value
      )
      tableStructures.value.push(response)
      ElMessage.success('表结构创建成功')
    } else {
      // 更新表
      const response = await tableStructureApi.updateTableStructure(
        tableForm.value.id,
        tableForm.value
      )
      const index = tableStructures.value.findIndex(t => t.id === response.id)
      if (index !== -1) {
        tableStructures.value[index] = response
      }
      ElMessage.success('表结构更新成功')
    }
    
    tableDialogVisible.value = false
  } catch (error) {
    if (error.name !== 'Error') {
      // 表单验证失败
      return
    }
    ElMessage.error('操作失败：' + (error.response?.data?.detail || error.message))
  }
}

// 新建字段
const handleCreateField = (table) => {
  currentTableId.value = table.id
  fieldForm.value = {
    field_name: '',
    field_alias: '',
    field_type: 'varchar',
    is_enabled: true
  }
  fieldDialogVisible.value = true
}

// 提交字段表单
const handleSubmitField = async () => {
  if (!fieldFormRef.value) return
  try {
    await fieldFormRef.value.validate()
    
    const response = await tableStructureApi.createTableField(
      currentTableId.value,
      fieldForm.value
    )
    
    // 添加到字段列表
    if (!allFields.value[currentTableId.value]) {
      allFields.value[currentTableId.value] = []
    }
    allFields.value[currentTableId.value].push(response)
    
    ElMessage.success('字段创建成功')
    fieldDialogVisible.value = false
  } catch (error) {
    if (error.name !== 'Error') {
      // 表单验证失败
      return
    }
    ElMessage.error('创建字段失败：' + (error.response?.data?.detail || error.message))
  }
}

// 更新字段
const handleUpdateField = async (field) => {
  try {
    await tableStructureApi.updateTableField(field.id, {
      field_alias: field.field_alias,
      is_enabled: field.is_enabled
    })
    ElMessage.success('字段更新成功')
  } catch (error) {
    ElMessage.error('更新字段失败：' + (error.response?.data?.detail || error.message))
    // 恢复原始值
    await getTableFieldsData(field.table_structure_id)
  }
}

// 导入表结构相关变量
const importDialogVisible = ref(false)
const importTableRef = ref()
const importTables = ref([])
const importSearchText = ref('')
const selectedImportTables = ref([])
const importLoading = ref(false)

// 筛选后的导入表列表
const filteredImportTables = computed(() => {
  if (!importSearchText.value) {
    return importTables.value
  }
  return importTables.value.filter(table => 
    table.table_name.toLowerCase().includes(importSearchText.value.toLowerCase()) ||
    (table.table_comment && table.table_comment.toLowerCase().includes(importSearchText.value.toLowerCase()))
  )
})

// 检查表是否可导入（已导入的不可选）
const checkImportable = (row) => {
  return !row.is_imported
}

// 导入选择变化
const handleImportSelectionChange = (selection) => {
  selectedImportTables.value = selection
}

// 全选（只选择可导入的）
const handleSelectAll = () => {
  importTableRef.value.clearSelection()
  filteredImportTables.value.forEach(row => {
    if (!row.is_imported) {
      importTableRef.value.toggleRowSelection(row, true)
    }
  })
}

// 反选
const handleDeselectAll = () => {
  filteredImportTables.value.forEach(row => {
    importTableRef.value.toggleRowSelection(row, false)
  })
}

// 打开导入对话框
const handleImportTables = async () => {
  try {
    const response = await tableStructureApi.getDatabaseTables(knowledgeAccessId.value)
    importTables.value = response
    importSearchText.value = ''
    selectedImportTables.value = []
    importDialogVisible.value = true
  } catch (error) {
    ElMessage.error('获取数据库表列表失败：' + (error.response?.data?.detail || error.message))
  }
}

// 确认导入
const handleConfirmImport = async () => {
  if (selectedImportTables.value.length === 0) {
    ElMessage.warning('请选择要导入的表')
    return
  }
  
  importLoading.value = true
  try {
    const tableNames = selectedImportTables.value.map(t => t.table_name)
    const response = await tableStructureApi.importTables(knowledgeAccessId.value, tableNames)
    
    ElMessage.success(`成功导入 ${response.imported_count} 张表`)
    importDialogVisible.value = false
    
    // 刷新表结构列表
    await getTableStructures()
  } catch (error) {
    ElMessage.error('导入表结构失败：' + (error.response?.data?.detail || error.message))
  } finally {
    importLoading.value = false
  }
}

// 组件挂载时获取数据
onMounted(() => {
  getTableStructures()
})
</script>

<style scoped>
.table-structure-config {
  padding: 20px;
}

.mt-20 {
  margin-top: 20px;
}

.card-header,
.field-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.card-header h3,
.field-list-header span {
  margin: 0;
  font-size: 16px;
  font-weight: bold;
}

.header-buttons {
  display: flex;
  gap: 10px;
}

.import-dialog-content {
  padding: 0;
}

.dialog-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.selection-buttons {
  display: flex;
  gap: 10px;
}

.selection-info {
  margin-top: 10px;
  text-align: right;
  color: #606266;
  font-size: 14px;
}

.tab-label-content {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.tab-name {
  font-weight: 500;
}

.tab-alias {
  color: #909399;
  font-size: 12px;
}

.tab-btn {
  margin-left: 4px;
  padding: 2px;
}

.tab-btn:hover {
  background-color: transparent;
}
</style>
