<template>
  <div class="model-center-page">
    <PageHeader
      :breadcrumbs="[{ label: '模型中心' }, { label: '向量模型' }]"
    >
      <template #extra>
        <el-tag v-if="activeConfig" type="success">当前默认：{{ activeConfig.name }}</el-tag>
      </template>
      <template #actions>
        <el-button type="primary" @click="openForm()">配置向量模型</el-button>
      </template>
    </PageHeader>

    <el-alert
      title="系统默认仅允许启用一个向量模型配置。向量化操作会自动使用当前默认配置。"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
    />

    <el-card shadow="never">
      <el-table :data="configs" style="width: 100%">
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="provider" label="提供商" width="120" />
        <el-table-column prop="model" label="模型" />
        <el-table-column prop="dimension" label="维度" width="100" />
        <el-table-column prop="is_default" label="默认" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success">默认</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openForm(row)">编辑</el-button>
            <el-popconfirm
              title="确定要删除该向量模型配置吗？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px" @close="resetForm">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="例如：默认向量模型" />
        </el-form-item>
        <el-form-item label="提供商" prop="provider">
          <el-select v-model="form.provider" style="width:100%">
            <el-option label="阿里云 DashScope" value="dashscope" />
            <el-option label="OpenAI" value="openai" />
            <el-option label="Azure OpenAI" value="azure" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Key" prop="api_key">
          <el-input v-model="form.api_key" type="password" show-password placeholder="请输入API Key" />
        </el-form-item>
        <el-form-item label="模型名称" prop="model">
          <el-input v-model="form.model" placeholder="text-embedding-v4" />
        </el-form-item>
        <el-form-item label="向量维度" prop="dimension">
          <el-input-number v-model="form.dimension" :min="1" :step="1" />
        </el-form-item>
        <el-form-item label="Base URL" prop="base_url">
          <el-input v-model="form.base_url" placeholder="OpenAI兼容 embeddings 地址；Azure OpenAI 填 deployment embeddings endpoint" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createEmbeddingConfig, deleteEmbeddingConfig, getEmbeddingConfigs, updateEmbeddingConfig } from '../api/embeddingConfig'

const configs = ref([])
const dialogVisible = ref(false)
const dialogTitle = ref('配置向量模型')
const formRef = ref(null)
const currentId = ref(null)
const activeConfig = computed(() => configs.value.find(item => item.is_default && item.is_active))

const form = reactive({
  name: '',
  provider: 'dashscope',
  api_key: '',
  model: 'text-embedding-v4',
  dimension: 1024,
  base_url: '',
  is_default: true,
  is_active: true
})

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  api_key: [{ required: true, message: '请输入API Key', trigger: 'blur' }],
  model: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  base_url: [{ required: true, message: '请输入Base URL', trigger: 'blur' }],
}

const loadConfigs = async () => {
  try {
    configs.value = await getEmbeddingConfigs()
  } catch (e) {
    ElMessage.error(e.message || '加载失败')
  }
}

const openForm = (row) => {
  dialogTitle.value = row ? '编辑向量模型' : '配置向量模型'
  currentId.value = row?.id || null
  form.name = row?.name || '默认向量模型'
  form.provider = row?.provider || 'dashscope'
  form.api_key = row?.api_key || ''
  form.model = row?.model || 'text-embedding-v4'
  form.dimension = row?.dimension || 1024
  form.base_url = row?.base_url || ''
  form.is_default = row?.is_default ?? true
  form.is_active = row?.is_active ?? true
  dialogVisible.value = true
}

const resetForm = () => {
  currentId.value = null
}

const handleDelete = async (row) => {
  try {
    await deleteEmbeddingConfig(row.id)
    ElMessage.success('删除成功')
    await loadConfigs()
  } catch (e) {
    ElMessage.error(e.message || '删除失败')
  }
}

const submitForm = async () => {
  try {
    await formRef.value.validate()
    const payload = { ...form }
    if (currentId.value) await updateEmbeddingConfig(currentId.value, payload)
    else await createEmbeddingConfig(payload)
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadConfigs()
  } catch (e) {
    if (e?.message) ElMessage.error(e.message || '保存失败')
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.model-center-page { display: flex; flex-direction: column; gap: 16px; }
.header-actions { display: flex; gap: 12px; align-items: center; }
</style>
