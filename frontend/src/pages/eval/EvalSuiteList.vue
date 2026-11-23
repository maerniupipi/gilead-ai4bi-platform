<template>
  <div class="eval-suite-list">
    <!-- 左侧文件夹 -->
    <aside class="folder-aside">
      <div class="folder-list">
        <div
          v-for="(f, idx) in flatFolders"
          :key="f.id"
          class="folder-row"
          :class="{ 'is-active': selectedFolderId === f.id }"
          :style="{ paddingLeft: (f.depth * 16 + 12) + 'px' }"
          @click="onSelectFolder(f.id)"
        >
          <div class="folder-row-main">
            <el-icon class="folder-item-icon"><Folder /></el-icon>
            <span class="folder-item-text">{{ f.name }}</span>
          </div>
          <el-dropdown trigger="click" @click.stop>
            <button type="button" class="folder-more-btn" aria-label="文件夹操作" @click.stop>
              <el-icon><MoreFilled /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="openRenameFolderDialog(f)">修改名称</el-dropdown-item>
                <el-dropdown-item :disabled="isFirstSibling(f)" @click="handleFolderMove(f, 'up')">上移</el-dropdown-item>
                <el-dropdown-item :disabled="isLastSibling(f)" @click="handleFolderMove(f, 'down')">下移</el-dropdown-item>
                <el-dropdown-item divided @click="handleFolderDelete(f)">删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div v-if="folders.length === 0" class="folder-empty">
          暂无文件夹
        </div>
      </div>
      <div class="folder-footer">
        <el-button class="folder-create-btn" plain @click="openCreateFolderDialog">创建文件夹</el-button>
      </div>
    </aside>

    <!-- 右侧主内容 -->
    <div class="suite-main">
      <PageHeader
        :breadcrumbs="[{ label: '评测中心' }, { label: '评测集' }]"
      >
        <template #actions>
          <el-button type="primary" @click="showCreateDialog">
            <Plus />
            新建评测集
          </el-button>
        </template>
      </PageHeader>
      <!-- 筛选栏 -->
      <div class="toolbar">
        <div class="toolbar-left">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索评测集..."
            style="width: 240px;"
            clearable
            @clear="loadSuites"
            @keyup.enter="loadSuites"
            class="search-input"
          >
            <template #prefix><Search /></template>
          </el-input>
        </div>
      </div>

      <!-- 列表 -->
      <div class="suite-table-wrap">
        <el-table
          v-loading="loading"
          :data="suites"
          stripe
          @row-click="handleRowClick"
          class="suite-table"
          :row-class-name="getRowClassName"
        >
          <el-table-column prop="name" label="评测集名称" min-width="200">
            <template #default="{ row }">
              <div class="suite-name-cell">
                <span class="suite-name">{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="suite-desc">{{ row.description || '暂无描述' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="case_count" label="用例数" width="100" align="center">
            <template #default="{ row }">
              <span class="case-count-badge">{{ row.case_count || 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="140">
            <template #default="{ row }">
              <span class="date-text">{{ formatDate(row.created_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" align="center">
            <template #default="{ row, $index }">
              <div class="op-actions">
                <button type="button" class="op-btn op-btn--edit" @click.stop="openEditDialog(row)">编辑</button>
                <button type="button" class="op-btn op-btn--share" @click.stop="handleShare(row)">分享</button>
                <button type="button" class="op-btn op-btn--delete" @click.stop="handleDelete(row)">删除</button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- 空状态 -->
        <div v-if="!loading && suites.length === 0" class="empty-state">
          <div class="empty-icon-wrap">
            <Folder style="width: 48px; height: 48px;" />
          </div>
          <p class="empty-text">暂无评测集</p>
          <p class="empty-hint">点击「新建评测集」开始创建</p>
        </div>
      </div>

      <!-- 分页 -->
      <div class="pagination-wrap" v-if="total > 0">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @current-change="loadSuites"
          @size-change="handleSizeChange"
        />
      </div>
    </div>

    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑评测集' : '新建评测集'"
      width="460px"
      destroy-on-close
      class="eval-dialog"
    >
      <el-form :model="form" label-position="top" ref="formRef" :rules="rules">
        <el-form-item label="评测集名称" prop="name">
          <el-input v-model="form.name" placeholder="输入评测集名称" maxlength="200" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="输入描述（可选）" maxlength="500" show-word-limit />
        </el-form-item>
        <el-form-item label="所属文件夹">
          <el-select v-model="form.folder_id" placeholder="选择文件夹（可选）" style="width: 100%;" clearable>
            <el-option v-for="f in flatFolders" :key="f.id" :label="f.name" :value="f.id"
              :style="{ paddingLeft: (f.depth * 16 + 8) + 'px' }" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false" class="cancel-btn">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave" class="confirm-btn">{{ isEditing ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <!-- 新建文件夹对话框 -->
    <el-dialog v-model="createFolderVisible" title="新建文件夹" width="380px" destroy-on-close class="eval-dialog">
      <el-form :model="folderForm" label-position="top">
        <el-form-item label="文件夹名称" prop="name">
          <el-input v-model="folderForm.name" placeholder="输入文件夹名称" maxlength="100" @keyup.enter="submitCreateFolder" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createFolderVisible = false" class="cancel-btn">取消</el-button>
        <el-button type="primary" :loading="createFolderLoading" @click="submitCreateFolder" class="confirm-btn">创建</el-button>
      </template>
    </el-dialog>

    <!-- 重命名文件夹对话框 -->
    <el-dialog v-model="renameFolderVisible" title="修改文件夹名称" width="380px" destroy-on-close class="eval-dialog">
      <el-form :model="renameFolderForm" label-position="top">
        <el-form-item label="文件夹名称">
          <el-input v-model="renameFolderForm.name" placeholder="输入文件夹名称" maxlength="100" @keyup.enter="submitRenameFolder" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameFolderVisible = false" class="cancel-btn">取消</el-button>
        <el-button type="primary" :loading="renameFolderLoading" @click="submitRenameFolder" class="confirm-btn">保存</el-button>
      </template>
    </el-dialog>

    <!-- 分享链接对话框 -->
    <el-dialog v-model="shareDialogVisible" title="分享评测集" width="520px" destroy-on-close class="eval-dialog">
      <div v-if="shareLoading" class="share-loading">生成中...</div>
      <div v-else-if="shareUrl" class="share-url-wrap">
        <p class="share-hint">将以下链接发送给他人，即可免登录查看评测集详情和任务结果：</p>
        <div class="share-url-row">
          <el-input v-model="shareUrl" readonly class="share-url-input" />
          <el-button type="primary" @click="copyShareUrl" class="copy-btn">复制</el-button>
        </div>
      </div>
      <template #footer>
        <el-button v-if="shareUrl" type="danger" text @click="handleRevokeShare">撤销分享</el-button>
        <el-button @click="shareDialogVisible = false" class="cancel-btn">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Folder, MoreFilled } from '@element-plus/icons-vue'
import { useSpaceContext } from '@/utils/spaceContext'
import * as evalApi from '@/api/eval'
import { buildEvalShareUrl } from '@/api/evalShare'

const router = useRouter()
const { currentSpace } = useSpaceContext()

// 数据
const suites = ref([])
const folders = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const searchKeyword = ref('')
const selectedFolderId = ref(null)
const loading = ref(false)
const saving = ref(false)

// 对话框
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const form = reactive({ name: '', description: '', folder_id: null })
const rules = {
  name: [{ required: true, message: '请输入评测集名称', trigger: 'blur' }],
}

// 文件夹
const createFolderVisible = ref(false)
const createFolderLoading = ref(false)
const folderForm = reactive({ name: '' })

// 重命名文件夹
const renameFolderVisible = ref(false)
const renameFolderLoading = ref(false)
const renamingFolderId = ref(null)
const renameFolderForm = reactive({ name: '' })

// 分享
const shareDialogVisible = ref(false)
const shareLoading = ref(false)
const shareUrl = ref('')
const shareSuiteId = ref(null)

// 拍平文件夹树
const flatFolders = computed(() => {
  return flattenFoldersTree(folders.value, 0)
})

function flattenFoldersTree(nodes, depth) {
  let result = []
  for (const node of nodes) {
    result.push({ ...node, depth })
    if (node.children && node.children.length) {
      result = result.concat(flattenFoldersTree(node.children, depth + 1))
    }
  }
  return result
}

// 获取同层级兄弟节点列表
function getSiblings(folder) {
  return flatFolders.value.filter(f => (f.parent_id || null) === (folder.parent_id || null))
}

function isFirstSibling(folder) {
  const siblings = getSiblings(folder)
  return siblings.length > 0 && siblings[0].id === folder.id
}

function isLastSibling(folder) {
  const siblings = getSiblings(folder)
  return siblings.length > 0 && siblings[siblings.length - 1].id === folder.id
}

// 加载评测集列表
async function loadSuites() {
  if (!currentSpace.value?.id) return
  loading.value = true
  try {
    const params = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    }
    if (selectedFolderId.value) params.folder_id = selectedFolderId.value
    if (searchKeyword.value) params.keyword = searchKeyword.value

    const data = await evalApi.getEvalSuites(currentSpace.value.id, params)
    suites.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error('加载评测集失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

// 加载文件夹树
async function loadFolders() {
  if (!currentSpace.value?.id) return
  try {
    const data = await evalApi.getEvalFolders(currentSpace.value.id)
    folders.value = data || []
    if (!selectedFolderId.value && folders.value.length > 0) {
      selectedFolderId.value = folders.value[0].id
    }
  } catch (e) {
    console.error('加载文件夹失败:', e)
  }
}

// 选择文件夹
function onSelectFolder(id) {
  selectedFolderId.value = id
  currentPage.value = 1
  loadSuites()
}

// 点击行 → 进入详情
function handleRowClick(row) {
  router.push(`/eval/suite/${row.id}`)
}

// 新建对话框
function showCreateDialog() {
  isEditing.value = false
  editingId.value = null
  form.name = ''
  form.description = ''
  form.folder_id = selectedFolderId.value || flatFolders.value[0]?.id || null
  dialogVisible.value = true
}

// 编辑对话框
function openEditDialog(row) {
  isEditing.value = true
  editingId.value = row.id
  form.name = row.name
  form.description = row.description || ''
  form.folder_id = row.folder_id
  dialogVisible.value = true
}

// 保存
async function handleSave() {
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const data = {
      name: form.name,
      description: form.description,
      folder_id: form.folder_id,
    }
    if (isEditing.value) {
      await evalApi.updateEvalSuite(currentSpace.value.id, editingId.value, data)
      ElMessage.success('保存成功')
    } else {
      await evalApi.createEvalSuite(currentSpace.value.id, data)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadSuites()
  } catch (e) {
    ElMessage.error((isEditing.value ? '保存' : '创建') + '失败: ' + (e.message || e))
  } finally {
    saving.value = false
  }
}

// 删除
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定要删除评测集「' + row.name + '」吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await evalApi.deleteEvalSuite(currentSpace.value.id, row.id)
    ElMessage.success('删除成功')
    loadSuites()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

// 分享
async function handleShare(row) {
  if (!currentSpace.value?.id) return
  shareSuiteId.value = row.id
  shareDialogVisible.value = true
  shareLoading.value = true
  shareUrl.value = ''
  try {
    const res = await evalApi.issueEvalShare(currentSpace.value.id, row.id)
    shareUrl.value = buildEvalShareUrl(res.token, res.share_public_base_url)
  } catch (e) {
    ElMessage.error('生成分享链接失败: ' + (e.message || e))
    shareDialogVisible.value = false
  } finally {
    shareLoading.value = false
  }
}

function copyShareUrl() {
  navigator.clipboard.writeText(shareUrl.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  }).catch(() => {
    ElMessage.error('复制失败，请手动复制')
  })
}

async function handleRevokeShare() {
  if (!currentSpace.value?.id || !shareSuiteId.value) return
  try {
    await ElMessageBox.confirm('撤销后，之前的分享链接将失效。确定要撤销吗？', '撤销分享', {
      confirmButtonText: '确定撤销',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await evalApi.revokeEvalShare(currentSpace.value.id, shareSuiteId.value)
    ElMessage.success('已撤销分享')
    shareUrl.value = ''
    shareDialogVisible.value = false
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('撤销失败: ' + (e.message || e))
  }
}

// 新建文件夹
function openCreateFolderDialog() {
  folderForm.name = ''
  createFolderVisible.value = true
}

async function submitCreateFolder() {
  if (!folderForm.name.trim()) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  createFolderLoading.value = true
  try {
    await evalApi.createEvalFolder(currentSpace.value.id, { name: folderForm.name })
    ElMessage.success('创建成功')
    createFolderVisible.value = false
    await loadFolders()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.message || e))
  } finally {
    createFolderLoading.value = false
  }
}

// 重命名文件夹
function openRenameFolderDialog(folder) {
  renamingFolderId.value = folder.id
  renameFolderForm.name = folder.name
  renameFolderVisible.value = true
}

async function submitRenameFolder() {
  if (!renameFolderForm.name.trim()) {
    ElMessage.warning('请输入文件夹名称')
    return
  }
  renameFolderLoading.value = true
  try {
    await evalApi.updateEvalFolder(currentSpace.value.id, renamingFolderId.value, { name: renameFolderForm.name })
    ElMessage.success('修改成功')
    renameFolderVisible.value = false
    await loadFolders()
  } catch (e) {
    ElMessage.error('修改失败: ' + (e.message || e))
  } finally {
    renameFolderLoading.value = false
  }
}

// 上移/下移文件夹
async function handleFolderMove(folder, direction) {
  try {
    await evalApi.moveEvalFolder(folder.id, currentSpace.value.id, { direction })
    await loadFolders()
  } catch (e) {
    ElMessage.error('移动失败: ' + (e.message || e))
  }
}

// 删除文件夹
async function handleFolderDelete(folder) {
  try {
    await ElMessageBox.confirm('确定要删除文件夹「' + folder.name + '」吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await evalApi.deleteEvalFolder(currentSpace.value.id, folder.id)
    ElMessage.success('删除成功')
    if (selectedFolderId.value === folder.id) {
      selectedFolderId.value = null
    }
    await loadFolders()
    loadSuites()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.message || e))
  }
}

function handleSizeChange(size) {
  pageSize.value = size
  currentPage.value = 1
  loadSuites()
}

function formatDate(d) {
  if (!d) return '--'
  return new Date(d).toLocaleDateString('zh-CN')
}

function getRowClassName({ row }) {
  return 'suite-row'
}

watch(
  () => currentSpace.value?.id,
  async (spaceId) => {
    if (!spaceId) return
    currentPage.value = 1
    await loadFolders()
    loadSuites()
  },
  { immediate: true }
)
</script>

<style scoped>
.eval-suite-list {
  display: flex;
  height: 100%;
  overflow: hidden;
  background: var(--bg-primary);
}

/* 文件夹侧边栏 — 匹配智能体模块样式 */
.folder-aside {
  width: 168px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-self: stretch;
  min-height: 0;
  max-height: 100%;
  overflow: hidden;
  border-right: 1px solid #e4e7ed;
  background: #f7f8fa;
}

.folder-list {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  padding: 8px 0;
}

.folder-row {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 6px 6px 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: #303133;
  transition: background 0.15s;
}

.folder-row:hover {
  background: rgba(61, 141, 130, 0.1);
}

.folder-row.is-active {
  background: #e8f4f1;
  color: #3d8d82;
  font-weight: 500;
}

.folder-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.folder-more-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #909399;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s;
}

.folder-more-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #606266;
}

.folder-row.is-active .folder-more-btn {
  color: #3d8d82;
}

.folder-item-icon {
  flex-shrink: 0;
}

.folder-item-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.folder-footer {
  flex-shrink: 0;
}

.folder-create-btn {
  margin: 12px;
  width: calc(100% - 24px);
}

.folder-empty {
  padding: 20px;
  text-align: center;
  font-size: 12px;
  color: #909399;
}

/* 主内容 */
.suite-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 20px 24px;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-shrink: 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-input :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px var(--border-color);
  transition: all 0.2s;
}

.search-input :deep(.el-input__wrapper:hover),
.search-input :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--el-color-primary);
}

.create-btn {
  border-radius: 8px;
  font-weight: 500;
}

/* 表格容器 */
.suite-table-wrap {
  flex: 1;
  overflow: auto;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
}

.suite-table {
  --el-table-border-color: transparent;
}

.suite-table :deep(.suite-row) {
  cursor: pointer;
  transition: background 0.15s;
}

.suite-table :deep(.suite-row:hover > td) {
  background: var(--bg-hover) !important;
}

.suite-table :deep(.el-table__header th) {
  background: var(--bg-primary) !important;
  font-weight: 600;
  font-size: 13px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.suite-table :deep(.el-table__body td) {
  font-size: 13px;
}

.suite-table :deep(.el-table__body .cell) {
  font-size: 13px;
}

.suite-name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.suite-name {
  font-weight: 500;
  color: var(--text-primary);
}

.suite-desc {
  color: var(--text-muted);
  font-size: 13px;
}

.case-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 600;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-radius: 12px;
}

.date-text {
  font-size: 13px;
  color: var(--text-muted);
}

.op-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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

.op-btn--edit,
.op-btn--share {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.op-btn--edit:hover,
.op-btn--share:hover {
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
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
}

.empty-icon-wrap {
  width: 80px;
  height: 80px;
  background: var(--el-color-primary-light-9);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-color-primary);
  margin-bottom: 16px;
}

.empty-text {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

/* 分页 */
.pagination-wrap {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
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
  padding: 0 20px 16px;
}

.cancel-btn {
  border-radius: 8px;
}

.confirm-btn {
  border-radius: 8px;
  font-weight: 500;
}

/* 分享 */
.share-loading {
  text-align: center;
  padding: 24px;
  color: #999;
}

.share-hint {
  font-size: 13px;
  color: #666;
  margin: 0 0 12px;
  line-height: 1.5;
}

.share-url-row {
  display: flex;
  gap: 8px;
}

.share-url-input {
  flex: 1;
}

.copy-btn {
  border-radius: 6px;
  flex-shrink: 0;
}
</style>
