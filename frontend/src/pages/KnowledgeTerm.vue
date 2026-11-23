<template>
  <div class="knowledge-term">
    <PageHeader
      :breadcrumbs="[{ label: '数据集', to: '/knowledge-access' }, { label: '知识词条' }]"
    />
    
    <el-card shadow="never" class="mt-20">
      <div class="card-header">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          新建词条
        </el-button>
        <div>
          <el-button @click="openImportDialog">
            <el-icon><Upload /></el-icon>
            导入
          </el-button>
          <el-button type="success" plain @click="handleExport">
            <el-icon><Download /></el-icon>
            导出
          </el-button>
        </div>
      </div>
      
      <el-table :data="knowledgeTerms" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="term_name" label="词条名称" />
        <el-table-column prop="term_value" label="词条值" show-overflow-tooltip>
          <template #default="scope">
            <div class="term-value">{{ scope.row.term_value }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="scope">
            <el-button type="primary" size="small" link @click="handleEdit(scope.row)">
              编辑
            </el-button>
            <el-button type="danger" size="small" link @click="handleDelete(scope.row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap" v-if="total > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="getKnowledgeTerms"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>
    
    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'create' ? '新建词条' : '编辑词条'"
      width="600px"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="80px"
      >
        <el-form-item label="名称" prop="term_name">
          <el-input v-model="form.term_name" placeholder="请输入词条名称" />
        </el-form-item>
        <el-form-item label="值" prop="term_value">
          <el-input
            v-model="form.term_value"
            type="textarea"
            placeholder="请输入词条值"
            :rows="4"
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

    <!-- 导入对话框 -->
    <el-dialog
      v-model="importDialogVisible"
      title="导入知识词条"
      width="540px"
      destroy-on-close
      @closed="onImportDialogClosed"
    >
      <el-form label-position="top">
        <el-form-item label="导入方式" required>
          <el-radio-group v-model="importMode">
            <el-radio label="replace_all">覆盖（清空当前数据后写入文件）</el-radio>
            <el-radio label="append">增加（在现有数据后追加）</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <div class="import-steps">
        <div class="import-step">
          <span class="import-step-label">1. 下载模板</span>
          <el-button type="primary" plain class="import-step-btn" @click="handleDownloadTemplate">
            <el-icon><Download /></el-icon>
            下载模板
          </el-button>
        </div>
        <div class="import-step">
          <span class="import-step-label">2. 上传填写后的文件</span>
          <el-upload
            class="import-upload"
            :auto-upload="false"
            :show-file-list="true"
            :limit="1"
            accept=".xlsx,.xlsm"
            v-model:file-list="importFileList"
            :on-change="onImportFilePick"
          >
            <el-button type="primary">
              <el-icon><Upload /></el-icon>
              选择文件
            </el-button>
          </el-upload>
        </div>
        <p class="import-footnote">
          支持 .xlsx、.xlsm；词条名称最多 <strong>100</strong> 个字符，词条值最多 <strong>500</strong> 个字符，超出部分在导入时截断。
        </p>
      </div>
      <template #footer>
        <el-button @click="importDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Upload, Download } from '@element-plus/icons-vue'
import knowledgeTermApi from '@/api/knowledgeTerm'
import {
  downloadTermTemplate,
  downloadTermExportFromApiRows,
  parseTermWorkbookArrayBuffer
} from '@/utils/kbTermExcel'

const route = useRoute()
const knowledgeAccessId = computed(() => parseInt(route.params.id))

// 知识词条列表数据
const knowledgeTerms = ref([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
// 对话框显示状态
const dialogVisible = ref(false)
// 对话框类型：create 或 edit
const dialogType = ref('create')
// 表单引用
const formRef = ref()
// 表单数据
const form = ref({
  term_name: '',
  term_value: ''
})
// 表单校验规则
const rules = {
  term_name: [
    { required: true, message: '请输入词条名称', trigger: 'blur' },
    { min: 1, max: 100, message: '长度在 1 到 100 个字符', trigger: 'blur' }
  ],
  term_value: [
    { required: true, message: '请输入词条值', trigger: 'blur' },
    { min: 1, max: 500, message: '长度在 1 到 500 个字符', trigger: 'blur' }
  ]
}

// 导入相关
const importDialogVisible = ref(false)
const importMode = ref('append')
const importFileList = ref([])

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}

// 获取知识词条列表
const getKnowledgeTerms = async () => {
  loading.value = true
  try {
    const skip = (currentPage.value - 1) * pageSize.value
    const response = await knowledgeTermApi.getKnowledgeTerms(knowledgeAccessId.value, {
      skip,
      limit: pageSize.value
    })
    knowledgeTerms.value = response.items || []
    total.value = response.total || 0
  } catch (error) {
    ElMessage.error('获取知识词条列表失败：' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

const handleSizeChange = () => {
  currentPage.value = 1
  getKnowledgeTerms()
}

// 新建词条
const handleCreate = () => {
  dialogType.value = 'create'
  form.value = {
    term_name: '',
    term_value: ''
  }
  dialogVisible.value = true
}

// 编辑词条
const handleEdit = (row) => {
  dialogType.value = 'edit'
  form.value = {
    id: row.id,
    term_name: row.term_name,
    term_value: row.term_value
  }
  dialogVisible.value = true
}

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    
    if (dialogType.value === 'create') {
      // 创建新词条
      await knowledgeTermApi.createKnowledgeTerm(
        knowledgeAccessId.value,
        form.value
      )
      ElMessage.success('词条创建成功')
    } else {
      // 更新词条
      await knowledgeTermApi.updateKnowledgeTerm(
        form.value.id,
        form.value
      )
      ElMessage.success('词条更新成功')
    }
    await getKnowledgeTerms()
    
    dialogVisible.value = false
  } catch (error) {
    if (error.name !== 'Error') {
      // 表单验证失败
      return
    }
    ElMessage.error('操作失败：' + (error.response?.data?.detail || error.message))
  }
}

// 删除词条
const handleDelete = (row) => {
  ElMessageBox.confirm('确定要删除该词条吗？删除后将不可恢复。', '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await knowledgeTermApi.deleteKnowledgeTerm(row.id)
      ElMessage.success('词条删除成功')
      await getKnowledgeTerms()
    } catch (error) {
      ElMessage.error('删除失败：' + (error.response?.data?.detail || error.message))
    }
  }).catch(() => {
    // 取消删除
  })
}

// 导出
const handleExport = async () => {
  try {
    const rows = await knowledgeTermApi.exportKnowledgeTerms(knowledgeAccessId.value)
    const name = `知识词条导出_${new Date().toISOString().slice(0, 10)}`
    await downloadTermExportFromApiRows(rows, name)
    if (!rows || rows.length === 0) {
      ElMessage.info('当前无数据，已下载模板文件')
    } else {
      ElMessage.success('导出成功')
    }
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '导出失败')
  }
}

// 导入相关函数
const openImportDialog = () => {
  importMode.value = 'append'
  importDialogVisible.value = true
}

const onImportDialogClosed = () => {
  importFileList.value = []
}

const handleDownloadTemplate = async () => {
  await downloadTermTemplate()
  ElMessage.success('模板已下载')
}

const onImportFilePick = async (uploadFile) => {
  const raw = uploadFile.raw
  if (!raw) return
  const lower = raw.name.toLowerCase()
  if (!lower.endsWith('.xlsx') && !lower.endsWith('.xlsm')) {
    ElMessage.error('请上传 .xlsx 或 .xlsm')
    importFileList.value = []
    return
  }
  try {
    const buf = await raw.arrayBuffer()
    const parsed = await parseTermWorkbookArrayBuffer(buf)
    const apiRows = parsed.filter(r => r.term_name || r.term_value)
    if (apiRows.length === 0) {
      ElMessage.warning('未解析到有效数据')
      importFileList.value = []
      return
    }
    const res = await knowledgeTermApi.importKnowledgeTerms(knowledgeAccessId.value, {
      mode: importMode.value,
      rows: apiRows
    })
    ElMessage.success(res.message || '导入成功')
    importDialogVisible.value = false
    importFileList.value = []
    currentPage.value = 1
    await getKnowledgeTerms()
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '导入失败')
    importFileList.value = []
  }
}

// 组件挂载时获取数据
onMounted(() => {
  getKnowledgeTerms()
})
</script>

<style scoped>
.knowledge-term {
  padding: 20px;
}

.mt-20 {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.card-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: bold;
}

.term-value {
  max-width: 400px;
  word-break: break-all;
}

.import-steps {
  padding: 8px 0;
}

.import-step {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.import-step-label {
  font-size: 14px;
  color: #606266;
}

.import-upload {
  display: inline-block;
}

.import-footnote {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin: 8px 0 0;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
