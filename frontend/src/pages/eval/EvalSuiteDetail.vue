<template>
  <div class="suite-detail">
    <PageHeader :breadcrumbs="breadcrumbs">
    </PageHeader>

    <!-- 标签页 -->
    <div class="detail-tabs" v-loading="loadingSuite">
      <el-tabs v-model="activeTab" class="eval-tabs">
        <!-- 用例管理 -->
        <el-tab-pane label="用例管理" name="cases">
          <div class="tab-toolbar">
            <el-input
              v-model="caseKeyword"
              placeholder="搜索问题内容..."
              style="max-width: 200px; width: 100%"
              clearable
              @clear="loadCases"
              @keyup.enter="loadCases"
              class="search-input"
            >
              <template #prefix><Search /></template>
            </el-input>
            <el-select v-model="caseDifficulty" placeholder="难度" clearable style="max-width: 110px; width: 100%" @change="loadCases">
              <el-option label="简单" value="easy" />
              <el-option label="中等" value="medium" />
              <el-option label="困难" value="hard" />
            </el-select>
            <el-input
              v-model="caseCategory"
              placeholder="按分类筛选"
              style="max-width: 130px; width: 100%"
              clearable
              @clear="loadCases"
              @keyup.enter="loadCases"
            />
            <div class="toolbar-right">
              <el-button v-if="selectedCases.length > 0" type="danger" @click="handleBatchDelete" class="tool-btn">
                <Delete />
                批量删除 ({{ selectedCases.length }})
              </el-button>
              <el-button @click="handleExportCases" class="tool-btn">
                <Download />
                导出
              </el-button>
              <el-button @click="downloadTemplate" class="tool-btn">
                <Download />
                下载模板
              </el-button>
              <el-button @click="showImportDialog" class="tool-btn">
                <Upload />
                导入
              </el-button>
              <el-button type="primary" @click="openAddCase" class="tool-btn primary">
                <Plus />
                新增用例
              </el-button>
            </div>
          </div>

          <!-- 用例列表 -->
          <div class="cases-table-wrap">
            <el-table
              v-loading="loadingCases"
              :data="cases"
              stripe
              @row-dblclick="openEditCase"
              @selection-change="handleSelectionChange"
              class="cases-table"
            >
              <el-table-column type="selection" width="40" />
              <el-table-column prop="input_prompt" label="问题（输入）" min-width="280" show-overflow-tooltip />
              <el-table-column prop="expected_output" label="期望答案" min-width="200" show-overflow-tooltip />
              <el-table-column prop="expected_output_type" label="类型" width="90" align="center">
                <template #default="{ row }">
                  <span class="type-badge">{{ getTypeLabel(row.expected_output_type) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="difficulty" label="难度" width="80" align="center">
                <template #default="{ row }">
                  <span class="difficulty-badge" :class="row.difficulty">{{ getDifficultyLabel(row.difficulty) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="category" label="分类" width="120" show-overflow-tooltip />
              <el-table-column prop="remark" label="备注" min-width="180" show-overflow-tooltip />
              <el-table-column label="操作" width="150" align="center">
                <template #default="{ row, $index }">
                  <div class="op-actions">
                    <button type="button" class="op-btn op-btn--edit" @click="openEditCase(row)">编辑</button>
                    <button type="button" class="op-btn op-btn--delete" @click="deleteCase(row, $index)">删除</button>
                  </div>
                </template>
              </el-table-column>
            </el-table>

            <div v-if="!loadingCases && cases.length === 0" class="empty-table">
              <div class="empty-icon-wrap">
                <List />
              </div>
              <p>暂无用例，点击「新增用例」或「导入」开始</p>
            </div>
          </div>

          <!-- 分页 -->
          <div class="pagination-wrap" v-if="caseTotal > 0">
            <el-pagination
              v-model:current-page="casePage"
              :page-size="casePageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="caseTotal"
              layout="total, sizes, prev, pager, next"
              @current-change="loadCases"
              @size-change="handleCaseSizeChange"
            />
          </div>
        </el-tab-pane>

        <!-- 评测任务 -->
        <el-tab-pane label="评测任务" name="tasks">
          <div class="tab-toolbar">
            <span class="suite-hint">在「<router-link to="/eval/tasks">任务状态</router-link>」中管理所有评测任务的执行。</span>
          </div>
          <div class="cases-table-wrap">
            <el-table v-loading="loadingTasks" :data="suiteTasks" stripe class="cases-table">
              <el-table-column prop="name" label="任务名称" min-width="180" />
              <el-table-column prop="status" label="状态" width="100" align="center">
                <template #default="{ row }">
                  <span class="status-badge" :class="row.status">{{ getTaskStatusLabel(row.status) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="total_cases" label="用例数" width="80" align="center" />
              <el-table-column prop="passed_cases" label="通过" width="80" align="center" />
              <el-table-column label="通过率" width="90" align="center">
                <template #default="{ row }">
                  {{ row.completed_cases > 0 ? (row.passed_cases / row.completed_cases * 100).toFixed(1) + '%' : '--' }}
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="160">
                <template #default="{ row }">
                  {{ formatDate(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80" align="center">
                <template #default="{ row }">
                  <el-button text size="small" type="primary" @click="router.push(`/eval/task/${row.id}`)">详情</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div v-if="!loadingTasks && suiteTasks.length === 0" class="empty-table">
              <div class="empty-icon-wrap">
                <List />
              </div>
              <p>暂无评测任务</p>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 用例编辑对话框 -->
    <el-dialog v-model="caseDialogVisible" :title="editingCase ? '编辑用例' : '新增用例'" width="90%" style="max-width:580px" destroy-on-close class="eval-dialog">
      <el-form :model="caseForm" label-position="top" class="case-form">
        <el-form-item label="问题（输入）" required>
          <el-input v-model="caseForm.input_prompt" type="textarea" :rows="3" placeholder="输入测试问题的提示词" />
        </el-form-item>
        <el-form-item label="期望答案">
          <el-input v-model="caseForm.expected_output" type="textarea" :rows="3" placeholder="输入期望的输出答案" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="输出类型" style="flex:1;">
            <el-select v-model="caseForm.expected_output_type" style="width: 100%;">
              <el-option label="文本" value="text" />
              <el-option label="SQL" value="sql" />
              <el-option label="JSON" value="json" />
              <el-option label="数值" value="number" />
              <el-option label="布尔" value="boolean" />
            </el-select>
          </el-form-item>
          <el-form-item label="难度" style="flex:1;">
            <el-select v-model="caseForm.difficulty" style="width: 100%;">
              <el-option label="简单" value="easy" />
              <el-option label="中等" value="medium" />
              <el-option label="困难" value="hard" />
            </el-select>
          </el-form-item>
          <el-form-item label="分类" style="flex:1;">
            <el-input v-model="caseForm.category" placeholder="分类名称" />
          </el-form-item>
          <el-form-item label="备注" style="flex:1;">
            <el-input v-model="caseForm.remark" placeholder="备注信息" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="caseDialogVisible = false" class="cancel-btn">取消</el-button>
        <el-button type="primary" :loading="savingCase" @click="handleSaveCase" class="confirm-btn">保存</el-button>
      </template>
    </el-dialog>

    <!-- 导入对话框 -->
    <el-dialog v-model="importDialogVisible" title="导入用例" width="90%" style="max-width:520px" destroy-on-close class="eval-dialog">
      <el-tabs v-model="importTab" class="import-tabs">
        <el-tab-pane label="上传文件" name="file">
          <div class="import-mode-row">
            <el-radio-group v-model="importMode" size="small">
              <el-radio-button value="skip">跳过重复</el-radio-button>
              <el-radio-button value="overwrite">覆盖重复</el-radio-button>
              <el-radio-button value="insert">插入新用例</el-radio-button>
            </el-radio-group>
          </div>
          <el-upload
            ref="uploadRef"
            action="#"
            :auto-upload="false"
            :on-change="handleFileChange"
            :limit="1"
            accept=".xlsx,.csv,.json,.jsonl"
            :before-upload="beforeUpload"
            drag
            class="upload-zone"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="upload-text">拖拽文件到此处或 <em>点击上传</em></div>
            <div class="upload-hint">支持 .xlsx / .csv / .json / .jsonl，单文件不超过 10MB</div>
          </el-upload>
          <div v-if="importFile" class="import-confirm">
            <span class="import-file-name">{{ importFile.name }}</span>
            <el-button type="primary" size="small" @click="executeImport" :loading="importing" class="import-btn">确认导入</el-button>
          </div>
          <el-progress v-if="importProgress > 0" :percentage="importProgress" class="import-progress" />
        </el-tab-pane>
        <el-tab-pane label="粘贴数据" name="paste">
          <el-input v-model="pasteData" type="textarea" :rows="8" placeholder="每行一条问题，或粘贴 JSON 数组" />
          <el-button type="primary" @click="importFromPaste" :loading="importing" class="paste-import-btn">导入</el-button>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>

    <!-- 评测集编辑对话框 -->
    <el-dialog v-model="suiteDialogVisible" title="编辑评测集" width="90%" style="max-width:460px" destroy-on-close class="eval-dialog">
      <el-form ref="suiteFormRef" :model="suiteForm" :rules="suiteFormRules" label-position="top">
        <el-form-item label="评测集名称" prop="name">
          <el-input v-model="suiteForm.name" maxlength="200" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="suiteForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="suiteDialogVisible = false" class="cancel-btn">取消</el-button>
        <el-button type="primary" :loading="savingSuite" @click="handleSaveSuite" class="confirm-btn">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Download, Upload, UploadFilled, List, Delete } from '@element-plus/icons-vue'
import { useSpaceContext } from '@/utils/spaceContext'
import * as evalApi from '@/api/eval'

const route = useRoute()
const router = useRouter()
const { currentSpace } = useSpaceContext()

const suiteId = computed(() => parseInt(route.params.id))

const breadcrumbs = computed(() => [
  { label: '评测集', to: '/eval/suites' },
  { label: suite.value?.name || '加载中...' }
])

// 套信息
const suite = ref(null)
const loadingSuite = ref(true)
const activeTab = ref('cases')

// 用例相关
const cases = ref([])
const loadingCases = ref(false)
const caseTotal = ref(0)
const casePage = ref(1)
const casePageSize = ref(20)
const caseKeyword = ref('')
const caseDifficulty = ref('')
const caseCategory = ref('')
const caseDialogVisible = ref(false)
const editingCase = ref(null)
const savingCase = ref(false)
const selectedCases = ref([])
const caseForm = reactive({
  input_prompt: '',
  expected_output: '',
  expected_output_type: 'text',
  difficulty: 'medium',
  category: '',
  remark: '',
})

// 导入相关
const importDialogVisible = ref(false)
const importTab = ref('file')
const importFile = ref(null)
const importing = ref(false)
const pasteData = ref('')
const importMode = ref('skip')
const importProgress = ref(0)

// 任务相关
const suiteTasks = ref([])
const loadingTasks = ref(false)

// 评测集编辑
const suiteDialogVisible = ref(false)
const savingSuite = ref(false)
const suiteForm = reactive({ name: '', description: '' })
const suiteFormRef = ref(null)
const suiteFormRules = {
  name: [{ required: true, message: '请输入评测集名称', trigger: 'blur' }]
}

// 加载套信息
async function loadSuite() {
  if (!currentSpace.value?.id) return
  loadingSuite.value = true
  try {
    suite.value = await evalApi.getEvalSuite(currentSpace.value.id, suiteId.value)
  } catch (e) {
    ElMessage.error('加载评测集失败: ' + (e.message || e))
  } finally {
    loadingSuite.value = false
  }
}

// 加载用例
async function loadCases() {
  loadingCases.value = true
  try {
    const params = {
      skip: (casePage.value - 1) * casePageSize.value,
      limit: casePageSize.value,
    }
    if (caseKeyword.value) params.keyword = caseKeyword.value
    if (caseDifficulty.value) params.difficulty = caseDifficulty.value
    if (caseCategory.value) params.category = caseCategory.value
    const data = await evalApi.getEvalCases(suiteId.value, params)
    cases.value = (data.items || data || []).map(c => ({
      ...c,
      expected_output: c.ground_truths?.[0]?.ground_truth || '',
    }))
    caseTotal.value = data.total || 0
  } catch (e) {
    ElMessage.error('加载用例失败: ' + (e.message || e))
  } finally {
    loadingCases.value = false
  }
}

// 加载任务
async function loadTasks() {
  if (!currentSpace.value?.id) return
  loadingTasks.value = true
  try {
    const data = await evalApi.getEvalTasks(currentSpace.value.id, { suite_id: suiteId.value, limit: 100 })
    suiteTasks.value = data.items || data || []
  } catch (e) {
    console.error('加载任务失败:', e)
  } finally {
    loadingTasks.value = false
  }
}

// 新增用例
function openAddCase() {
  editingCase.value = null
  caseForm.input_prompt = ''
  caseForm.expected_output = ''
  caseForm.expected_output_type = 'text'
  caseForm.difficulty = 'medium'
  caseForm.category = ''
  caseForm.remark = ''
  caseDialogVisible.value = true
}

// 编辑用例
function openEditCase(row) {
  editingCase.value = row.id
  caseForm.input_prompt = row.input_prompt
  caseForm.expected_output = row.expected_output || ''
  caseForm.expected_output_type = row.expected_output_type || 'text'
  caseForm.difficulty = row.difficulty || 'medium'
  caseForm.category = row.category || ''
  caseForm.remark = row.remark || ''
  caseDialogVisible.value = true
}

// 保存用例
async function handleSaveCase() {
  if (!caseForm.input_prompt.trim()) {
    ElMessage.warning('请输入问题内容')
    return
  }
  savingCase.value = true
  try {
    const data = {
      input_prompt: caseForm.input_prompt,
      expected_output: caseForm.expected_output,
      expected_output_type: caseForm.expected_output_type,
      difficulty: caseForm.difficulty,
      category: caseForm.category,
      remark: caseForm.remark,
    }
    if (editingCase.value) {
      await evalApi.updateEvalCase(editingCase.value, suiteId.value, data)
    } else {
      await evalApi.createEvalCase(suiteId.value, data)
    }
    ElMessage.success('保存成功')
    caseDialogVisible.value = false
    loadCases()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    savingCase.value = false
  }
}

// 删除用例
async function deleteCase(row, index) {
  try {
    await ElMessageBox.confirm('确定要删除该用例吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await evalApi.deleteEvalCase(row.id, suiteId.value)
    ElMessage.success('删除成功')
    cases.value.splice(index, 1)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

// 下载模板
function downloadTemplate() {
  const headers = ['input_prompt', 'expected_answer', 'expected_output_type', 'difficulty', 'category', 'remark']
  const example = [
    '查询本月销售额最高的产品',
    'SELECT product_name, SUM(amount) FROM sales WHERE date >= "2024-01-01" GROUP BY product_name ORDER BY SUM(amount) DESC LIMIT 10',
    'sql', 'medium', '销售分析', '用于验证聚合排序',
  ]
  const csv = [headers.join(','), example.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = '评测用例模板.csv'
  a.click()
  URL.revokeObjectURL(url)
}

// 导入
function showImportDialog() {
  importFile.value = null
  pasteData.value = ''
  importTab.value = 'file'
  importDialogVisible.value = true
}

function handleFileChange(file) {
  importFile.value = file.raw
}

function beforeUpload(file) {
  const isLt10M = file.size / 1024 / 1024 < 10
  if (!isLt10M) {
    ElMessage.error('文件大小不能超过 10MB')
    return false
  }
  return true
}

function handleSelectionChange(selection) {
  selectedCases.value = selection
}

function handleCaseSizeChange(size) {
  casePageSize.value = size
  casePage.value = 1
  loadCases()
}

async function handleBatchDelete() {
  if (!selectedCases.value.length) return
  try {
    await ElMessageBox.confirm('确定要删除选中的 ' + selectedCases.value.length + ' 条用例吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    const ids = selectedCases.value.map(c => c.id)
    await evalApi.batchDeleteEvalCases(suiteId.value, ids)
    ElMessage.success('删除成功')
    selectedCases.value = []
    loadCases()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function handleExportCases() {
  if (!cases.value.length) {
    ElMessage.warning('暂无用例可导出')
    return
  }
  const headers = ['input_prompt', 'expected_answer', 'expected_output_type', 'difficulty', 'category', 'remark']
  const rows = cases.value.map(c => [
    c.input_prompt,
    c.expected_output || '',
    c.expected_output_type || 'text',
    c.difficulty || 'medium',
    c.category || '',
    c.remark || '',
  ])
  const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))].join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${suite.value?.name || '评测用例'}_导出.csv`
  a.click()
  URL.revokeObjectURL(url)
}

async function executeImport() {
  if (!importFile.value) return
  importing.value = true
  try {
    const text = await importFile.value.text()
    let cases = []
    const name = importFile.value.name.toLowerCase()
    if (name.endsWith('.json') || name.endsWith('.jsonl')) {
      try {
        cases = JSON.parse(text)
        if (!Array.isArray(cases)) cases = [cases]
      } catch {
        cases = text.split('\n').filter(l => l.trim()).map(l => JSON.parse(l))
      }
    } else {
      const lines = text.split('\n').filter(l => l.trim())
      const headers = lines[0]?.split(',').map(h => h.trim().replace(/^\ufeff/, '')) || []
      for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',')
        const row = {}
        headers.forEach((h, idx) => { row[h] = (values[idx] || '').trim() })
        if (row.input_prompt) {
          cases.push({
            input_prompt: row.input_prompt,
            expected_answer: row.expected_answer || row.expected_output || '',
            expected_output_type: row.expected_output_type || 'text',
            difficulty: row.difficulty || 'medium',
            category: row.category || '',
            remark: row.remark || '',
          })
        }
      }
    }
    if (!cases.length) {
      ElMessage.warning('未能解析到有效数据')
      importing.value = false
      return
    }
    importProgress.value = 30
    const result = await evalApi.executeImport(suiteId.value, { cases, import_mode: importMode.value })
    importProgress.value = 100
    const msgs = []
    if (result.created_count > 0) msgs.push(`新增 ${result.created_count}`)
    if (result.updated_count > 0) msgs.push(`更新 ${result.updated_count}`)
    if (result.skipped_count > 0) msgs.push(`跳过 ${result.skipped_count}`)
    ElMessage.success(msgs.join('，') || '导入完成')
    importDialogVisible.value = false
    importProgress.value = 0
    loadCases()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.message || e))
    importProgress.value = 0
  } finally {
    importing.value = false
  }
}

async function importFromPaste() {
  if (!pasteData.value.trim()) return
  importing.value = true
  try {
    let cases = []
    const text = pasteData.value.trim()
    try {
      cases = JSON.parse(text)
      if (!Array.isArray(cases)) cases = [cases]
    } catch {
      cases = text.split('\n').filter(l => l.trim()).map(line => ({
        input_prompt: line.trim(),
        expected_answer: '',
        expected_output_type: 'text',
        difficulty: 'medium',
      }))
    }
    const result = await evalApi.executeImport(suiteId.value, { cases, import_mode: importMode.value })
    const msgs = []
    if (result.created_count > 0) msgs.push(`新增 ${result.created_count}`)
    if (result.updated_count > 0) msgs.push(`更新 ${result.updated_count}`)
    if (result.skipped_count > 0) msgs.push(`跳过 ${result.skipped_count}`)
    ElMessage.success(msgs.join('，') || '导入完成')
    importDialogVisible.value = false
    loadCases()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.message || e))
  } finally {
    importing.value = false
  }
}

// 评测集编辑
function openEditSuite() {
  suiteForm.name = suite.value?.name || ''
  suiteForm.description = suite.value?.description || ''
  suiteDialogVisible.value = true
}

async function handleSaveSuite() {
  if (suiteFormRef.value) {
    try {
      await suiteFormRef.value.validate()
    } catch {
      return
    }
  }
  if (!currentSpace.value?.id) return
  savingSuite.value = true
  try {
    await evalApi.updateEvalSuite(currentSpace.value.id, suiteId.value, {
      name: suiteForm.name,
      description: suiteForm.description,
    })
    ElMessage.success('保存成功')
    suiteDialogVisible.value = false
    loadSuite()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.message || e))
  } finally {
    savingSuite.value = false
  }
}

// 辅助
function formatDate(d) {
  if (!d) return '--'
  return new Date(d).toLocaleDateString('zh-CN')
}

function getTypeLabel(t) {
  const m = { text: '文本', sql: 'SQL', json: 'JSON', number: '数值', boolean: '布尔' }
  return m[t] || t || '--'
}

function getDifficultyLabel(d) {
  return { easy: '简单', medium: '中等', hard: '困难' }[d] || d || '--'
}

function getDifficultyType(d) {
  return { easy: 'success', medium: 'warning', hard: 'danger' }[d] || 'info'
}

function getTaskStatusType(s) {
  return { completed: 'success', running: 'primary', failed: 'danger', cancelled: 'info', draft: 'info' }[s] || 'info'
}

function getTaskStatusLabel(s) {
  return { completed: '已完成', running: '运行中', failed: '失败', cancelled: '已取消', draft: '草稿', pending: '等待中', paused: '已暂停' }[s] || s
}

onMounted(() => {
  loadSuite()
  loadCases()
  loadTasks()
})
</script>

<style scoped>
.suite-detail {
  width: 100%;
  max-width: none;
  padding: 20px clamp(12px, 2vw, 28px);
  box-sizing: border-box;
}

/* 面包屑 */
.detail-tabs {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 0 clamp(12px, 1.5vw, 20px) 20px;
  overflow: hidden;
}

.eval-tabs :deep(.el-tabs__header) {
  margin: 0 0 16px;
}

.eval-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
}

.eval-tabs :deep(.el-tabs__item) {
  font-size: 14px;
  font-weight: 500;
  padding: 0 16px;
  height: 44px;
  line-height: 44px;
}

.eval-tabs :deep(.el-tabs__item.is-active) {
  color: var(--el-color-primary);
}

.eval-tabs :deep(.el-tabs__active-bar) {
  height: 2px;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.toolbar-right {
  margin-left: auto;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.search-input :deep(.el-input__wrapper) {
  border-radius: 8px;
}

.tool-btn {
  border-radius: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.tool-btn.primary {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}

.suite-hint {
  font-size: 13px;
  color: var(--text-muted);
}

.suite-hint a {
  color: var(--el-color-primary);
}

/* 表格 */
.cases-table-wrap {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 12px;
  width: 100%;
}

.cases-table :deep(.el-table__header th) {
  background: var(--bg-primary) !important;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.cases-table :deep(.el-table__body td) {
  font-size: 13px;
}

.cases-table :deep(.el-table__body .cell) {
  font-size: 13px;
}

.type-badge {
  display: inline-flex;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  background: var(--bg-primary);
  color: var(--text-secondary);
  border-radius: 4px;
  border: 1px solid var(--border-color);
}

.difficulty-badge {
  display: inline-flex;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 10px;
}

.difficulty-badge.easy {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.difficulty-badge.medium {
  background: rgba(230, 162, 60, 0.1);
  color: #e6a23c;
}

.difficulty-badge.hard {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.status-badge {
  display: inline-flex;
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 10px;
}

.status-badge.completed {
  background: rgba(103, 194, 58, 0.1);
  color: #67c23a;
}

.status-badge.running {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.status-badge.failed {
  background: rgba(245, 108, 108, 0.1);
  color: #f56c6c;
}

.status-badge.draft,
.status-badge.pending {
  background: var(--bg-primary);
  color: var(--text-muted);
}

.op-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.op-btn {
  border: none;
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  transition:
    background-color 0.2s,
    color 0.2s,
    transform 0.15s;
}

.op-btn:active {
  transform: translateY(1px);
}

.op-btn--edit {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.op-btn--edit:hover {
  color: #fff;
  background: var(--el-color-primary);
}

.op-btn--delete {
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.op-btn--delete:hover {
  color: #fff;
  background: var(--el-color-danger);
}

/* 空状态 */
.empty-table {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 40px;
  color: var(--text-muted);
  font-size: 14px;
}

.empty-icon-wrap {
  width: 64px;
  height: 64px;
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-color-primary);
  margin-bottom: 12px;
}

.empty-table p {
  margin: 0;
}

/* 分页 */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
}

.cases-table {
  width: 100%;
}

/* 用例表单 */
.case-form :deep(.el-form-item__label) {
  font-weight: 500;
  font-size: 13px;
}

.case-form :deep(.el-form-item) {
  margin-bottom: 14px;
}

.form-row {
  display: flex;
  gap: 8px;
}

.form-row :deep(.el-form-item__label) {
  font-size: 13px;
}

/* 导入对话框 */
.import-mode-row {
  margin-bottom: 12px;
}

.import-progress {
  margin-top: 12px;
}

.upload-zone {
  width: 100%;
  margin-bottom: 12px;
}

.upload-zone :deep(.el-upload-dragger) {
  padding: 32px 20px;
  border-radius: 10px;
  border: 2px dashed var(--border-color);
  background: var(--bg-primary);
  transition: all 0.2s;
}

.upload-zone :deep(.el-upload-dragger:hover) {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.upload-icon {
  font-size: 32px;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.upload-text {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.upload-text em {
  color: var(--el-color-primary);
  font-style: normal;
  cursor: pointer;
}

.upload-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.import-confirm {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-primary);
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.import-file-name {
  font-size: 13px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 240px;
}

.import-btn {
  border-radius: 6px;
}

.paste-import-btn {
  margin-top: 12px;
  width: 100%;
  border-radius: 8px;
}

/* 对话框 */
.eval-dialog :deep(.el-dialog__header) {
  padding: 20px 24px 0;
  margin: 0;
}

.eval-dialog :deep(.el-dialog__body) {
  padding: 16px 20px;
}

.eval-dialog :deep(.el-dialog__title) {
  font-size: 16px;
}

.eval-dialog :deep(.el-form-item__label) {
  font-size: 13px;
}

.eval-dialog :deep(.el-dialog__footer) {
  padding: 0 24px 20px;
}

.cancel-btn {
  border-radius: 8px;
}

.confirm-btn {
  border-radius: 8px;
  font-weight: 500;
}

/* 响应式 */
@media screen and (max-width: 768px) {
  .suite-detail {
    padding: 12px;
  }

  .detail-tabs {
    padding: 0 12px 12px;
  }

  .tab-toolbar {
    gap: 8px;
  }

  .tab-toolbar .search-input,
  .tab-toolbar .el-select,
  .tab-toolbar .el-input {
    width: 100% !important;
  }

  .toolbar-right {
    margin-left: 0;
    width: 100%;
    flex-wrap: wrap;
  }

  .toolbar-right .tool-btn {
    flex: 1 1 calc(50% - 6px);
    min-width: 120px;
    justify-content: center;
  }

  .cases-table-wrap {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .cases-table {
    min-width: 880px;
  }

  .pagination-wrap {
    justify-content: center;
  }

  .pagination-wrap :deep(.el-pagination) {
    flex-wrap: wrap;
    justify-content: center;
  }

  .form-row {
    flex-direction: column;
    gap: 0;
  }

  .import-confirm {
    flex-direction: column;
    gap: 8px;
    align-items: stretch;
  }

  .import-file-name {
    max-width: none;
  }

  .eval-dialog :deep(.el-dialog__header) {
    padding: 16px 16px 0;
  }

  .eval-dialog :deep(.el-dialog__body) {
    padding: 12px 12px;
  }

  .eval-dialog :deep(.el-dialog__footer) {
    padding: 0 16px 16px;
  }
}

@media screen and (max-width: 576px) {
  .eval-tabs :deep(.el-tabs__item) {
    padding: 0 10px;
    font-size: 13px;
  }

  .toolbar-right .tool-btn {
    flex: 1 1 100%;
  }

  .suite-hint {
    font-size: 12px;
    line-height: 1.5;
  }
}
</style>
