<template>
  <div class="knowledge-base-sample-library">
    <PageHeader
      :breadcrumbs="[{ label: '知识库列表', to: '/knowledge-base' }, { label: `样例库 — ${knowledgeBaseName}` }]"
    />
    
    <!-- 样例库列表 -->
    <el-card shadow="never" v-if="kbSampleLibraries.length > 0">
      <template #header>
        <div class="card-header">
          <span>已选择的样例</span>
          <el-button type="primary" @click="handleSelectSamples">
            <el-icon><Select /></el-icon>
            选择样例
          </el-button>
        </div>
      </template>
      
      <el-table :data="paginatedSamples" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="样例名称" width="200">
          <template #default="scope">
            <span>{{ scope.row.sample_name || scope.row.sample_name_cache }}</span>
          </template>
        </el-table-column>
        <el-table-column label="样例内容" show-overflow-tooltip>
          <template #default="scope">
            <el-tooltip :content="scope.row.sample_content || scope.row.sample_content_cache" placement="top">
              <div class="sample-content-text">{{ scope.row.sample_content || scope.row.sample_content_cache }}</div>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="scope">
            {{ formatDate(scope.row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="scope">
            <el-button type="danger" size="small" link @click="handleDeleteSample(scope.row)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap" v-if="kbSampleLibraries.length > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="kbSampleLibraries.length"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="() => { currentPage = 1 }"
        />
      </div>
    </el-card>
    
    <el-empty description="暂无样例" v-else>
      <el-button type="primary" @click="handleSelectSamples">
        <el-icon><Select /></el-icon>
        选择样例
      </el-button>
    </el-empty>
    
    <!-- 选择样例对话框 -->
    <el-dialog
      v-model="selectDialogVisible"
      title="选择样例"
      width="800px"
    >
      <el-card shadow="never">
        <el-table 
          :data="availableSampleLibraries" 
          stripe 
          style="width: 100%"
          @select="handleSampleSelect"
          @select-all="handleSampleSelectAll"
        >
          <el-table-column type="selection" width="55" />
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="sample_name" label="样例名称" width="200" />
          <el-table-column prop="sql_content" label="样例内容" show-overflow-tooltip>
            <template #default="scope">
              <el-tooltip :content="scope.row.sql_content" placement="top">
                <div class="sample-content-text">{{ scope.row.sql_content }}</div>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180">
            <template #default="scope">
              {{ formatDate(scope.row.created_at) }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
      
      <!-- 已选择的样例数量 -->
      <div class="selected-info" v-if="selectedSampleIds.length > 0">
        <span>已选择 {{ selectedSampleIds.length }} 个样例</span>
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
import sampleLibraryApi from '@/api/sampleLibrary'

const route = useRoute()
const router = useRouter()

// 知识库ID和名称
const knowledgeBaseId = ref(route.query.knowledgeBaseId)
const knowledgeBaseName = ref(route.query.knowledgeBaseName)

// 知识库样例库列表
const kbSampleLibraries = ref([])
// 可用的样例库列表
const availableSampleLibraries = ref([])
// 选择对话框
const selectDialogVisible = ref(false)
// 已选择的样例ID
const selectedSampleIds = ref([])
// 分页
const currentPage = ref(1)
const pageSize = ref(20)

const paginatedSamples = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return kbSampleLibraries.value.slice(start, start + pageSize.value)
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

// 获取知识库样例库
const getKbSampleLibraries = async () => {
  try {
    const response = await knowledgeBaseApi.getKnowledgeBase(knowledgeBaseId.value)
    kbSampleLibraries.value = response.kb_sample_libraries || []
  } catch (error) {
    ElMessage.error('获取知识库样例库失败：' + (error.response?.data?.detail || error.message))
  }
}

// 获取可用的样例库（来自知识接入）
const getAvailableSampleLibraries = async () => {
  try {
    // 首先获取知识库详情，了解其关联的知识接入ID
    const knowledgeBase = await knowledgeBaseApi.getKnowledgeBase(knowledgeBaseId.value)
    const knowledgeAccessId = knowledgeBase.knowledge_access_id
    
    // 获取该知识接入下的所有样例
    const response = await sampleLibraryApi.getSampleLibraries(knowledgeAccessId)

    availableSampleLibraries.value = response.items || []
  } catch (error) {
    ElMessage.error('获取可用样例库失败：' + (error.response?.data?.detail || error.message))
  }
}

// 选择样例
const handleSampleSelect = (selection, row) => {
  selectedSampleIds.value = selection.map(item => item.id)
}

// 全选样例
const handleSampleSelectAll = (selection) => {
  selectedSampleIds.value = selection.map(item => item.id)
}

// 选择样例
const handleSelectSamples = () => {
  selectedSampleIds.value = []
  getAvailableSampleLibraries()
  selectDialogVisible.value = true
}

// 确认选择样例
const handleConfirmSelect = async () => {
  if (selectedSampleIds.value.length === 0) {
    ElMessage.warning('请至少选择一个样例')
    return
  }
  
  try {
    await knowledgeBaseApi.batchSelectSampleLibraries(knowledgeBaseId.value, {
      ids: selectedSampleIds.value
    })
    ElMessage.success('选择样例成功')
    selectDialogVisible.value = false
    getKbSampleLibraries()
  } catch (error) {
    ElMessage.error('选择样例失败：' + (error.response?.data?.detail || error.message))
  }
}

// 删除样例
const handleDeleteSample = async (sample) => {
  try {
    await knowledgeBaseApi.deleteKbSampleLibrary(sample.id)
    ElMessage.success('删除样例成功')
    getKbSampleLibraries()
  } catch (error) {
    ElMessage.error('删除样例失败：' + (error.response?.data?.detail || error.message))
  }
}

// 页面加载时获取数据
onMounted(() => {
  getKbSampleLibraries()
})
</script>

<style scoped>
.knowledge-base-sample-library {
  padding: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sample-content-text {
  max-width: 400px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
