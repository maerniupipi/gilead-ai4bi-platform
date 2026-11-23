<template>
  <div class="knowledge-base-ner">
    <PageHeader
      :breadcrumbs="[{ label: '知识库列表', to: '/knowledge-base' }, { label: `NER 映射 — ${knowledgeBaseName}` }]"
    />

    <el-card shadow="never" class="ner-main-card">
      <template #header>
        <div class="card-header">
          <div class="card-title-block">
            <span class="card-title">NER 映射</span>
            <span class="card-sub">
              本知识库共 <strong>{{ totalNerCount }}</strong> / {{ NER_MAX }} 条
            </span>
          </div>
          <div class="ner-toolbar">
            <el-input
              v-model="searchKeyword"
              clearable
              placeholder="搜索当前 Sheet 内数据"
              class="ner-search"
              :disabled="!!editingId"
              @keyup.enter="runSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button type="primary" :disabled="!!editingId || totalNerCount >= NER_MAX" @click="handleAdd">
              <el-icon><Plus /></el-icon>
              新增
            </el-button>
            <el-button :disabled="!!editingId" @click="openImportDialog">
              <el-icon><Upload /></el-icon>
              导入
            </el-button>
            <el-button type="success" plain :disabled="!!editingId" @click="handleExport">
              <el-icon><Download /></el-icon>
              导出
            </el-button>
          </div>
        </div>
      </template>

      <div class="ner-master-detail">
        <!-- 左侧：对应 Excel Sheet -->
        <aside class="sheet-list-panel">
          <div class="sheet-list-head">Sheet 列表</div>
          <div class="sheet-list">
            <div
              v-for="s in sheets"
              :key="s.sheet_name"
              class="sheet-item"
              :class="{ active: s.sheet_name === selectedSheetName }"
              @click="selectSheet(s.sheet_name)"
            >
              <div class="sheet-name">{{ s.sheet_name }}</div>
              <div class="sheet-meta">共 {{ s.row_count }} 条</div>
              <div class="sheet-actions-small">
                <el-button type="danger" size="small" :disabled="!!editingId" @click.stop="handleDeleteSheet(s)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
            </div>
            <div v-if="sheets.length === 0" class="sheet-empty-hint">
              暂无 Sheet，请先<strong>导入</strong>或点击<strong>新增</strong>（将使用「默认」）
            </div>
          </div>
        </aside>

        <!-- 右侧：当前 Sheet 下表格 + 分页 -->
        <div class="ner-detail-panel">
          <div v-if="!selectedSheetName" class="no-selection">
            请选择左侧 Sheet；若无数据可先导入或新增
          </div>
          <template v-else>
            <div class="detail-head">
              <span class="detail-title">Sheet「{{ selectedSheetName }}」</span>
            </div>
            <div class="ner-table-wrap" v-loading="loading">
              <el-table :data="displayRows" border stripe class="ner-table" row-key="id">
                <el-table-column prop="table_name" label="表名" min-width="110">
                  <template #default="{ row }">
                    <el-input
                      v-if="isRowEditing(row)"
                      v-model="draft.table_name"
                      size="small"
                      :maxlength="NER_FIELD_MAX"
                      placeholder="表名"
                    />
                    <span v-else>{{ row.table_name }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="field_name" label="字段名" min-width="100">
                  <template #default="{ row }">
                    <el-input
                      v-if="isRowEditing(row)"
                      v-model="draft.field_name"
                      size="small"
                      :maxlength="NER_FIELD_MAX"
                      placeholder="字段名"
                    />
                    <span v-else>{{ row.field_name }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="standard_name" label="标准名称（数据库字段值）" min-width="160">
                  <template #default="{ row }">
                    <el-input
                      v-if="isRowEditing(row)"
                      v-model="draft.standard_name"
                      size="small"
                      :maxlength="NER_FIELD_MAX"
                      placeholder="标准值"
                    />
                    <span v-else>{{ row.standard_name }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="alias" label="别名" min-width="90">
                  <template #default="{ row }">
                    <el-input
                      v-if="isRowEditing(row)"
                      v-model="draft.alias"
                      size="small"
                      :maxlength="NER_FIELD_MAX"
                      placeholder="别名"
                    />
                    <span v-else>{{ row.alias }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip>
                  <template #default="{ row }">
                    <el-input
                      v-if="isRowEditing(row)"
                      v-model="draft.remark"
                      size="small"
                      :maxlength="NER_FIELD_MAX"
                      placeholder="备注"
                    />
                    <span v-else>{{ row.remark }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="140" fixed="right" align="center">
                  <template #default="{ row }">
                    <template v-if="isRowEditing(row)">
                      <el-button type="primary" size="small" link @click="handleConfirmEdit(row)">确认</el-button>
                      <el-button size="small" link @click="handleCancelEdit(row)">取消</el-button>
                    </template>
                    <template v-else>
                      <el-button
                        type="primary"
                        size="small"
                        link
                        :disabled="!!editingId"
                        @click="handleModify(row)"
                      >
                        修改
                      </el-button>
                      <el-button
                        type="danger"
                        size="small"
                        link
                        :disabled="!!editingId"
                        @click="handleDeleteRow(row)"
                      >
                        删除
                      </el-button>
                    </template>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <div class="ner-pagination" v-if="selectedSheetName && !pendingRow">
              <el-pagination
                v-model:current-page="page"
                v-model:page-size="pageSize"
                :page-sizes="[10, 20, 50]"
                layout="total, sizes, prev, pager, next"
                :total="total"
                background
                @current-change="fetchRows"
                @size-change="onPageSizeChange"
              />
            </div>
          </template>
        </div>
      </div>
    </el-card>

    <el-dialog
      v-model="importDialogVisible"
      title="导入 NER 映射"
      width="540px"
      destroy-on-close
      @closed="onImportDialogClosed"
    >
      <el-form label-position="top">
        <el-form-item label="导入方式" required>
          <el-radio-group v-model="importMode">
            <el-radio label="replace_all">全量覆盖（清空本知识库全部 NER 后写入文件）</el-radio>
            <el-radio label="append">批量新增（在现有数据后追加）</el-radio>
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
          支持 .xlsx、.xlsm；将读取<strong>所有工作表</strong>中的数据行（首行表头会自动跳过）。每个数据格最多
          <strong>{{ NER_FIELD_MAX }}</strong>
          个字符，超出部分在导入时截断；单个知识库累计不超过 <strong>{{ NER_MAX }}</strong> 条。
        </p>
      </div>
      <template #footer>
        <el-button @click="importDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Upload, Download, Delete } from '@element-plus/icons-vue'
import knowledgeBaseApi from '@/api/knowledgeBase'
import {
  downloadNerTemplate,
  downloadNerExportFromApiRows,
  parseNerWorkbookArrayBuffer,
  nerParsedToApiRows,
  clipCell,
  NER_CELL_MAX
} from '@/utils/kbNerExcel'

const route = useRoute()

const NER_MAX = 1000
const NER_FIELD_MAX = NER_CELL_MAX

const knowledgeBaseId = computed(() => {
  const v = route.query.knowledgeBaseId
  const n = parseInt(String(v), 10)
  return Number.isFinite(n) ? n : null
})
const knowledgeBaseName = computed(() => route.query.knowledgeBaseName || '当前知识库')

const sheets = ref([])
const selectedSheetName = ref('')
const serverRows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const loading = ref(false)

const editingId = ref(null)
const pendingRow = ref(null)
const draft = reactive({
  table_name: '',
  field_name: '',
  standard_name: '',
  alias: '',
  remark: ''
})

const importDialogVisible = ref(false)
const importMode = ref('append')
const importFileList = ref([])

const totalNerCount = computed(() =>
  sheets.value.reduce((acc, s) => acc + (s.row_count || 0), 0)
)

const displayRows = computed(() => {
  if (pendingRow.value) {
    return [pendingRow.value, ...serverRows.value]
  }
  return serverRows.value
})

function isRowEditing(row) {
  if (pendingRow.value && row === pendingRow.value) return true
  return editingId.value != null && row.id === editingId.value
}

function resetDraft() {
  draft.table_name = ''
  draft.field_name = ''
  draft.standard_name = ''
  draft.alias = ''
  draft.remark = ''
}

async function fetchSheets() {
  if (knowledgeBaseId.value == null) return
  try {
    sheets.value = await knowledgeBaseApi.listNerSheets(knowledgeBaseId.value)
    if (
      selectedSheetName.value &&
      !sheets.value.some((s) => s.sheet_name === selectedSheetName.value)
    ) {
      selectedSheetName.value = sheets.value[0]?.sheet_name || ''
    } else if (!selectedSheetName.value && sheets.value.length > 0) {
      selectedSheetName.value = sheets.value[0].sheet_name
    }
  } catch (e) {
    ElMessage.error('加载 Sheet 列表失败：' + (e.response?.data?.detail || e.message))
  }
}

async function fetchRows() {
  if (knowledgeBaseId.value == null || !selectedSheetName.value) {
    serverRows.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const res = await knowledgeBaseApi.listNerRows(knowledgeBaseId.value, {
      sheet_name: selectedSheetName.value,
      q: searchKeyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value
    })
    serverRows.value = res.items || []
    total.value = res.total ?? 0
  } catch (e) {
    ElMessage.error('加载数据失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function selectSheet(name) {
  if (editingId.value) {
    ElMessage.warning('请先确认或取消当前编辑')
    return
  }
  pendingRow.value = null
  selectedSheetName.value = name
  page.value = 1
  fetchRows()
}

function onPageSizeChange() {
  page.value = 1
  fetchRows()
}

function runSearch() {
  if (editingId.value) return
  page.value = 1
  fetchRows()
}

let searchTimer = null
watch(searchKeyword, () => {
  if (editingId.value) return
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    fetchRows()
  }, 400)
})

watch(page, () => {
  if (pendingRow.value) {
    pendingRow.value = null
    editingId.value = null
    resetDraft()
  }
})

async function handleAdd() {
  if (editingId.value) {
    ElMessage.warning('请先确认或取消当前编辑')
    return
  }
  if (totalNerCount.value >= NER_MAX) {
    ElMessage.warning(`单知识库 NER 不能超过 ${NER_MAX} 条`)
    return
  }
  if (knowledgeBaseId.value == null) {
    ElMessage.error('缺少知识库 ID')
    return
  }
  await fetchSheets()
  let sheet = selectedSheetName.value
  if (!sheet) {
    sheet = sheets.value[0]?.sheet_name || '默认'
    selectedSheetName.value = sheet
    await fetchRows()
  }
  pendingRow.value = {
    id: 'pending',
    _local: true,
    sheet_name: sheet,
    table_name: '',
    field_name: '',
    standard_name: '',
    alias: '',
    remark: ''
  }
  editingId.value = 'pending'
  resetDraft()
}

function handleModify(row) {
  if (row._local) return
  editingId.value = row.id
  draft.table_name = row.table_name || ''
  draft.field_name = row.field_name || ''
  draft.standard_name = row.standard_name || ''
  draft.alias = row.alias || ''
  draft.remark = row.remark || ''
}

async function handleConfirmEdit(row) {
  if (knowledgeBaseId.value == null) return
  const t = clipCell(draft.table_name)
  const f = clipCell(draft.field_name)
  if (!t || !f) {
    ElMessage.warning('请填写表名与字段名')
    return
  }
  const body = {
    sheet_name: selectedSheetName.value,
    table_name: t,
    field_name: f,
    standard_name: clipCell(draft.standard_name),
    alias: clipCell(draft.alias),
    remark: clipCell(draft.remark)
  }
  try {
    if (row._local || row.id === 'pending') {
      await knowledgeBaseApi.createNerRow(knowledgeBaseId.value, body)
      ElMessage.success('已新增')
    } else {
      await knowledgeBaseApi.updateNerRow(knowledgeBaseId.value, row.id, body)
      ElMessage.success('已保存')
    }
    pendingRow.value = null
    editingId.value = null
    resetDraft()
    await fetchSheets()
    await fetchRows()
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '保存失败')
  }
}

function handleCancelEdit(row) {
  if (row._local || row.id === 'pending') {
    pendingRow.value = null
  }
  editingId.value = null
  resetDraft()
}

async function handleDeleteRow(row) {
  if (row._local || knowledgeBaseId.value == null) return
  try {
    await ElMessageBox.confirm('确定删除该条记录吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await knowledgeBaseApi.deleteNerRow(knowledgeBaseId.value, row.id)
    ElMessage.success('已删除')
    await fetchSheets()
    await fetchRows()
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '删除失败')
  }
}

async function handleDeleteSheet(s) {
  if (editingId.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除整个 Sheet「${s.sheet_name}」下的全部 ${s.row_count} 条记录吗？`,
      '警告',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await knowledgeBaseApi.deleteNerSheet(knowledgeBaseId.value, s.sheet_name)
    ElMessage.success('已清空该 Sheet')
    if (selectedSheetName.value === s.sheet_name) {
      selectedSheetName.value = ''
    }
    await fetchSheets()
    if (sheets.value.length > 0) {
      selectedSheetName.value = sheets.value[0].sheet_name
    }
    await fetchRows()
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '删除失败')
  }
}

async function handleExport() {
  if (knowledgeBaseId.value == null) return
  try {
    const rows = await knowledgeBaseApi.exportNerRows(knowledgeBaseId.value)
    const name = `NER导出_${knowledgeBaseName.value}_${new Date().toISOString().slice(0, 10)}`
    await downloadNerExportFromApiRows(rows, name)
    if (!rows || rows.length === 0) {
      ElMessage.info('当前无数据，已下载模板文件')
    } else {
      ElMessage.success('导出成功')
    }
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '导出失败')
  }
}

function openImportDialog() {
  importMode.value = 'append'
  importDialogVisible.value = true
}

function onImportDialogClosed() {
  importFileList.value = []
}

async function handleDownloadTemplate() {
  await downloadNerTemplate()
  ElMessage.success('模板已下载')
}

async function onImportFilePick(uploadFile) {
  const raw = uploadFile.raw
  if (!raw || knowledgeBaseId.value == null) return
  const lower = raw.name.toLowerCase()
  if (!lower.endsWith('.xlsx') && !lower.endsWith('.xlsm')) {
    ElMessage.error('请上传 .xlsx 或 .xlsm')
    importFileList.value = []
    return
  }
  try {
    const buf = await raw.arrayBuffer()
    const parsed = await parseNerWorkbookArrayBuffer(buf)
    const apiRows = nerParsedToApiRows(parsed).filter(
      (r) =>
        r.table_name ||
        r.field_name ||
        r.standard_name ||
        r.alias ||
        r.remark
    )
    if (apiRows.length === 0) {
      ElMessage.warning('未解析到有效数据')
      importFileList.value = []
      return
    }
    if (importMode.value === 'append') {
      if (totalNerCount.value + apiRows.length > NER_MAX) {
        ElMessage.error(
          `批量新增后将超过 ${NER_MAX} 条（当前 ${totalNerCount.value}，文件 ${apiRows.length} 条）`
        )
        importFileList.value = []
        return
      }
    } else if (apiRows.length > NER_MAX) {
      ElMessage.error(`全量覆盖单次不能超过 ${NER_MAX} 条`)
      importFileList.value = []
      return
    }
    const res = await knowledgeBaseApi.importNerRows(knowledgeBaseId.value, {
      mode: importMode.value,
      rows: apiRows
    })
    ElMessage.success(res.message || '导入成功')
    importDialogVisible.value = false
    importFileList.value = []
    await fetchSheets()
    if (!selectedSheetName.value && sheets.value.length > 0) {
      selectedSheetName.value = sheets.value[0].sheet_name
    }
    page.value = 1
    await fetchRows()
  } catch (e) {
    ElMessage.error((e.response?.data?.detail || e.message) || '导入失败')
    importFileList.value = []
  }
}

watch(
  () => route.query.knowledgeBaseId,
  async () => {
    editingId.value = null
    pendingRow.value = null
    resetDraft()
    selectedSheetName.value = ''
    page.value = 1
    await fetchSheets()
    await fetchRows()
  }
)

onMounted(async () => {
  await fetchSheets()
  await fetchRows()
})
</script>

<style scoped>
.knowledge-base-ner {
  padding: 20px;
}

.card-header {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.card-title-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-title {
  font-weight: 500;
  color: #303133;
}

.card-sub {
  font-size: 12px;
  color: #909399;
}

.ner-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.ner-search {
  width: 260px;
}

.ner-main-card {
  border: 1px solid #e4e7ed;
}

.ner-master-detail {
  display: flex;
  gap: 20px;
  min-height: calc(100vh - 320px);
}

.sheet-list-panel {
  flex: none;
  width: 200px;
  border-right: 1px solid #eee;
  padding-right: 12px;
  display: flex;
  flex-direction: column;
}

.sheet-list-head {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 10px;
}

.sheet-list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.sheet-item {
  padding: 12px;
  border-bottom: 1px solid #eee;
  cursor: pointer;
  transition: background-color 0.2s;
}

.sheet-item:hover {
  background-color: #f5f7fa;
}

.sheet-item.active {
  background-color: var(--el-color-primary-light-9);
  border-right: 3px solid var(--el-color-primary);
}

.sheet-name {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}

.sheet-meta {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.sheet-actions-small {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.sheet-empty-hint {
  padding: 16px 12px;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}

.ner-detail-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.detail-head {
  margin-bottom: 12px;
}

.detail-title {
  font-weight: 500;
  color: #303133;
}

.no-selection {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 240px;
  color: #909399;
  background: #f5f7fa;
  border-radius: 4px;
  border: 1px dashed #dcdfe6;
}

.ner-table-wrap {
  flex: 1;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  overflow: hidden;
  min-height: 200px;
}

.ner-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.import-steps {
  margin-top: 8px;
}

.import-step {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 18px;
}

.import-step-label {
  font-size: 13px;
  font-weight: 500;
  color: #606266;
}

.import-step-btn {
  align-self: flex-start;
}

.import-upload {
  display: block;
}

.import-footnote {
  margin: 4px 0 0;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.65;
  color: #909399;
  background: #f5f7fa;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
</style>
