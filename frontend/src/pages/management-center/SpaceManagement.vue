<template>
  <div class="space-management">
    <PageHeader
      :breadcrumbs="[{ label: '空间管理' }]"
    />

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>空间列表</span>
          <el-button type="primary" @click="handleCreate">
            <el-icon><Plus /></el-icon>
            创建空间
          </el-button>
        </div>
      </template>

      <el-table :data="spaceList" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="150">
          <template #default="scope">
            <span class="space-name">{{ scope.row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="编码" width="120" />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="scope">
            <el-tag :type="scope.row.is_active ? 'success' : 'info'" size="small">
              {{ scope.row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="成员数" width="100">
          <template #default="scope">
            <span>{{ scope.row.member_count || 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="删除状态" width="120">
          <template #default="scope">
            <el-tag v-if="canPermanentlyDelete(scope.row)" type="warning" size="small">可彻底删除</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right" align="center">
          <template #default="scope">
            <el-button type="primary" size="small" link @click="handleEdit(scope.row)">编辑</el-button>
            <el-button type="primary" size="small" link @click="handleMembers(scope.row)">成员管理</el-button>
            <el-button v-if="canPermanentlyDelete(scope.row)" type="warning" size="small" link @click="handleCancelDelete(scope.row)">取消删除</el-button>
            <el-button type="danger" size="small" link @click="handleDelete(scope.row)" :disabled="isDeleteDisabled(scope.row)">
              {{ deleteActionText(scope.row) }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'create' ? '创建空间' : '编辑空间'"
      width="500px"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入空间名称" maxlength="100" />
        </el-form-item>
        <el-form-item label="编码" prop="code">
          <el-input v-model="form.code" placeholder="请输入唯一编码" maxlength="50" :disabled="dialogType === 'edit'" />
          <div class="form-tip">编码只能包含字母、数字和下划线</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="可选，空间描述" maxlength="500" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" :disabled="form.id === 1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>

    <!-- 成员管理对话框 -->
    <el-dialog
      v-model="membersDialogVisible"
      :title="'成员管理 - ' + currentSpace?.name"
      width="650px"
    >
      <div class="members-header">
        <el-button type="primary" size="small" @click="handleAddMember">
          <el-icon><Plus /></el-icon>
          添加成员
        </el-button>
      </div>
      <el-table :data="memberList" stripe style="width: 100%; margin-top: 8px;" max-height="400">
        <el-table-column prop="user_id" label="用户ID" width="70" />
        <el-table-column prop="display_name" label="用户名" min-width="120">
          <template #default="scope">
            <span>{{ scope.row.display_name || `用户${scope.row.user_id}` }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.role === 'owner'" type="warning" size="small">所有者</el-tag>
            <el-select
              v-else
              v-model="scope.row.role"
              size="small"
              @change="handleRoleChange(scope.row)"
            >
              <el-option label="管理员" value="admin" />
              <el-option label="成员" value="member" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="加入时间" width="160">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right" align="center">
          <template #default="scope">
            <el-button
              type="danger"
              size="small"
              link
              @click="handleRemoveMember(scope.row)"
              :disabled="scope.row.role === 'owner'"
            >
              删除成员
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 添加成员对话框 -->
    <el-dialog
      v-model="addMemberDialogVisible"
      title="添加成员"
      width="400px"
    >
      <el-form ref="addMemberFormRef" :model="addMemberForm" label-width="80px">
        <el-form-item label="用户" prop="user_id">
          <el-select
            v-model="addMemberForm.user_id"
            filterable
            placeholder="请选择或搜索用户"
            style="width: 100%"
            :loading="userLoading"
          >
            <el-option
              v-for="user in selectableUsers"
              :key="user.id"
              :label="userOptionLabel(user)"
              :value="user.id"
            />
          </el-select>
          <div class="form-tip">只展示未加入当前空间的启用用户</div>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="addMemberForm.role" placeholder="请选择角色" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="成员" value="member" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addMemberDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitAddMember" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import * as spaceApi from '@/api/space'
import * as userApi from '@/api/user'

const loading = ref(false)
const spaceList = ref([])
const dialogVisible = ref(false)
const dialogType = ref('create')
const submitting = ref(false)
const formRef = ref(null)
const membersDialogVisible = ref(false)
const currentSpace = ref(null)
const memberList = ref([])
const allUsers = ref([])
const userLoading = ref(false)
const form = reactive({
  name: '',
  code: '',
  description: '',
  is_active: true
})

const rules = {
  name: [
    { required: true, message: '请输入空间名称', trigger: 'blur' }
  ],
  code: [
    { required: true, message: '请输入空间编码', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '编码只能包含字母、数字和下划线', trigger: 'blur' }
  ]
}

// 添加成员相关
const addMemberDialogVisible = ref(false)
const addMemberFormRef = ref(null)
const addMemberForm = reactive({
  user_id: null,
  role: 'member'
})

const selectableUsers = computed(() => {
  const memberIds = new Set(memberList.value.map(m => Number(m.user_id)))
  return allUsers.value.filter(u =>
    u.is_active !== false &&
    u.system_role !== 'super_admin' &&
    !memberIds.has(Number(u.id))
  )
})

async function loadSpaces() {
  loading.value = true
  try {
    const data = await spaceApi.getAllSpaces()
    spaceList.value = data || []
  } catch (e) {
    ElMessage.error('加载空间列表失败：' + e.message)
  } finally {
    loading.value = false
  }
}

function handleCreate() {
  dialogType.value = 'create'
  form.name = ''
  form.code = ''
  form.description = ''
  form.is_active = true
  dialogVisible.value = true
}

function handleEdit(row) {
  dialogType.value = 'edit'
  form.name = row.name
  form.code = row.code
  form.description = row.description || ''
  form.is_active = row.is_active !== false
  form.id = row.id
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    if (dialogType.value === 'create') {
      await spaceApi.createSpace({
        name: form.name,
        code: form.code,
        description: form.description,
        is_active: form.is_active
      })
      ElMessage.success('创建成功')
    } else {
      await spaceApi.updateSpace(form.id, {
        name: form.name,
        description: form.description,
        is_active: form.is_active
      })
      ElMessage.success('更新成功')
    }
    dialogVisible.value = false
    loadSpaces()
  } catch (e) {
    ElMessage.error('操作失败：' + e.message)
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  try {
    if (canPermanentlyDelete(row)) {
      await ElMessageBox.confirm(
        `确定要彻底删除空间「${row.name}」吗？删除后不可恢复。`,
        '确认删除',
        { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
      )
      await spaceApi.deleteSpace(row.id, {})
      ElMessage.success('删除成功')
    } else {
      await ElMessageBox.confirm(
        `删除空间「${row.name}」后将被禁用，并进入「可彻底删除」状态，需再次确认才会从系统中移除。`,
        '删除空间',
        { confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning' }
      )
      const res = await spaceApi.deleteSpace(row.id, {})
      if (res?.status === 'pending') {
        ElMessage.warning('空间已禁用，可再次点击「确认删除」彻底移除')
      } else {
        ElMessage.success('删除成功')
      }
    }
    loadSpaces()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败：' + errorMessage(e))
    }
  }
}

async function loadUsersForSelect() {
  userLoading.value = true
  try {
    const data = await userApi.getUsers({ skip: 0, limit: 500 })
    allUsers.value = data.users || []
  } catch (e) {
    ElMessage.error('加载用户列表失败：' + e.message)
  } finally {
    userLoading.value = false
  }
}

function userOptionLabel(user) {
  const name = user.display_name || user.username
  return `${name}（${user.username} / ID: ${user.id}）`
}

function errorMessage(e) {
  if (typeof e?.message === 'object') {
    return e.message.message || JSON.stringify(e.message)
  }
  return e?.message || '未知错误'
}

function canPermanentlyDelete(row) {
  return Boolean(row.delete_available_at)
}

function isDeleteDisabled(row) {
  return row.id === 1 || row.code === 'default'
}

function deleteActionText(row) {
  return canPermanentlyDelete(row) ? '确认删除' : '删除'
}

async function handleCancelDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要取消空间「${row.name}」的删除吗？取消后空间将恢复启用。`,
      '取消删除',
      { confirmButtonText: '确定取消', cancelButtonText: '暂不取消', type: 'info' }
    )
    await spaceApi.cancelDeleteSpace(row.id)
    ElMessage.success('已取消删除')
    loadSpaces()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('取消失败：' + errorMessage(e))
    }
  }
}

async function handleMembers(row) {
  currentSpace.value = row
  membersDialogVisible.value = true
  await loadMembers(row.id)
}

async function loadMembers(spaceId) {
  try {
    const members = await spaceApi.getSpaceMembers(spaceId)
    memberList.value = members || []
  } catch (e) {
    ElMessage.error('加载成员失败：' + e.message)
  }
}

function handleAddMember() {
  addMemberForm.user_id = null
  addMemberForm.role = 'member'
  addMemberDialogVisible.value = true
  loadUsersForSelect()
}

async function handleSubmitAddMember() {
  if (!addMemberForm.user_id) {
    ElMessage.warning('请选择用户')
    return
  }
  submitting.value = true
  try {
    await spaceApi.addSpaceMember(currentSpace.value.id, {
      user_id: addMemberForm.user_id,
      role: addMemberForm.role
    })
    ElMessage.success('添加成功')
    addMemberDialogVisible.value = false
    await loadMembers(currentSpace.value.id)
    await loadSpaces()
  } catch (e) {
    ElMessage.error('添加失败：' + e.message)
  } finally {
    submitting.value = false
  }
}

async function handleRemoveMember(row) {
  try {
    await ElMessageBox.confirm('确定要移除该成员吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await spaceApi.removeSpaceMember(currentSpace.value.id, row.user_id)
    ElMessage.success('移除成功')
    await loadMembers(currentSpace.value.id)
    await loadSpaces()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('移除失败：' + e.message)
    }
  }
}

async function handleRoleChange(row) {
  try {
    await spaceApi.addSpaceMember(currentSpace.value.id, {
      user_id: row.user_id,
      role: row.role
    })
    ElMessage.success('角色更新成功')
    await loadSpaces()
  } catch (e) {
    ElMessage.error('角色更新失败：' + e.message)
    await loadMembers(currentSpace.value.id)
  }
}

onMounted(() => {
  loadSpaces()
})

const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}
</script>

<style scoped>
.space-management {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.space-name {
  font-weight: 500;
}

.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.members-header {
  padding-bottom: 8px;
  border-bottom: 1px solid #e4e7ed;
}

:deep(.el-dialog .el-form-item) {
  margin-bottom: 14px;
}

:deep(.el-dialog .el-form-item:last-child) {
  margin-bottom: 0;
}

:deep(.el-card) {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

:deep(.el-card__body) {
  flex: 1;
  overflow: auto;
}
</style>
