<template>
  <div class="autobi-atomic-capabilities">
    <PageHeader
      :breadcrumbs="[{ label: '实验中心 · 原子能力' }]"
    />
    <el-tabs v-model="activeTab" type="border-card" @tab-change="handleTabChange">
      <el-tab-pane label="ES表值召回" name="elasticsearch-value-retriever">
        <CapabilityPanel
          title="ES表值召回"
          api-name="elasticsearch-value-retriever"
          :input-fields="esValueInputFields"
          @execute="handleExecute"
        />
      </el-tab-pane>
      <el-tab-pane label="ES知识词召回" name="elasticsearch-knowledge-retriever">
        <CapabilityPanel
          title="ES知识词召回"
          api-name="elasticsearch-knowledge-retriever"
          :input-fields="esKnowledgeInputFields"
          @execute="handleExecute"
        />
      </el-tab-pane>
      <el-tab-pane label="SQL样例召回" name="sql-template-retriever">
        <CapabilityPanel
          title="SQL样例召回"
          api-name="sql-template-retriever"
          :input-fields="sqlTemplateInputFields"
          @execute="handleExecute"
        />
      </el-tab-pane>
      <el-tab-pane label="表字段召回" name="table-meta-retriever">
        <CapabilityPanel
          title="表字段召回"
          api-name="table-meta-retriever"
          :input-fields="tableMetaInputFields"
          @execute="handleExecute"
        />
      </el-tab-pane>
      <el-tab-pane label="表值召回" name="table-value-retriever">
        <CapabilityPanel
          title="表值召回"
          api-name="table-value-retriever"
          :input-fields="tableValueInputFields"
          @execute="handleExecute"
        />
      </el-tab-pane>
      <el-tab-pane label="表值召回(对应字段)" name="global-value-meta-retriever">
        <CapabilityPanel
          title="表值召回(对应字段)"
          api-name="global-value-meta-retriever"
          :input-fields="globalValueInputFields"
          @execute="handleExecute"
        />
      </el-tab-pane>
      <el-tab-pane label="多列同值" name="multi-global-value-meta-retriever">
        <CapabilityPanel
          title="多列同值"
          api-name="multi-global-value-meta-retriever"
          :input-fields="multiGlobalValueInputFields"
          @execute="handleExecute"
        />
      </el-tab-pane>
      <el-tab-pane label="NER" name="ner-retriever">
        <CapabilityPanel
          title="NER"
          api-name="ner-retriever"
          :input-fields="nerInputFields"
          @execute="handleExecute"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import CapabilityPanel from '../components/CapabilityPanel.vue'
import {
  esValueRetriever,
  esKnowledgeRetriever,
  sqlTemplateRetriever,
  tableMetaRetriever,
  tableValueRetriever,
  globalValueMetaRetriever,
  multiGlobalValueMetaRetriever,
  nerRetriever
} from '../api/autobiAtomic'
import knowledgeBaseApi from '../api/knowledgeBase'

const activeTab = ref('elasticsearch-value-retriever')
const knowledgeBaseOptions = ref([])

// 获取知识库列表
const fetchKnowledgeBases = async () => {
  try {
    const res = await knowledgeBaseApi.getKnowledgeBaseList()
    if (res) {
      knowledgeBaseOptions.value = res.map(kb => ({
        value: kb.id,
        label: `${kb.name} (ID: ${kb.id})`
      }))
    }
  } catch (error) {
    console.error('获取知识库列表失败:', error)
  }
}

onMounted(() => {
  fetchKnowledgeBases()
})

// ES 表值：索引 es_kb{knowledge_base_id}_table_value；query 可为字符串或数组；分数在服务端按批归一化
const esValueInputFields = [
  { key: 'knowledge_base_id', label: '知识库', type: 'select', required: true, placeholder: '请选择知识库', options: knowledgeBaseOptions },
  {
    key: 'request_body',
    label: '请求Body (JSON)',
    type: 'textarea',
    required: true,
    placeholder:
      '{\n  "query": "关键词或自然语言",\n  "top_k": 5,\n  "score_threshold": null\n}',
    default:
      '{\n  "query": "",\n  "top_k": 5,\n  "score_threshold": null\n}',
    rows: 12
  }
]

// ES 知识词：索引 es_kb{knowledge_base_id}_knowledge；match data_detail
const esKnowledgeInputFields = [
  { key: 'knowledge_base_id', label: '知识库', type: 'select', required: true, placeholder: '请选择知识库', options: knowledgeBaseOptions },
  {
    key: 'request_body',
    label: '请求Body (JSON)',
    type: 'textarea',
    required: true,
    placeholder:
      '{\n  "query": "问题或关键词",\n  "top_k": 8,\n  "score_threshold": null\n}',
    default:
      '{\n  "query": "",\n  "top_k": 8,\n  "score_threshold": null\n}',
    rows: 12
  }
]

// SQL 样例召回：Milvus field_type=sql_sample；可选 top_k、score_threshold
const sqlTemplateInputFields = [
  { key: 'knowledge_base_id', label: '知识库', type: 'select', required: true, placeholder: '请选择知识库', options: knowledgeBaseOptions },
  {
    key: 'request_body',
    label: '请求Body (JSON)',
    type: 'textarea',
    required: true,
    placeholder:
      '{\n  "query": "自然语言问题",\n  "top_k": 5,\n  "score_threshold": null\n}',
    default:
      '{\n  "query": "",\n  "top_k": 5,\n  "score_threshold": null\n}',
    rows: 12
  }
]

// 表字段召回：Milvus field_type=table_column；默认 score_threshold 0.3
const tableMetaInputFields = [
  { key: 'knowledge_base_id', label: '知识库', type: 'select', required: true, placeholder: '请选择知识库', options: knowledgeBaseOptions },
  {
    key: 'request_body',
    label: '请求Body (JSON)',
    type: 'textarea',
    required: true,
    placeholder:
      '{\n  "query": "自然语言问题",\n  "top_k": 15,\n  "score_threshold": 0.3\n}',
    default:
      '{\n  "query": "",\n  "top_k": 15,\n  "score_threshold": 0.3\n}',
    rows: 12
  }
]

// 表值召回：Milvus field_type=table_value；可选 ES 回退
const tableValueInputFields = [
  { key: 'knowledge_base_id', label: '知识库', type: 'select', required: true, placeholder: '请选择知识库', options: knowledgeBaseOptions },
  {
    key: 'request_body',
    label: '请求Body (JSON)',
    type: 'textarea',
    required: true,
    placeholder:
      '{\n  "query": "自然语言",\n  "table_name": "物理表名（可选）",\n  "top_k": 6,\n  "score_threshold": null\n}',
    default:
      '{\n  "query": "",\n  "table_name": null,\n  "top_k": 6,\n  "score_threshold": null\n}',
    rows: 12
  }
]

// 表值召回(对应字段)：table_name 推荐 表名.字段名（或 表名&&字段名 等与存储一致），或仅表名
const globalValueInputFields = [
  { key: 'knowledge_base_id', label: '知识库', type: 'select', required: true, placeholder: '请选择知识库', options: knowledgeBaseOptions },
  {
    key: 'request_body',
    label: '请求Body (JSON)',
    type: 'textarea',
    required: true,
    placeholder:
      '{\n  "query": "自然语言",\n  "table_name": "表名.字段名（推荐）或 表名&&字段名（可选）",\n  "top_k": 10,\n  "score_threshold": null\n}',
    default:
      '{\n  "query": "",\n  "table_name": null,\n  "top_k": 10,\n  "score_threshold": null\n}',
    rows: 14
  }
]

// 多列同值：向量和关键词各取 top_k，保持原顺序去重，每字段最多 2*top_k
const multiGlobalValueInputFields = [
  { key: 'knowledge_base_id', label: '知识库', type: 'select', required: true, placeholder: '请选择知识库', options: knowledgeBaseOptions },
  {
    key: 'request_body',
    label: '请求Body (JSON)',
    type: 'textarea',
    required: true,
    placeholder:
      '{\n  "query": "自然语言",\n  "table_name": ["表A.列1", "表B.列2"],\n  "top_k": 6,\n  "score_threshold": null,\n  "keyword_score_threshold": null\n}',
    default:
      '{\n  "query": "",\n  "table_name": ["表名.字段名"],\n  "top_k": 6,\n  "score_threshold": null,\n  "keyword_score_threshold": null\n}',
    rows: 16
  }
]

// NER：entity 为字符串数组；按别名包含实体子串查 kb_ner_row
const nerInputFields = [
  { key: 'knowledge_base_id', label: '知识库', type: 'select', required: true, placeholder: '请选择知识库', options: knowledgeBaseOptions },
  {
    key: 'request_body',
    label: '请求Body (JSON)',
    type: 'textarea',
    required: true,
    placeholder:
      '{\n  "query": "用户问题（用于生成说明）",\n  "entity": ["上海", "年份"],\n  "top_k": 20\n}',
    default:
      '{\n  "query": "",\n  "entity": ["上海", "年份"],\n  "top_k": 20\n}',
    rows: 14
  }
]

// API映射表
const apiMap = {
  'elasticsearch-value-retriever': esValueRetriever,
  'elasticsearch-knowledge-retriever': esKnowledgeRetriever,
  'sql-template-retriever': sqlTemplateRetriever,
  'table-meta-retriever': tableMetaRetriever,
  'table-value-retriever': tableValueRetriever,
  'global-value-meta-retriever': globalValueMetaRetriever,
  'multi-global-value-meta-retriever': multiGlobalValueMetaRetriever,
  'ner-retriever': nerRetriever
}

const handleTabChange = () => {
  // 切换tab时清空结果
}

const handleExecute = async (apiName, formData, callback) => {
  try {
    const api = apiMap[apiName]
    if (!api) {
      ElMessage.error('未知的API类型')
      callback({ error: '未知的API类型' })
      return
    }

    // 知识库ID作为URL参数
    const knowledgeBaseId = parseInt(formData.knowledge_base_id)
    if (!knowledgeBaseId) {
      ElMessage.error('请选择知识库')
      callback({ error: '请选择知识库' })
      return
    }

    // 解析请求Body JSON
    let requestData
    try {
      requestData = JSON.parse(formData.request_body || '{}')
    } catch (e) {
      ElMessage.error('请求Body JSON格式错误')
      callback({ error: '请求Body JSON格式错误' })
      return
    }

    const data = await api(knowledgeBaseId, requestData)

    if (data && (Array.isArray(data.results) || Object.prototype.hasOwnProperty.call(data, 'sql') || Array.isArray(data.rows))) {
      callback({ success: true, data })
    } else {
      callback({ error: '返回数据格式异常' })
    }
  } catch (error) {
    const errorMsg = error.response?.data?.detail || error.message || '请求异常'
    ElMessage.error(errorMsg)
    callback({ error: errorMsg })
  }
}
</script>

<style scoped>

.autobi-atomic-capabilities h2 {
  margin-bottom: 20px;
  color: #303133;
}
</style>
