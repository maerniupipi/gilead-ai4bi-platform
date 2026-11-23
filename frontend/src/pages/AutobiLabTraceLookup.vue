<template>
  <div class="trace-lookup-page">
    <PageHeader
      :breadcrumbs="[{ label: '实验中心', to: { name: 'AutoBIList' } }, { label: '追踪日志' }]"
    />
    <el-card shadow="never" class="trace-lookup-card">
      <p class="trace-lookup-desc">
        输入单次提问生成的追踪 ID（UUID），查看已写入 Redis 的各步骤请求与返回。与实验室内「调试信息」展示结构一致。
      </p>
      <el-input
        v-model="traceIdInput"
        placeholder="粘贴 trace_id，例如 550e8400-e29b-41d4-a716-446655440000"
        clearable
        class="trace-lookup-input"
        @keyup.enter="goView"
      />
      <div class="trace-lookup-actions">
        <el-button type="primary" @click="goView">查看日志</el-button>
        <el-button @click="$router.push({ name: 'AutoBIList' })">返回实验中心</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const traceIdInput = ref('')

function goView() {
  const id = traceIdInput.value.trim()
  if (!id) {
    ElMessage.warning('请输入追踪 ID')
    return
  }
  router.push({ name: 'AutobiLabTraceView', params: { traceId: id } })
}
</script>

<style scoped>
.trace-lookup-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.trace-lookup-desc {
  margin: 0 0 20px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.trace-lookup-input {
  margin-bottom: 16px;
  max-width: 560px;
}

.trace-lookup-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
</style>
