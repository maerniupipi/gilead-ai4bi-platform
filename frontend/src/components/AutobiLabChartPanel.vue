<template>
  <div v-if="spec && sqlData?.rows?.length" class="lab-chart-panel">
    <div class="lab-chart-head">
      <span class="lab-chart-title">数据可视化</span>
      <span v-if="spec.type" class="lab-chart-hint">模型建议：{{ typeLabel(spec.type) }}</span>
    </div>
    <el-alert
      v-if="spec.error"
      type="warning"
      :closable="false"
      show-icon
      class="lab-chart-alert"
      :title="spec.error"
      :description="spec.detail || undefined"
    />
    <el-tabs v-model="activeTab" class="lab-chart-tabs" @tab-change="onTabChange">
      <el-tab-pane label="柱状图" name="bar">
        <div ref="barRef" class="lab-chart-canvas" />
      </el-tab-pane>
      <el-tab-pane label="饼图" name="pie">
        <div ref="pieRef" class="lab-chart-canvas" />
      </el-tab-pane>
      <el-tab-pane label="折线图" name="line">
        <div ref="lineRef" class="lab-chart-canvas" />
      </el-tab-pane>
      <el-tab-pane label="数据表格" name="table">
        <div class="lab-chart-table-wrap">
          <el-table :data="sqlData.rows" size="small" border stripe max-height="320">
            <el-table-column
              v-for="col in sqlData.columns"
              :key="col"
              :prop="col"
              :label="col"
              min-width="100"
              show-overflow-tooltip
            />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import {
  buildBarLineOptions,
  buildPieOptions,
  chartTypeToTabKey
} from '../utils/autobiLabChartSpec.js'

const props = defineProps({
  spec: { type: Object, default: null },
  sqlData: { type: Object, default: null }
})

const activeTab = ref('bar')
const barRef = ref(null)
const pieRef = ref(null)
const lineRef = ref(null)

/** @type {import('echarts').EChartsType[]} */
const instances = []

function typeLabel(t) {
  const m = { A: '柱状图', B: '折线图', C: '饼图', D: '表格' }
  return m[t] || t
}

function disposeAll() {
  while (instances.length) {
    const c = instances.pop()
    try {
      c.dispose()
    } catch {
      /* ignore */
    }
  }
}

function getOrCreateChart(dom) {
  if (!dom) return null
  let chart = echarts.getInstanceByDom(dom)
  if (!chart) chart = echarts.init(dom)
  if (!instances.includes(chart)) instances.push(chart)
  return chart
}

function renderCharts() {
  const spec = props.spec
  const sql = props.sqlData
  if (!spec || !sql?.rows?.length) return

  nextTick(() => {
    const bar = getOrCreateChart(barRef.value)
    if (bar) bar.setOption(buildBarLineOptions(spec, sql, 'bar'), true)

    const pie = getOrCreateChart(pieRef.value)
    if (pie) pie.setOption(buildPieOptions(spec, sql), true)

    const line = getOrCreateChart(lineRef.value)
    if (line) line.setOption(buildBarLineOptions(spec, sql, 'line'), true)

    onTabChange()
  })
}

function onTabChange() {
  nextTick(() => {
    instances.forEach(c => {
      try {
        c.resize()
      } catch {
        /* ignore */
      }
    })
  })
}

function onWinResize() {
  instances.forEach(c => {
    try {
      c.resize()
    } catch {
      /* ignore */
    }
  })
}

onMounted(() => {
  activeTab.value = chartTypeToTabKey(props.spec?.type)
  renderCharts()
  window.addEventListener('resize', onWinResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWinResize)
  disposeAll()
})

watch(
  () => [props.spec, props.sqlData],
  () => {
    disposeAll()
    activeTab.value = chartTypeToTabKey(props.spec?.type)
    renderCharts()
  },
  { deep: true }
)
</script>

<style scoped>
.lab-chart-panel {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(91, 143, 249, 0.2);
  box-shadow: 0 4px 20px rgba(80, 120, 200, 0.08);
}

.lab-chart-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.lab-chart-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.lab-chart-hint {
  font-size: 12px;
  color: #909399;
}

.lab-chart-alert {
  margin-bottom: 10px;
}

.lab-chart-tabs :deep(.el-tabs__header) {
  margin-bottom: 8px;
}

.lab-chart-canvas {
  width: 100%;
  height: 300px;
}

.lab-chart-table-wrap {
  padding-top: 4px;
}
</style>
