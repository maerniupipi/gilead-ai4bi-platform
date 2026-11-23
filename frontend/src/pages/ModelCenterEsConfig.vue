<template>
  <div class="es-config-page">
    <PageHeader
      :breadcrumbs="[{ label: '模型中心' }, { label: 'ES配置' }]"
    >
      <template #extra>
        <div class="active-badge" v-if="activeConfig">
          <span class="active-dot" />
          <span class="active-label">{{ activeConfig.name }}</span>
        </div>
      </template>
      <template #actions>
        <el-button type="primary" @click="openForm()">配置ES</el-button>
      </template>
    </PageHeader>

    <el-alert
      title="同一时间仅允许启用一个 ES 实例。切换启用对象后，需要重新向量化已有知识库数据。"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
    />

    <el-card shadow="never">
      <el-table :data="configs" style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="host" label="Host" min-width="180" show-overflow-tooltip />
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column prop="username" label="用户名" min-width="100" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <div class="status-cell">
              <span
                class="status-dot"
                :class="isConfigActive(row) ? 'on' : 'off'"
              />
              <span class="status-text" :class="isConfigActive(row) ? 'on' : 'off'">
                {{ isConfigActive(row) ? '运行中' : '已停止' }}
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="340" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openForm(row)">编辑</el-button>
            <el-button size="small" type="primary" @click="handleTest(row)">测试</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
            <el-button
              v-if="!isConfigActive(row)"
              size="small"
              type="success"
              :loading="activatingId === row.id"
              @click="handleActivate(row)"
            >
              启动
            </el-button>
            <el-button
              v-else
              size="small"
              type="warning"
              :loading="activatingId === row.id"
              @click="handleDeactivate(row)"
            >
              停止
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：默认ES" />
        </el-form-item>
        <el-form-item label="Host" prop="host">
          <el-input v-model="form.host" placeholder="ES: http://127.0.0.1 / Azure: https://xxx.search.windows.net" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input v-model="form.port" placeholder="9200" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="ES用户名；Azure AI Search 可留空" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="ES密码；Azure AI Search 填 API Key" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testVisible" title="测试ES连接" width="520px">
      <el-form :model="testForm" label-width="120px">
        <el-form-item label="ES名称">
          <el-input v-model="testForm.name" disabled />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="testVisible = false">取消</el-button>
        <el-button type="primary" :loading="testing" @click="executeTest">开始测试</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createEsConfig, deleteEsConfig, getEsConfigs, testEsConfig, updateEsConfig } from '../api/esConfig'

const configs = ref([])
const dialogVisible = ref(false)
const testVisible = ref(false)
const testing = ref(false)
const dialogTitle = ref('配置ES')
const formRef = ref(null)
const currentId = ref(null)
const activatingId = ref(null)
const activeConfig = computed(() => configs.value.find(item => item.is_active))

const isConfigActive = (row) => row.is_active

const form = reactive({
  name: '',
  host: '',
  port: '9200',
  username: '',
  password: ''
})

const testForm = reactive({ name: '', host: '', port: '', username: '', password: '' })

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  host: [{ required: true, message: '请输入Host', trigger: 'blur' }],
}

const loadConfigs = async () => {
  configs.value = await getEsConfigs()
}

const openForm = (row) => {
  dialogTitle.value = row ? '编辑ES配置' : '配置ES'
  currentId.value = row?.id || null
  form.name = row?.name || '默认ES'
  form.host = row?.host || ''
  form.port = row?.port || '9200'
  form.username = row?.username || ''
  form.password = row?.password || ''
  dialogVisible.value = true
}

const resetForm = () => {
  currentId.value = null
}

const submitForm = async () => {
  await formRef.value.validate()
  const payload = { ...form }
  if (!currentId.value && !activeConfig.value) {
    payload.is_default = true
    payload.is_active = true
  }
  if (currentId.value) await updateEsConfig(currentId.value, payload)
  else await createEsConfig(payload)
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await loadConfigs()
}

const handleTest = (row) => {
  testForm.name = row.name
  testForm.host = row.host
  testForm.port = row.port
  testForm.username = row.username
  testForm.password = row.password
  testVisible.value = true
}

const executeTest = async () => {
  testing.value = true
  try {
    const result = await testEsConfig(testForm)
    if (result.success) ElMessage.success(result.message || '连接成功')
    else ElMessage.error(result.message || '连接失败')
  } finally {
    testing.value = false
  }
}

const handleActivate = async (row) => {
  try {
    await ElMessageBox.confirm(
      `启用「${row.name}」作为默认 ES 实例后，已有知识库的 ES 索引数据将失效，需要重新执行向量化操作。确定要切换吗？`,
      '切换 ES 实例确认',
      {
        confirmButtonText: '确定切换',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }

  activatingId.value = row.id
  try {
    // 先测试连接
    const testPayload = {
      name: row.name,
      host: row.host,
      port: row.port,
      username: row.username,
      password: row.password
    }
    const testResult = await testEsConfig(testPayload)
    if (!testResult.success) {
      const reason = testResult.message || '连接失败'
      ElMessage.error(`连接测试失败：${reason}，请检查配置后重试`)
      return
    }

    // Deactivate all currently active configs first
    const currentlyActive = configs.value.filter(s => isConfigActive(s) && s.id !== row.id)
    for (const s of currentlyActive) {
      await updateEsConfig(s.id, { is_active: false })
    }
    // Activate the target
    await updateEsConfig(row.id, { is_active: true })
    ElMessage.success(`已启用「${row.name}」，请对现有知识库重新执行向量化`)
    await loadConfigs()
  } catch (error) {
    const detail = error?.message || error?.response?.data?.detail || ''
    ElMessage.error(`启动失败：${detail}`)
  } finally {
    activatingId.value = null
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除「${row.name}」吗？删除后不可恢复。`,
      '删除 ES 配置确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  await deleteEsConfig(row.id)
  ElMessage.success('删除成功')
  await loadConfigs()
}

const handleDeactivate = async (row) => {
  try {
    await ElMessageBox.confirm(
      `停止「${row.name}」后，当前没有正在运行的 ES 实例，知识库相关功能将不可用。确定要停止吗？`,
      '停止 ES 实例确认',
      {
        confirmButtonText: '确定停止',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
  } catch {
    return
  }

  activatingId.value = row.id
  try {
    await updateEsConfig(row.id, { is_active: false })
    ElMessage.success(`已停止「${row.name}」`)
    await loadConfigs()
  } catch (error) {
    const detail = error?.message || error?.response?.data?.detail || ''
    ElMessage.error(`停止失败：${detail}`)
  } finally {
    activatingId.value = null
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.es-config-page { display: flex; flex-direction: column; gap: 16px; }
.header-actions { display: flex; gap: 12px; align-items: center; }

.active-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
}

.active-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.4);
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 6px rgba(34, 197, 94, 0.4); }
  50% { box-shadow: 0 0 12px rgba(34, 197, 94, 0.6); }
}

.active-label {
  font-size: 13px;
  font-weight: 600;
  color: #166534;
}

/* Status column */
.status-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.on {
  background: #22c55e;
}

.status-dot.off {
  background: #d1d5db;
}

.status-text {
  font-size: 12px;
  font-weight: 500;
}

.status-text.on {
  color: #166534;
}

.status-text.off {
  color: #9ca3af;
}
</style>
