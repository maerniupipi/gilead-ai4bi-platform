<template>
  <div class="sample-library">
    <PageHeader
      :breadcrumbs="[{ label: '数据集', to: '/knowledge-access' }, { label: '样例库' }]"
    />
    
    <el-card shadow="never" class="mt-20">
      <div class="card-header">
        <el-button type="primary" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          新建样例
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
      
      <el-table :data="sampleLibraries" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="sample_name" label="样例名称" />
        <el-table-column prop="sql_content" label="SQL内容" show-overflow-tooltip>
          <template #default="scope">
            <div class="sql-content">{{ scope.row.sql_content }}</div>
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
          @current-change="getSampleLibraries"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>
    
    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'create' ? '新建样例' : '编辑样例'"
      width="700px"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="80px"
      >
        <el-form-item label="名称" prop="sample_name">
          <el-input v-model="form.sample_name" placeholder="请输入样例名称" />
        </el-form-item>
        <el-form-item label="SQL内容" prop="sql_content">
          <el-input
            v-model="form.sql_content"
            type="textarea"
            placeholder="请输入SQL内容"
            :rows="6"
            monospace
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
      title="导入样例"
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
          支持 .xlsx、.xlsm；样例名称最多 <strong>100</strong> 个字符，SQL内容最多 <strong>2000</strong> 个字符，超出部分在导入时截断。
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
import sampleLibraryApi from '@/api/sampleLibrary'
import {
  downloadSampleTemplate,
  downloadSampleExportFromApiRows,
  parseSampleWorkbookArrayBuffer
} from '@/utils/kbSampleExcel'

const route = useRoute()
const knowledgeAccessId = computed(() => parseInt(route.params.id))

// 样例库列表数据
const sampleLibraries = ref([])
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
  sample_name: '',
  sql_content: ''
})
// 表单校验规则
const rules = {
  sample_name: [
    { required: true, message: '请输入样例名称', trigger: 'blur' },
    { min: 1, max: 100, message: '长度在 1 到 100 个字符', trigger: 'blur' }
  ],
  sql_content: [
    { required: true, message: '请输入SQL内容', trigger: 'blur' },
    { min: 1, max: 2000, message: '长度在 1 到 2000 个字符', trigger: 'blur' }
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

// 获取样例库列表
const getSampleLibraries = async () => {
  loading.value = true
  try {
    const skip = (currentPage.value - 1) * pageSize.value
    const response = await sampleLibraryApi.getSampleLibraries(knowledgeAccessId.value, {
      skip,
      limit: pageSize.value
    })
    sampleLibraries.value = response.items || []
    total.value = response.total || 0
  } catch (error) {
    ElMessage.error('获取样例库列表失败：' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

const handleSizeChange = () => {
  currentPage.value = 1
  getSampleLibraries()
}

// 新建样例
const handleCreate = () => {
  dialogType.value = 'create'
  form.value = {
    sample_name: '',
    sql_content: ''
  }
  dialogVisible.value = true
}

// 编辑样例
const handleEdit = (row) => {
  dialogType.value = 'edit'
  form.value = {
    id: row.id,
    sample_name: row.sample_name,
    sql_content: row.sql_content
  }
  dialogVisible.value = true
}

// 提交表单
const handleSubmit = async () => {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
    
    if (dialogType.value === 'create') {
      // 创建新样例
      await sampleLibraryApi.createSampleLibrary(
        knowledgeAccessId.value,
        form.value
      )
      ElMessage.success('样例创建成功')
    } else {
      // 更新样例
      await sampleLibraryApi.updateSampleLibrary(
        form.value.id,
        form.value
      )
      ElMessage.success('样例更新成功')
    }
    await getSampleLibraries()
    
    dialogVisible.value = false
  } catch (error) {
    if (error.name !== 'Error') {
      // 表单验证失败
      return
    }
    ElMessage.error('操作失败：' + (error.response?.data?.detail || error.message))
  }
}

// 删除样例
const handleDelete = (row) => {
  ElMessageBox.confirm('确定要删除该样例吗？删除后将不可恢复。', '警告', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await sampleLibraryApi.deleteSampleLibrary(row.id)
      ElMessage.success('样例删除成功')
      await getSampleLibraries()
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
    const rows = await sampleLibraryApi.exportSampleLibraries(knowledgeAccessId.value)
    const name = `样例库导出_${new Date().toISOString().slice(0, 10)}`
    await downloadSampleExportFromApiRows(rows, name)
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
  await downloadSampleTemplate()
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
    const parsed = await parseSampleWorkbookArrayBuffer(buf)
    const apiRows = parsed.filter(r => r.sample_name || r.sql_content)
    if (apiRows.length === 0) {
      ElMessage.warning('未解析到有效数据')
      importFileList.value = []
      return
    }
    const res = await sampleLibraryApi.importSampleLibraries(knowledgeAccessId.value, {
      mode: importMode.value,
      rows: apiRows
    })
    ElMessage.success(res.message || '导入成功')
    importDialogVisible.value = false
    importFileList.value = []
    currentPage.value = 1
    await getSampleLibraries()
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '导入失败')
    importFileList.value = []
  }
}

// 组件挂载时获取数据
onMounted(() => {
  getSampleLibraries()
})
</script>

<style scoped>
.sample-library {
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

.sql-content {
  max-width: 400px;
  word-break: break-all;
  font-family: monospace;
  font-size: 14px;
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
