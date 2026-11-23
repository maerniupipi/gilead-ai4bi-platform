<template>
  <div class="vector-store-page">
    <PageHeader
      :breadcrumbs="[{ label: '模型中心' }, { label: '向量库' }]"
    >
      <template #extra>
        <div class="active-badge" v-if="activeStore">
          <span class="active-dot" />
          <span class="active-label">{{ activeStore.name }}</span>
        </div>
      </template>
      <template #actions>
        <el-button type="primary" @click="openForm()">配置向量库</el-button>
      </template>
    </PageHeader>

    <el-alert
      title="同一时间仅允许启用一个向量库。切换启用对象后，需要重新向量化已有知识库数据。"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
    />

    <el-card shadow="never">
      <el-table :data="stores" style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="provider" label="类型" width="110" />
        <el-table-column prop="host" label="Host" min-width="160" show-overflow-tooltip />
        <el-table-column prop="port" label="Port" width="80" />
        <el-table-column prop="database" label="数据库" min-width="100" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <div class="status-cell">
              <span
                class="status-dot"
                :class="isStoreActive(row) ? 'on' : 'off'"
              />
              <span class="status-text" :class="isStoreActive(row) ? 'on' : 'off'">
                {{ isStoreActive(row) ? '运行中' : '已停止' }}
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
              v-if="!isStoreActive(row)"
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
          <el-input v-model="form.name" placeholder="例如：默认 Milvus" />
        </el-form-item>
        <el-form-item label="类型" prop="provider">
          <el-select v-model="form.provider" style="width:100%">
            <el-option label="Milvus" value="milvus" />
            <el-option label="OpenSearch" value="opensearch" />
            <el-option label="Azure AI Search" value="azure_ai_search" />
            <el-option label="Qdrant" value="qdrant" />
            <el-option label="PostgreSQL + pgvector" value="pgvector" />
            <el-option label="Elasticsearch" value="elasticsearch" />
          </el-select>
        </el-form-item>
        <el-form-item label="Host" prop="host">
          <el-input v-model="form.host" :placeholder="form.provider === 'azure_ai_search' ? 'https://xxx.search.windows.net' : '127.0.0.1'" />
        </el-form-item>
        <el-form-item v-if="form.provider !== 'azure_ai_search'" label="Port" prop="port">
          <el-input v-model="form.port" placeholder="19530" />
        </el-form-item>
        <el-form-item v-if="form.provider === 'pgvector'" label="数据库名">
          <el-input v-model="form.database" placeholder="postgres" />
        </el-form-item>
        <el-form-item v-else label="数据库/命名空间">
          <el-input v-model="form.database" placeholder="app" />
        </el-form-item>
        <el-form-item v-if="['milvus','opensearch'].includes(form.provider)" label="用户名">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item v-if="['milvus','opensearch'].includes(form.provider)" label="密码">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item v-if="form.provider === 'azure_ai_search'" label="API Key">
          <el-input v-model="form.password" type="password" show-password placeholder="Azure AI Search admin/query key" />
        </el-form-item>
        <el-form-item v-if="['milvus','opensearch'].includes(form.provider)" label="集合前缀">
          <el-input v-model="form.collection_prefix" placeholder="v_kb" />
        </el-form-item>
        <el-form-item v-else label="资源前缀">
          <el-input v-model="form.collection_prefix" placeholder="v_kb" />
        </el-form-item>
        <el-form-item label="向量维度">
          <el-input-number v-model="form.dimension" :min="1" :step="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testVisible" title="测试向量库连接" width="520px">
      <el-form :model="testForm" label-width="120px">
        <el-form-item label="向量库名称">
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
import { createVectorStore, deleteVectorStore, getVectorStores, testVectorStore, updateVectorStore } from '../api/vectorStore'

const stores = ref([])
const dialogVisible = ref(false)
const testVisible = ref(false)
const testing = ref(false)
const dialogTitle = ref('配置向量库')
const formRef = ref(null)
const currentId = ref(null)
const activatingId = ref(null)
const activeStore = computed(() => stores.value.find(item => item.is_active))

const isStoreActive = (row) => row.is_active

const form = reactive({
  name: '',
  provider: 'milvus',
  host: '',
  port: '',
  username: '',
  password: '',
  database: 'app',
  collection_prefix: 'v_kb',
  dimension: 1024
})

const testForm = reactive({ name: '', provider: 'milvus', host: '', port: '', username: '', password: '', database: '', collection_prefix: '', dimension: 1024 })

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  host: [{ required: true, message: '请输入Host', trigger: 'blur' }],
  port: [
    {
      validator: (rule, value, callback) => {
        if (form.provider !== 'azure_ai_search' && !value) callback(new Error('请输入Port'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

const loadStores = async () => {
  stores.value = await getVectorStores()
}

const openForm = (row) => {
  dialogTitle.value = row ? '编辑向量库' : '配置向量库'
  currentId.value = row?.id || null
  form.name = row?.name || '默认向量库'
  form.provider = row?.provider || 'milvus'
  form.host = row?.host || ''
  form.port = row?.port || ''
  form.username = row?.username || ''
  form.password = row?.password || ''
  form.database = row?.database || 'app'
  form.collection_prefix = row?.collection_prefix || 'v_kb'
  form.dimension = row?.dimension || 1024
  dialogVisible.value = true
}

const resetForm = () => {
  currentId.value = null
}

const submitForm = async () => {
  await formRef.value.validate()
  const payload = { ...form }
  // New stores are active by default if no other is active
  if (!currentId.value && !activeStore.value) {
    payload.is_active = true
  }
  if (currentId.value) await updateVectorStore(currentId.value, payload)
  else await createVectorStore(payload)
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await loadStores()
}

const handleTest = (row) => {
  testForm.name = row.name
  testForm.provider = row.provider
  testForm.host = row.host
  testForm.port = row.port
  testForm.username = row.username
  testForm.password = row.password
  testForm.database = row.database
  testForm.collection_prefix = row.collection_prefix
  testForm.dimension = row.dimension
  testVisible.value = true
}

const executeTest = async () => {
  testing.value = true
  try {
    const result = await testVectorStore(testForm)
    if (result.success) ElMessage.success(result.message || '连接成功')
    else ElMessage.error(result.message || '连接失败')
  } finally {
    testing.value = false
  }
}

const handleActivate = async (row) => {
  try {
    await ElMessageBox.confirm(
      `启用「${row.name}」作为默认向量库后，已有知识库的向量数据将失效，需要重新执行向量化操作。确定要切换吗？`,
      '切换向量库确认',
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
      provider: row.provider,
      host: row.host,
      port: row.port,
      username: row.username,
      password: row.password,
      database: row.database,
      collection_prefix: row.collection_prefix,
      dimension: row.dimension
    }
    const testResult = await testVectorStore(testPayload)
    if (!testResult.success) {
      const reason = testResult.message || '连接失败'
      ElMessage.error(`连接测试失败：${reason}，请检查配置后重试`)
      return
    }

    // Deactivate all currently active stores first
    const currentlyActive = stores.value.filter(s => isStoreActive(s) && s.id !== row.id)
    for (const s of currentlyActive) {
      await updateVectorStore(s.id, { is_active: false })
    }
    // Activate the target
    await updateVectorStore(row.id, { is_active: true })
    ElMessage.success(`已启用「${row.name}」，请对现有知识库重新执行向量化`)
    await loadStores()
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
      '删除向量库确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  await deleteVectorStore(row.id)
  ElMessage.success('删除成功')
  await loadStores()
}

const handleDeactivate = async (row) => {
  try {
    await ElMessageBox.confirm(
      `停止「${row.name}」后，当前没有正在运行的向量库，知识库相关功能将不可用。确定要停止吗？`,
      '停止向量库确认',
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
    await updateVectorStore(row.id, { is_active: false })
    ElMessage.success(`已停止「${row.name}」`)
    await loadStores()
  } catch (error) {
    const detail = error?.message || error?.response?.data?.detail || ''
    ElMessage.error(`停止失败：${detail}`)
  } finally {
    activatingId.value = null
  }
}

onMounted(loadStores)
</script>

<style scoped>
.vector-store-page { display: flex; flex-direction: column; gap: 16px; }
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
