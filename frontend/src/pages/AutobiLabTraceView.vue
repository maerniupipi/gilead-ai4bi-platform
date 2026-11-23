<template>
  <div class="trace-view-page">
    <header class="trace-view-head">
      <div class="trace-view-head-row">
        <h1 class="trace-view-title">流水线日志</h1>
        <div class="trace-view-actions">
          <el-button text type="primary" @click="router.push({ name: 'AutobiLabTraceLookup' })">
            返回查询
          </el-button>
          <el-button text type="primary" @click="router.push({ name: 'AutoBIList' })">实验中心列表</el-button>
        </div>
      </div>
      <div v-if="trace" class="trace-meta">
        <div class="trace-meta-line">
          <span class="label">追踪 ID</span>
          <code class="trace-id">{{ trace.trace_id }}</code>
          <el-button size="small" @click="copyId">复制</el-button>
        </div>
        <div class="trace-meta-line">
          <span class="label">项目</span>
          <span>{{ trace.project_name || trace.project_id }}</span>
        </div>
        <div class="trace-meta-line">
          <span class="label">提问</span>
          <span class="user-q">{{ trace.user_message }}</span>
        </div>
        <div v-if="trace.updated_at" class="trace-meta-line muted">
          <span class="label">更新</span>
          <span>{{ formatTime(trace.updated_at) }}</span>
        </div>
      </div>
      <div v-else-if="!loading && errorMsg" class="trace-error">{{ errorMsg }}</div>
    </header>

    <main class="trace-view-body">
      <el-skeleton v-if="loading" :rows="8" animated />
      <AutobiLabStepCards v-else :rows="normalizedSteps" show-step-uuid />
    </main>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getAutobiLabTrace } from '../api/autobiLabTrace'
import AutobiLabStepCards from '../components/AutobiLabStepCards.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const errorMsg = ref('')
const trace = ref(null)

const normalizedSteps = computed(() => {
  const steps = trace.value?.steps
  if (!Array.isArray(steps)) return []
  return steps.map(s => ({
    stepUuid: s.step_uuid,
    meta: {
      stepId: s.step_id,
      title: s.title,
      apiKey: s.api_key,
      color: s.color
    },
    status: s.status,
    request: s.request,
    response: s.response,
    error: s.error,
    durationMs: s.duration_ms
  }))
})

function formatTime(ms) {
  if (ms == null) return ''
  const d = new Date(ms)
  return d.toLocaleString()
}

async function load() {
  const id = route.params.traceId
  if (!id) {
    errorMsg.value = '缺少 trace_id'
    trace.value = null
    loading.value = false
    return
  }
  loading.value = true
  errorMsg.value = ''
  trace.value = null
  try {
    trace.value = await getAutobiLabTrace(String(id))
  } catch (e) {
    errorMsg.value = e.message || '加载失败'
    ElMessage.error(errorMsg.value)
  } finally {
    loading.value = false
  }
}

function copyId() {
  const id = trace.value?.trace_id
  if (!id) return
  navigator.clipboard.writeText(id).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.warning('复制失败')
  )
}

watch(
  () => route.params.traceId,
  () => load(),
  { immediate: true }
)
</script>

<style scoped>
.trace-view-page {
  flex: 1;
  min-height: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  background: linear-gradient(165deg, #dce8ff 0%, #eef3ff 35%, #f0f4ff 70%, #e8ecfa 100%);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  overflow: hidden;
}

.trace-view-head {
  flex-shrink: 0;
  width: 100%;
  max-width: min(1120px, 100%);
  margin: 0 auto;
  padding: 20px 40px 12px;
  box-sizing: border-box;
}

.trace-view-head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.trace-view-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.trace-view-actions {
  display: flex;
  gap: 4px;
}

.trace-meta {
  padding: 16px 18px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 4px 24px rgba(80, 100, 200, 0.08);
}

.trace-meta-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 13px;
  color: #303133;
}

.trace-meta-line:last-child {
  margin-bottom: 0;
}

.trace-meta-line.muted {
  color: #909399;
  font-size: 12px;
}

.trace-meta-line .label {
  flex: 0 0 56px;
  color: #909399;
  font-size: 12px;
}

.trace-id {
  font-size: 12px;
  word-break: break-all;
  flex: 1;
  min-width: 0;
}

.user-q {
  flex: 1;
  min-width: 0;
  white-space: pre-wrap;
}

.trace-error {
  color: #f56c6c;
  font-size: 14px;
}

.trace-view-body {
  flex: 1;
  min-height: 0;
  width: 100%;
  max-width: min(1120px, 100%);
  margin: 0 auto;
  padding: 8px 40px 28px;
  box-sizing: border-box;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
