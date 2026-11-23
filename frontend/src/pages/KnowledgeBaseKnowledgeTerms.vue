<template>
  <div class="knowledge-base-knowledge-terms">
    <PageHeader
      :breadcrumbs="[{ label: '知识库列表', to: '/knowledge-base' }, { label: `知识词条 — ${knowledgeBaseName}` }]"
    />
    
    <!-- 知识词条列表 -->
    <el-card shadow="never" v-if="kbKnowledgeTerms.length > 0">
      <template #header>
        <div class="card-header">
          <span>已选择的知识词条</span>
          <el-button type="primary" @click="handleSelectTerms">
            <el-icon><Select /></el-icon>
            选择知识词条
          </el-button>
        </div>
      </template>
      
      <el-table :data="paginatedTerms" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="词条名称" width="200">
          <template #default="scope">
            <span>{{ scope.row.term_name || scope.row.term_name_cache }}</span>
          </template>
        </el-table-column>
        <el-table-column label="词条值" show-overflow-tooltip>
          <template #default="scope">
            <span>{{ scope.row.term_value || scope.row.term_value_cache }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="scope">
            <el-button type="danger" size="small" link @click="handleDeleteTerm(scope.row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap" v-if="kbKnowledgeTerms.length > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="kbKnowledgeTerms.length"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="() => { currentPage = 1 }"
        />
      </div>
    </el-card>
    
    <el-empty description="暂无知识词条" v-else>
      <el-button type="primary" @click="handleSelectTerms">
        <el-icon><Select /></el-icon>
        选择知识词条
      </el-button>
    </el-empty>
    
    <!-- 选择知识词条对话框 -->
    <el-dialog
      v-model="selectDialogVisible"
      title="选择知识词条"
      width="800px"
    >
      <el-card shadow="never">
        <el-table 
          :data="availableKnowledgeTerms" 
          stripe 
          style="width: 100%"
          @select="handleTermSelect"
          @select-all="handleTermSelectAll"
        >
          <el-table-column type="selection" width="55" />
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="term_name" label="词条名称" width="200" />
          <el-table-column prop="term_value" label="词条值" show-overflow-tooltip />
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="scope">
              {{ formatDate(scope.row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
      
      <!-- 已选择的词条数量 -->
      <div class="selected-info" v-if="selectedTermIds.length > 0">
        <span>已选择 {{ selectedTermIds.length }} 个知识词条</span>
      </div>
      
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="selectDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleConfirmSelect">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Select, Delete } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import knowledgeBaseApi from '@/api/knowledgeBase'
import knowledgeTermApi from '@/api/knowledgeTerm'

const route = useRoute()
const router = useRouter()

// 知识库ID和名称
const knowledgeBaseId = ref(route.query.knowledgeBaseId)
const knowledgeBaseName = ref(route.query.knowledgeBaseName)

// 知识库知识词条列表
const kbKnowledgeTerms = ref([])
// 可用的知识词条列表
const availableKnowledgeTerms = ref([])
// 选择对话框
const selectDialogVisible = ref(false)
// 已选择的词条ID
const selectedTermIds = ref([])
// 分页
const currentPage = ref(1)
const pageSize = ref(20)

const paginatedTerms = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return kbKnowledgeTerms.value.slice(start, start + pageSize.value)
})

// 验证知识库ID
if (!knowledgeBaseId.value) {
  ElMessage.error('知识库ID不能为空')
  router.push('/knowledge-base')
}

// 格式化日期
const formatDate = (dateString) => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN')
}

// 获取知识库知识词条
const getKbKnowledgeTerms = async () => {
  try {
    const response = await knowledgeBaseApi.getKnowledgeBase(knowledgeBaseId.value)
    kbKnowledgeTerms.value = response.kb_knowledge_terms || []
  } catch (error) {
    ElMessage.error('获取知识库知识词条失败：' + (error.response?.data?.detail || error.message))
  }
}

// 获取可用的知识词条（来自知识接入）
const getAvailableKnowledgeTerms = async () => {
  try {
    // 首先获取知识库详情，了解其关联的知识接入ID
    const knowledgeBase = await knowledgeBaseApi.getKnowledgeBase(knowledgeBaseId.value)
    const knowledgeAccessId = knowledgeBase.knowledge_access_id
    
    // 获取该知识接入下的所有知识词条（无分页）
    const response = await knowledgeTermApi.getAllKnowledgeTerms(knowledgeAccessId)

    availableKnowledgeTerms.value = response || []
  } catch (error) {
    ElMessage.error('获取可用知识词条失败：' + (error.response?.data?.detail || error.message))
  }
}

// 选择词条
const handleTermSelect = (selection, row) => {
  selectedTermIds.value = selection.map(item => item.id)
}

// 全选词条
const handleTermSelectAll = (selection) => {
  selectedTermIds.value = selection.map(item => item.id)
}

// 选择知识词条
const handleSelectTerms = () => {
  selectedTermIds.value = []
  getAvailableKnowledgeTerms()
  selectDialogVisible.value = true
}

// 确认选择知识词条
const handleConfirmSelect = async () => {
  if (selectedTermIds.value.length === 0) {
    ElMessage.warning('请至少选择一个知识词条')
    return
  }
  
  try {
    await knowledgeBaseApi.batchSelectKnowledgeTerms(knowledgeBaseId.value, {
      ids: selectedTermIds.value
    })
    ElMessage.success('选择知识词条成功')
    selectDialogVisible.value = false
    getKbKnowledgeTerms()
  } catch (error) {
    ElMessage.error('选择知识词条失败：' + (error.response?.data?.detail || error.message))
  }
}

// 删除知识词条
const handleDeleteTerm = async (term) => {
  try {
    await knowledgeBaseApi.deleteKbKnowledgeTerm(term.id)
    ElMessage.success('删除知识词条成功')
    getKbKnowledgeTerms()
  } catch (error) {
    ElMessage.error('删除知识词条失败：' + (error.response?.data?.detail || error.message))
  }
}

// 页面加载时获取数据
onMounted(() => {
  getKbKnowledgeTerms()
})
</script>

<style scoped>
.knowledge-base-knowledge-terms {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.selected-info {
  padding: 10px;
  text-align: right;
  color: #606266;
}

.dialog-footer {
  text-align: right;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
