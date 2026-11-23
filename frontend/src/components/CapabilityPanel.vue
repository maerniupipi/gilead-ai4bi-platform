<template>
  <div class="capability-panel">
    <div class="panel-header">
      <h3>{{ title }}</h3>
    </div>
    
    <div class="panel-content">
      <!-- 左侧：输入参数 -->
      <div class="input-section">
        <div class="section-title">
          <el-icon><Edit /></el-icon>
          <span>输入参数</span>
        </div>
        
        <el-form :model="formData" label-position="top" class="input-form">
          <el-form-item
            v-for="field in inputFields"
            :key="field.key"
            :label="field.label"
            :required="field.required"
          >
            <el-input
              v-if="field.type === 'text'"
              v-model="formData[field.key]"
              :placeholder="field.placeholder"
              clearable
            />
            <el-input
              v-else-if="field.type === 'textarea'"
              v-model="formData[field.key]"
              type="textarea"
              :rows="field.rows || 4"
              :placeholder="field.placeholder"
            />
            <el-input-number
              v-else-if="field.type === 'number'"
              v-model="formData[field.key]"
              :placeholder="field.placeholder"
              :min="1"
              style="width: 100%"
            />
            <el-select
              v-else-if="field.type === 'select'"
              v-model="formData[field.key]"
              :placeholder="field.placeholder"
              style="width: 100%"
              clearable
            >
              <el-option
                v-for="option in (field.options?.value || field.options)"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </el-form-item>
          
          <el-form-item>
            <el-button
              type="primary"
              :disabled="loading"
              @click="handleExecute"
              style="width: 100%"
            >
              <el-icon v-if="!loading"><Pointer /></el-icon>
              <el-icon v-else class="is-loading"><Loading /></el-icon>
              <span>{{ loading ? '运行中...' : '执行API调用' }}</span>
            </el-button>
          </el-form-item>
        </el-form>
      </div>
      
      <!-- 右侧：返回结果 -->
      <div class="output-section">
        <div class="section-title">
          <el-icon><Document /></el-icon>
          <span>返回结果</span>
        </div>
        
        <div class="output-content">
          <div v-if="!result && !loading" class="empty-state">
            <el-icon :size="48"><Document /></el-icon>
            <p>点击"执行API调用"查看结果</p>
          </div>
          
          <div v-else-if="loading" class="loading-state">
            <el-icon :size="32" class="is-loading"><Loading /></el-icon>
            <p>正在执行...</p>
          </div>
          
          <div v-else-if="result && result.error" class="error-state">
            <el-icon :size="32" color="#f56c6c"><CircleClose /></el-icon>
            <p class="error-message">{{ result.error }}</p>
          </div>
          
          <div v-else-if="result && result.success" class="success-state">
            <div class="result-summary">
              <el-tag type="success" size="large">成功</el-tag>
              <span class="result-count">共 {{ result.data?.total || 0 }} 条结果</span>
            </div>

            <div v-if="result.data?.narrative" class="ner-narrative-block">
              <div class="raw-json-title">自然语言摘要</div>
              <pre class="narrative-pre">{{ result.data.narrative }}</pre>
            </div>
            
            <div v-if="result.data?.results?.length" class="result-list">
              <div
                v-for="(item, index) in result.data.results"
                :key="index"
                class="result-item"
              >
                <div class="result-header">
                  <span class="result-index">#{{ index + 1 }}</span>
                  <el-tag type="primary" size="small">score: {{ item.score?.toFixed(4) }}</el-tag>
                </div>
                <div class="result-content">{{ item.content }}</div>
                <div v-if="item.metadata" class="result-metadata">
                  <el-tag
                    v-for="(value, key) in item.metadata"
                    :key="key"
                    type="info"
                    size="small"
                    class="metadata-tag"
                  >
                    {{ key }}: {{ value }}
                  </el-tag>
                </div>
              </div>
            </div>
            
            <div class="raw-json">
              <div class="raw-json-title">原始JSON响应：</div>
              <pre>{{ JSON.stringify(result.data, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { Edit, Document, Pointer, Loading, CircleClose } from '@element-plus/icons-vue'

const props = defineProps({
  title: {
    type: String,
    required: true
  },
  apiName: {
    type: String,
    required: true
  },
  inputFields: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['execute'])

const loading = ref(false)
const result = ref(null)

// 初始化表单数据
const formData = reactive({})

// 根据inputFields初始化formData
const initFormData = () => {
  props.inputFields.forEach(field => {
    formData[field.key] = field.default !== undefined ? field.default : ''
  })
}

initFormData()

// 监听inputFields变化，重新初始化
watch(() => props.inputFields, () => {
  Object.keys(formData).forEach(key => delete formData[key])
  initFormData()
  result.value = null
}, { deep: true })

const handleExecute = async () => {
  // 验证必填字段
  for (const field of props.inputFields) {
    if (field.required && !formData[field.key]) {
      return
    }
  }
  
  loading.value = true
  result.value = null
  
  emit('execute', props.apiName, { ...formData }, (response) => {
    result.value = response
    loading.value = false
  })
}
</script>

<style scoped>
.capability-panel {
  background: #fff;
  border-radius: 8px;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid #e4e7ed;
  background: #f5f7fa;
  border-radius: 8px 8px 0 0;
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.panel-content {
  display: flex;
  min-height: 500px;
}

.input-section {
  width: 40%;
  padding: 20px;
  border-right: 1px solid #e4e7ed;
}

.output-section {
  width: 60%;
  padding: 20px;
  background: #fafafa;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 16px;
}

.input-form {
  :deep(.el-form-item__label) {
    font-weight: 500;
  }
}

.output-content {
  min-height: 400px;
}

.empty-state,
.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: #909399;
  gap: 16px;
}

.error-state .error-message {
  color: #f56c6c;
  max-width: 80%;
  text-align: center;
}

.success-state {
  .ner-narrative-block {
    margin-bottom: 16px;
  }

  .narrative-pre {
    margin: 0;
    padding: 12px;
    background: #f0f9eb;
    border: 1px solid #e1f3d8;
    border-radius: 6px;
    font-size: 13px;
    line-height: 1.6;
    white-space: pre-wrap;
    color: #303133;
  }

  .result-summary {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #e4e7ed;
  }
  
  .result-count {
    color: #606266;
    font-size: 14px;
  }
  
  .result-list {
    max-height: 300px;
    overflow-y: auto;
    margin-bottom: 16px;
  }
  
  .result-item {
    background: #fff;
    border: 1px solid #e4e7ed;
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 12px;
  }
  
  .result-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
  }
  
  .result-index {
    font-weight: 600;
    color: #409eff;
  }
  
  .result-content {
    color: #303133;
    font-size: 14px;
    line-height: 1.5;
    margin-bottom: 8px;
    word-break: break-all;
  }
  
  .result-metadata {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  
  .metadata-tag {
    font-size: 11px;
  }
  
  .raw-json {
    background: #2d2d2d;
    border-radius: 6px;
    padding: 12px;
    margin-top: 16px;
  }
  
  .raw-json-title {
    color: #909399;
    font-size: 12px;
    margin-bottom: 8px;
  }
  
  .raw-json pre {
    color: #7ee787;
    font-size: 12px;
    line-height: 1.5;
    overflow-x: auto;
    margin: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
}

.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
