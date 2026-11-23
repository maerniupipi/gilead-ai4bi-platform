<template>
  <div class="account-mgmt">
    <PageHeader
      :breadcrumbs="[{ label: '管理页面' }, { label: '用户管理' }]"
    >
      <template #actions>
        <el-button type="primary" @click="openCreate" v-if="currentUserInfo">
          <el-icon><Plus /></el-icon>
          创建用户
        </el-button>
      </template>
    </PageHeader>

    <el-card shadow="never" class="table-card" v-loading="loading">
      <el-table :data="userList" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" min-width="120">
          <template #default="scope">
            <span class="username">{{ scope.row.username }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="display_name" label="显示名称" min-width="150">
          <template #default="scope">
            {{ scope.row.display_name || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="100">
          <template #default="scope">
            <el-switch
              v-model="scope.row.is_active"
              :disabled="!canDisableUser(scope.row)"
              size="small"
              @change="handleStatusChange(scope.row)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="scope">
            <el-button
              type="danger"
              size="small"
              link
              @click="handleDelete(scope.row)"
              :disabled="!canDeleteUser(scope.row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建 -->
    <el-dialog v-model="createVisible" title="创建用户" width="500px" destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="请输入用户名" maxlength="64" />
        </el-form-item>
        <el-form-item label="显示名称" prop="display_name">
          <el-input v-model="createForm.display_name" placeholder="请输入显示名称" maxlength="128" />
        </el-form-item>
        <el-form-item label="初始密码" prop="password">
          <el-input v-model="createForm.password" type="password" placeholder="请输入密码，默认123456" maxlength="128" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import * as userApi from '@/api/user'

const loading = ref(false)
const userList = ref([])
const currentUserInfo = ref(null)
const createVisible = ref(false)
const creating = ref(false)
const changing = ref(false)
const createFormRef = ref(null)

const createForm = reactive({
  username: '',
  display_name: '',
  password: ''
})

const createRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 1, max: 64, message: '长度在 1 到 64 个字符', trigger: 'blur' }
  ]
}

async function loadCurrentUser() {
  try {
    currentUserInfo.value = await userApi.getCurrentUser()
  } catch (e) {
    console.error('获取当前用户失败', e)
  }
}

async function loadUsers() {
  loading.value = true
  try {
    const data = await userApi.getUsers()
    userList.value = data.users || []
  } catch (e) {
    ElMessage.error('加载用户列表失败：' + e.message)
  } finally {
    loading.value = false
  }
}

function canDeleteUser(row) {
  if (!currentUserInfo.value) return false
  if (row.system_role === 'super_admin') return false
  if (row.id === currentUserInfo.value.id) return false
  return true
}

function canDisableUser(row) {
  if (!currentUserInfo.value) return false
  if (row.system_role === 'super_admin') return false
  return true
}

function openCreate() {
  createForm.username = ''
  createForm.display_name = ''
  createForm.password = ''
  createVisible.value = true
}

async function submitCreate() {
  try {
    await createFormRef.value?.validate()
  } catch {
    return
  }
  creating.value = true
  try {
    await userApi.createUser({
      username: createForm.username,
      display_name: createForm.display_name || undefined,
      password: createForm.password || undefined
    })
    ElMessage.success('创建成功')
    createVisible.value = false
    loadUsers()
  } catch (e) {
    ElMessage.error('创建失败：' + e.message)
  } finally {
    creating.value = false
  }
}

async function handleStatusChange(row) {
  if (changing.value) return
  changing.value = true
  try {
    await userApi.updateUser(row.id, { is_active: row.is_active })
    ElMessage.success(row.is_active ? '已启用' : '已禁用')
  } catch (e) {
    ElMessage.error('更新失败：' + e.message)
    loadUsers()
  } finally {
    changing.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定要删除该用户吗？删除后不可恢复。', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await userApi.deleteUser(row.id)
    ElMessage.success('删除成功')
    loadUsers()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败：' + e.message)
    }
  }
}

const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}

onMounted(() => {
  loadCurrentUser()
  loadUsers()
})
</script>

<style scoped>
.account-mgmt {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.username {
  font-weight: 500;
}

.table-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.table-card :deep(.el-card__body) {
  flex: 1;
  overflow: auto;
}
</style>
