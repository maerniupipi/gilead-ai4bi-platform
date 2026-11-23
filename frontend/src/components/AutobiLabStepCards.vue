<template>
  <div class="lab-step-cards">
    <div
      v-for="row in rows"
      :key="row.stepUuid || row.meta?.stepId"
      class="lab-step-card"
      :style="{ borderLeftColor: row.meta?.color || '#5b8ff9' }"
    >
      <div class="lab-step-head">
        <span class="lab-step-num">{{ row.meta?.stepId }}</span>
        <span class="lab-step-title">{{ row.meta?.title }}</span>
        <el-tag size="small" :type="tagType(row.status)" class="lab-step-tag">
          {{ row.meta?.apiKey }}
        </el-tag>
      </div>
      <div v-if="showStepUuid && row.stepUuid" class="lab-step-uuid" title="步骤 UUID">
        {{ row.stepUuid }}
      </div>
      <div class="lab-step-status-line">
        <span :class="['lab-step-state', row.status]">{{ statusText(row.status) }}</span>
        <span v-if="row.durationMs != null" class="lab-step-dur">{{ row.durationMs }} ms</span>
      </div>
      <el-collapse v-if="row.status !== 'pending' && row.status !== 'running'">
        <el-collapse-item title="请求参数" :name="`req-${row.meta?.stepId}-${row.stepUuid}`">
          <pre class="lab-json">{{ pretty(row.request) }}</pre>
        </el-collapse-item>
        <el-collapse-item title="返回参数" :name="`res-${row.meta?.stepId}-${row.stepUuid}`">
          <pre class="lab-json">{{ row.error || pretty(row.response) }}</pre>
        </el-collapse-item>
      </el-collapse>
      <el-collapse v-else-if="row.status === 'running'">
        <el-collapse-item title="请求参数（进行中）" :name="`run-${row.meta?.stepId}`">
          <pre class="lab-json">{{ pretty(row.request) }}</pre>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup>
defineProps({
  rows: {
    type: Array,
    default: () => []
  },
  showStepUuid: {
    type: Boolean,
    default: false
  }
})

function tagType(status) {
  if (status === 'done') return 'success'
  if (status === 'error') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

function statusText(s) {
  const m = { pending: '待执行', running: '执行中', done: '完成', error: '失败' }
  return m[s] || s
}

function pretty(obj) {
  if (obj == null) return ''
  if (typeof obj === 'string') return obj
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}
</script>

<style scoped>
.lab-step-cards {
  width: 100%;
}

.lab-step-card {
  margin-bottom: 12px;
  padding: 10px 10px 6px;
  border-radius: 10px;
  background: #fafbff;
  border-left: 4px solid #5b8ff9;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.lab-step-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.lab-step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 6px;
  background: #e9f8fa;
  color: #1fb8cc;
  font-size: 11px;
  font-weight: 700;
}

.lab-step-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.lab-step-tag {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lab-step-uuid {
  font-size: 10px;
  color: #909399;
  word-break: break-all;
  margin: -2px 0 6px;
  font-family: ui-monospace, monospace;
}

.lab-step-status-line {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  margin-bottom: 6px;
  color: #909399;
}

.lab-step-state.running {
  color: #e6a23c;
}

.lab-step-state.done {
  color: #67c23a;
}

.lab-step-state.error {
  color: #f56c6c;
}

.lab-step-dur {
  color: #c0c4cc;
}

.lab-json {
  margin: 0;
  padding: 8px;
  font-size: 11px;
  line-height: 1.45;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 6px;
  overflow-x: auto;
  max-height: 220px;
}

.lab-step-card :deep(.el-collapse) {
  border: none;
}

.lab-step-card :deep(.el-collapse-item__header) {
  height: 32px;
  line-height: 32px;
  font-size: 12px;
  background: transparent;
}

.lab-step-card :deep(.el-collapse-item__wrap) {
  border: none;
}

.lab-step-card :deep(.el-collapse-item__content) {
  padding-bottom: 8px;
}
</style>
