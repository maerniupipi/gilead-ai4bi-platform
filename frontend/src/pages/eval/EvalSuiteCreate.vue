<template>
  <div class="eval-suite-create">
    <div class="create-container">
      <PageHeader :breadcrumbs="[{ label: '评测集', to: '/eval/suites' }, { label: '新建评测集' }]" />

      <div class="create-header">
        <h1 class="create-title">新建评测集</h1>
        <p class="create-desc">创建一个新的评测集来管理和运行 AI 系统评测</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        class="create-form"
      >
        <el-form-item label="评测集名称" prop="name">
          <el-input
            v-model="form.name"
            placeholder="请输入评测集名称"
            size="large"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="所属文件夹" prop="folder_id">
          <el-select
            v-model="form.folder_id"
            placeholder="选择文件夹"
            style="width: 100%"
          >
            <el-option
              v-for="folder in folders"
              :key="folder.id"
              :label="folder.name"
              :value="folder.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            placeholder="输入评测集描述（可选）"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="标签">
          <el-select
            v-model="form.tag_ids"
            multiple
            filterable
            allow-create
            placeholder="选择或输入新标签"
            style="width: 100%"
            @change="handleTagChange"
          >
            <el-option
              v-for="tag in availableTags"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            >
              <span :style="{ color: tag.color }">{{ tag.name }}</span>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="默认任务源类型">
          <el-radio-group v-model="form.default_task_source_type">
            <el-radio value="agent">工作流</el-radio>
            <el-radio value="lab">实验室</el-radio>
            <el-radio value="xlsx_qa">XLSX 问答</el-radio>
            <el-radio value="api">开放 API</el-radio>
            <el-radio value="custom">自定义</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="默认对比方式">
          <el-select v-model="form.default_comparison_method" style="width: 100%">
            <el-option value="exact" label="精确匹配" />
            <el-option value="regex" label="正则匹配" />
            <el-option value="contains" label="包含匹配" />
            <el-option value="multi_level" label="多级对比" />
            <el-option value="semantic" label="语义相似（开发中）" disabled />
            <el-option value="sql_execute" label="SQL执行（开发中）" disabled />
            <el-option value="llm_judge" label="LLM评判（开发中）" disabled />
          </el-select>
        </el-form-item>
      </el-form>

      <div class="create-footer">
        <el-button @click="handleCancel">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          创建评测集
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useSpaceContext } from '@/utils/spaceContext'
import * as evalApi from '@/api/eval'

const router = useRouter()
const { currentSpace } = useSpaceContext()

const formRef = ref(null)
const submitting = ref(false)
const folders = ref([])
const availableTags = ref([])

const form = reactive({
  name: '',
  folder_id: null,
  description: '',
  tag_ids: [],
  default_task_source_type: 'agent',
  default_comparison_method: 'exact'
})

const rules = {
  name: [{ required: true, message: '请输入评测集名称', trigger: 'blur' }],
  folder_id: [{ required: true, message: '请选择文件夹', trigger: 'change' }]
}

async function loadFolders() {
  if (!currentSpace.value?.id) return
  try {
    const data = await evalApi.getEvalFolders(currentSpace.value.id)
    folders.value = data || []
    // 默认选中第一个文件夹
    if (folders.value.length > 0 && !form.folder_id) {
      form.folder_id = folders.value[0].id
    }
  } catch (e) {
    console.error('加载文件夹失败:', e)
  }
}

async function loadTags() {
  if (!currentSpace.value?.id) return
  try {
    const data = await evalApi.getEvalTags(currentSpace.value.id)
    availableTags.value = data || []
  } catch (e) {
    console.error('加载标签失败:', e)
  }
}

// 标签变更（处理 inline 创建）
async function handleTagChange(values) {
  for (const val of values) {
    if (typeof val === 'string') {
      try {
        const newTag = await evalApi.createEvalTag(currentSpace.value.id, { name: val, color: '#409EFF' })
        availableTags.value.push(newTag)
        const idx = form.tag_ids.indexOf(val)
        if (idx !== -1) {
          form.tag_ids.splice(idx, 1, newTag.id)
        }
        ElMessage.success(`已创建标签"${val}"`)
      } catch (e) {
        ElMessage.error('创建标签失败: ' + e.message)
        const idx = form.tag_ids.indexOf(val)
        if (idx !== -1) {
          form.tag_ids.splice(idx, 1)
        }
      }
    }
  }
}

function handleCancel() {
  router.back()
}

async function handleSubmit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch (e) {
    return
  }

  submitting.value = true
  try {
    const data = {
      name: form.name,
      folder_id: form.folder_id,
      description: form.description,
      tag_ids: form.tag_ids,
      default_task_source_type: form.default_task_source_type,
      default_comparison_method: form.default_comparison_method
    }

    const result = await evalApi.createEvalSuite(currentSpace.value.id, data)
    ElMessage.success('创建成功')
    router.push(`/eval/suite/${result.id}`)
  } catch (e) {
    ElMessage.error('创建失败: ' + e.message)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadFolders()
  loadTags()
})
</script>

<style scoped>
.eval-suite-create {
  padding: 28px 32px;
  display: flex;
  justify-content: center;
}

.create-container {
  width: 100%;
  max-width: 640px;
}

.create-header {
  margin-bottom: 32px;
}

.create-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.create-desc {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.create-form {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 32px;
  margin-bottom: 24px;
}

.create-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
