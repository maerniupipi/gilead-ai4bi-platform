<template>
  <div class="space-switcher" v-if="ready">
    <el-dropdown trigger="click" @command="handleCommand">
      <div class="space-trigger">
        <div class="space-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <rect x="3" y="3" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.9"/>
            <rect x="14" y="3" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.7"/>
            <rect x="3" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.7"/>
            <rect x="14" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.9"/>
          </svg>
        </div>
        <span class="space-name">{{ currentSpace?.name || '选择空间' }}</span>
        <el-icon class="arrow-icon"><ArrowDown /></el-icon>
      </div>
      <template #dropdown>
        <el-dropdown-menu class="space-dropdown-menu">
          <div class="space-dropdown-header">工作空间</div>
          <el-dropdown-item
            v-for="space in availableSpaces"
            :key="space.id"
            :command="space.id"
            :class="{ 'is-active': space.id === currentSpace?.id }"
          >
            <div class="space-item">
              <div class="space-item-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="3" width="7" height="7" rx="1.5" fill="currentColor"/>
                  <rect x="14" y="3" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.7"/>
                  <rect x="3" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.7"/>
                  <rect x="14" y="14" width="7" height="7" rx="1.5" fill="currentColor"/>
                </svg>
              </div>
              <div class="space-item-content">
                <div class="space-item-name">{{ space.name }}</div>
                <div class="space-item-role">{{ getRoleLabel(space.role) }}</div>
              </div>
              <el-icon v-if="space.id === currentSpace?.id" class="check-icon"><Check /></el-icon>
            </div>
          </el-dropdown-item>
          <div class="space-divider"></div>
          <el-dropdown-item command="create" class="action-item">
            <el-icon><Plus /></el-icon>
            创建新空间
          </el-dropdown-item>
          <el-dropdown-item command="manage" class="action-item">
            <el-icon><Setting /></el-icon>
            空间管理
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 创建空间对话框 -->
    <el-dialog
      v-model="createDialogVisible"
      title="创建新空间"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-position="top">
        <el-form-item label="空间名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入空间名称" maxlength="100" />
        </el-form-item>
        <el-form-item label="空间编码" prop="code">
          <el-input v-model="createForm.code" placeholder="请输入唯一编码，用于URL等" maxlength="50" />
          <div class="form-tip">编码只能包含字母、数字和下划线</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="可选，空间描述" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateSpace" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <!-- 切换空间 Loading 过渡 -->
    <SpaceLoadingOverlay :visible="switching" @complete="handleReload" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, Check, Plus, Setting } from '@element-plus/icons-vue'
import { useSpaceContext } from '@/utils/spaceContext'
import * as spaceApi from '@/api/space'
import SpaceLoadingOverlay from './SpaceLoadingOverlay.vue'

const router = useRouter()

const { currentSpace, availableSpaces, loadSpaces, switchSpace } = useSpaceContext()

const ready = ref(false)
const createDialogVisible = ref(false)
const creating = ref(false)
const createFormRef = ref(null)

/** 切换空间加载过渡 */
const switching = ref(false)

const createForm = reactive({
  name: '',
  code: '',
  description: ''
})

const createRules = {
  name: [
    { required: true, message: '请输入空间名称', trigger: 'blur' },
    { min: 1, max: 100, message: '长度在 1 到 100 个字符', trigger: 'blur' }
  ],
  code: [
    { required: true, message: '请输入空间编码', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '编码只能包含字母、数字和下划线', trigger: 'blur' }
  ]
}

function getRoleLabel(role) {
  const roleMap = {
    owner: '所有者',
    super_admin: '超级管理员',
    admin: '管理员',
    member: '成员',
    viewer: '访客'
  }
  return roleMap[role] || role
}

async function handleCommand(command) {
  if (command === 'create') {
    createForm.name = ''
    createForm.code = ''
    createForm.description = ''
    createDialogVisible.value = true
  } else if (command === 'manage') {
    router.push('/management/space')
  } else {
    try {
      await switchSpace(command)
      // 切换成功，显示全屏加载过渡，然后强制刷新页面
      switching.value = true
    } catch (e) {
      ElMessage.error('切换空间失败：' + e.message)
    }
  }
}

function handleReload() {
  window.location.reload()
}

async function handleCreateSpace() {
  if (!createFormRef.value) return
  try {
    await createFormRef.value.validate()
  } catch (e) {
    return
  }
  creating.value = true
  try {
    const newSpace = await spaceApi.createSpace({
      name: createForm.name,
      code: createForm.code,
      description: createForm.description,
      is_active: true
    })
    ElMessage.success('空间创建成功')
    createDialogVisible.value = false
    await switchSpace(newSpace.id)
    switching.value = true
  } catch (e) {
    ElMessage.error('创建空间失败：' + e.message)
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  await loadSpaces()
  ready.value = true
})
</script>

<style scoped>
.space-switcher {
  display: flex;
  align-items: center;
}

.space-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #f1f3f8;
  border-radius: 8px;
  cursor: pointer;
  transition: all 200ms ease;
  border: 1px solid transparent;
}

.space-trigger:hover {
  background: #e8ebf4;
  border-color: #d8dce8;
}

.space-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #1fb8cc;
}

.space-name {
  font-size: 13px;
  font-weight: 600;
  color: #1a1d23;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.arrow-icon {
  color: #9ca3af;
  font-size: 12px;
  transition: transform 200ms ease;
}

.space-trigger:hover .arrow-icon {
  transform: translateY(1px);
}

.space-dropdown-header {
  padding: 8px 16px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #9ca3af;
  border-bottom: 1px solid #e8eaef;
  margin-bottom: 8px;
}

.space-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.space-item-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f1f3f8;
  border-radius: 6px;
  color: #5c6370;
  flex-shrink: 0;
  transition: all 200ms ease;
}

.space-item-name {
  font-size: 14px;
  color: #1a1d23;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.space-item-role {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

.check-icon {
  color: #1fb8cc;
  font-size: 14px;
  flex-shrink: 0;
}

.is-active .space-item-icon {
  background: #e9f8fa;
  color: #1fb8cc;
}

.action-item {
  font-size: 13px !important;
}

.action-item :deep(.el-icon) {
  margin-right: 6px;
}

.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: #9ca3af;
}

.space-divider {
  height: 1px;
  background: #e8eaef;
  margin: 4px 0;
}
</style>
