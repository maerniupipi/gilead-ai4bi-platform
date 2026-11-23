<template>
  <div class="oss-config-page">
    <PageHeader
      :breadcrumbs="[{ label: '管理中心' }, { label: '对象存储' }]"
    >
      <template #extra>
        <div class="active-badge" v-if="activeConfig">
          <span class="active-dot" />
          <span class="active-label">{{ activeConfig.name }}</span>
        </div>
      </template>
      <template #actions>
        <el-button type="primary" @click="openForm()">配置存储</el-button>
      </template>
    </PageHeader>

    <el-alert
      title="同一时间仅允许启用一个对象存储。切换启用对象后需要重新上传文件。"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
    />

    <el-card shadow="never">
      <el-table :data="configs" style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="provider" label="类型" width="110">
          <template #default="{ row }">
            {{ providerLabel(row.provider) }}
          </template>
        </el-table-column>
        <el-table-column prop="endpoint" label="Endpoint / Region" min-width="200" show-overflow-tooltip />
        <el-table-column prop="bucket" label="Bucket" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <div class="status-cell">
              <span class="status-dot" :class="isConfigActive(row) ? 'on' : 'off'" />
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
      <el-form ref="formRef" :model="form" :rules="rules" label-width="130px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：阿里云 OSS" />
        </el-form-item>
        <el-form-item label="类型" prop="provider">
          <el-select v-model="form.provider" style="width:100%">
            <el-option label="阿里云 OSS" value="aliyun" />
            <el-option label="AWS S3" value="s3" />
            <el-option label="Azure Blob" value="azure" />
            <el-option label="MinIO" value="minio" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.provider === 'aliyun'" label="Endpoint" prop="endpoint">
          <el-input v-model="form.endpoint" placeholder="oss-cn-shanghai.aliyuncs.com" />
        </el-form-item>
        <el-form-item v-if="form.provider === 's3' || form.provider === 'minio'" label="Endpoint" prop="endpoint">
          <el-input v-model="form.endpoint" placeholder="https://s3.amazonaws.com 或 MinIO 地址" />
        </el-form-item>
        <el-form-item v-if="form.provider === 'azure'" label="连接字符串" prop="endpoint">
          <el-input v-model="form.endpoint" placeholder="DefaultEndpointsProtocol=..." type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item v-if="form.provider === 's3' || form.provider === 'minio'" label="Region" prop="region">
          <el-input v-model="form.region" placeholder="us-east-1" />
        </el-form-item>
        <el-form-item label="Bucket" prop="bucket">
          <el-input v-model="form.bucket" placeholder="my-bucket" />
        </el-form-item>
        <el-form-item label="Access Key" prop="access_key">
          <el-input v-model="form.access_key" placeholder="AK" />
        </el-form-item>
        <el-form-item label="Secret Key" prop="secret_key">
          <el-input v-model="form.secret_key" type="password" show-password placeholder="SK" />
        </el-form-item>
        <el-form-item label="存储路径前缀">
          <el-input v-model="form.prefix" placeholder="xlsx-qa/（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testVisible" title="测试存储连接" width="520px">
      <el-form :model="testForm" label-width="130px">
        <el-form-item label="配置名称">
          <el-input v-model="testForm.name" disabled />
        </el-form-item>
        <el-form-item label="类型">
          <el-input :value="providerLabel(testForm.provider)" disabled />
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
import { createOssConfig, deleteOssConfig, getOssConfigs, testOssConfig, updateOssConfig } from '@/api/ossConfig'

const configs = ref([])
const dialogVisible = ref(false)
const testVisible = ref(false)
const testing = ref(false)
const dialogTitle = ref('配置对象存储')
const formRef = ref(null)
const currentId = ref(null)
const activatingId = ref(null)
const activeConfig = computed(() => configs.value.find(item => item.is_active))

const isConfigActive = (row) => row.is_active

const PROVIDER_LABELS = {
  aliyun: '阿里云 OSS',
  s3: 'AWS S3',
  azure: 'Azure Blob',
  minio: 'MinIO',
}

const providerLabel = (p) => PROVIDER_LABELS[p] || p

const form = reactive({
  name: '',
  provider: 'aliyun',
  endpoint: '',
  bucket: '',
  access_key: '',
  secret_key: '',
  prefix: '',
  region: '',
})

const testForm = reactive({
  name: '',
  provider: 'aliyun',
  endpoint: '',
  bucket: '',
  access_key: '',
  secret_key: '',
  prefix: '',
  region: '',
})

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  provider: [{ required: true, message: '请选择类型', trigger: 'change' }],
  endpoint: [{ required: true, message: '请输入 Endpoint', trigger: 'blur' }],
  bucket: [{ required: true, message: '请输入 Bucket', trigger: 'blur' }],
  access_key: [{ required: true, message: '请输入 Access Key', trigger: 'blur' }],
  secret_key: [{ required: true, message: '请输入 Secret Key', trigger: 'blur' }],
}

const loadConfigs = async () => {
  configs.value = await getOssConfigs()
}

const openForm = (row) => {
  dialogTitle.value = row ? '编辑存储配置' : '配置对象存储'
  currentId.value = row?.id || null
  form.name = row?.name || '默认存储'
  form.provider = row?.provider || 'aliyun'
  form.endpoint = row?.endpoint || ''
  form.bucket = row?.bucket || ''
  form.access_key = row?.access_key || ''
  form.secret_key = row?.secret_key || ''
  form.prefix = row?.prefix || ''
  form.region = row?.region || ''
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
  if (currentId.value) await updateOssConfig(currentId.value, payload)
  else await createOssConfig(payload)
  ElMessage.success('保存成功')
  dialogVisible.value = false
  await loadConfigs()
}

const handleTest = (row) => {
  testForm.name = row.name
  testForm.provider = row.provider
  testForm.endpoint = row.endpoint
  testForm.bucket = row.bucket
  testForm.access_key = row.access_key
  testForm.secret_key = row.secret_key
  testForm.prefix = row.prefix
  testForm.region = row.region
  testVisible.value = true
}

const executeTest = async () => {
  testing.value = true
  try {
    const result = await testOssConfig(testForm)
    if (result.success) ElMessage.success(result.message || '连接成功')
    else ElMessage.error(result.message || '连接失败')
  } finally {
    testing.value = false
  }
}

const handleActivate = async (row) => {
  try {
    await ElMessageBox.confirm(
      `启用「${row.name}」后，原存储配置将被切换。确定要切换吗？`,
      '切换存储确认',
      { confirmButtonText: '确定切换', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  activatingId.value = row.id
  try {
    const testPayload = {
      name: row.name,
      provider: row.provider,
      endpoint: row.endpoint,
      bucket: row.bucket,
      access_key: row.access_key,
      secret_key: row.secret_key,
      region: row.region,
    }
    const testResult = await testOssConfig(testPayload)
    if (!testResult.success) {
      ElMessage.error(`连接测试失败：${testResult.message}，请检查配置后重试`)
      return
    }
    const currentlyActive = configs.value.filter(s => isConfigActive(s) && s.id !== row.id)
    for (const s of currentlyActive) {
      await updateOssConfig(s.id, { is_active: false })
    }
    await updateOssConfig(row.id, { is_active: true })
    ElMessage.success(`已启用「${row.name}」`)
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
      '删除存储配置确认',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  await deleteOssConfig(row.id)
  ElMessage.success('删除成功')
  await loadConfigs()
}

const handleDeactivate = async (row) => {
  try {
    await ElMessageBox.confirm(
      `停止「${row.name}」后，对象存储功能将不可用。确定要停止吗？`,
      '停止存储确认',
      { confirmButtonText: '确定停止', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  activatingId.value = row.id
  try {
    await updateOssConfig(row.id, { is_active: false })
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
.oss-config-page { display: flex; flex-direction: column; gap: 16px; }
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

.status-dot.on { background: #22c55e; }
.status-dot.off { background: #d1d5db; }

.status-text {
  font-size: 12px;
  font-weight: 500;
}

.status-text.on { color: #166534; }
.status-text.off { color: #9ca3af; }
</style>
