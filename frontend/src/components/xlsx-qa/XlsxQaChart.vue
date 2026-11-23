<template>
  <div
    v-if="chart && chart.chart_type && chart.chart_type !== 'none'"
    class="xq-chart"
    :class="[`xq-chart--${size}`, `xq-chart--type-${chart.chart_type}`]"
  >
    <div class="xq-chart-head">
      <span class="xq-chart-tag" :class="`tag-${chart.chart_type}`">{{ chartTypeLabel }}</span>
      <span v-if="chart.title" class="xq-chart-title">{{ chart.title }}</span>
    </div>
    <div v-if="chart.explain" class="xq-chart-explain">{{ chart.explain }}</div>

    <!-- 图形：bar / line / pie -->
    <template v-if="isGraphical">
      <!-- 柱状图：支持横向滚动 -->
      <div
        v-if="chart.chart_type === 'bar'"
        class="xq-chart-bar-wrap"
        :style="barWrapStyle"
      >
        <div ref="chartEl" class="xq-chart-canvas" :style="barCanvasStyle" />
      </div>
      <!-- 折线图 -->
      <div v-else-if="chart.chart_type === 'line'" ref="chartEl" class="xq-chart-canvas" />
      <!-- 饼图：正方形容器 -->
      <div v-else-if="chart.chart_type === 'pie'" class="xq-chart-pie-wrap">
        <div ref="chartEl" class="xq-chart-canvas xq-chart-pie-canvas" />
      </div>
    </template>

    <!-- 表格：直接渲染 columns + rows -->
    <div v-else class="xq-chart-table">
      <el-table :data="tableData" size="small" border stripe max-height="320" style="width: 100%">
        <el-table-column
          v-for="c in chart.columns || []"
          :key="c"
          :prop="c"
          :label="c"
          show-overflow-tooltip
          min-width="120"
        />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DatasetComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  DatasetComponent,
  CanvasRenderer
])

const props = defineProps({
  chart: { type: Object, default: null },
  size: { type: String, default: 'large' } // 'large' | 'small'
})

const chartEl = ref(null)
let instance = null
let resizeObs = null
let intersectionObs = null
let _renderRetries = 0
const _RETRY_DELAYS = [80, 160, 300, 500, 900, 1500, 2500] // ms，最多重试 7 次

const PIE_TOP_N = 10 // 饼图最多展示 top N

const chartTypeLabel = computed(() => ({
  bar: props.size === 'large' ? '柱状图' : '📊',
  line: props.size === 'large' ? '折线图' : '📈',
  pie: props.size === 'large' ? '饼图' : '🥧',
  table: props.size === 'large' ? '数据表格' : '📋'
}[props.chart?.chart_type] || ''))

const isGraphical = computed(() => ['bar', 'line', 'pie'].includes(props.chart?.chart_type))

const tableData = computed(() => {
  const cols = props.chart?.columns || []
  return (props.chart?.rows || []).map((r) => {
    const o = {}
    cols.forEach((c, i) => {
      const v = r[i]
      o[c] = v === null || v === undefined ? '' : v
    })
    return o
  })
})

// 柱状图横向滚动：每个类目最少 40px 宽（小图 32px）
const MIN_BAR_WIDTH = computed(() => props.size === 'large' ? 44 : 36)
const barCategoryCount = computed(() => {
  if (props.chart?.chart_type !== 'bar') return 0
  return (props.chart?.rows || []).length
})
const barMinTotalWidth = computed(() => Math.max(320, barCategoryCount.value * MIN_BAR_WIDTH.value))
const barWrapStyle = computed(() => ({
  overflowX: barCategoryCount.value > 12 ? 'auto' : 'hidden',
  overflowY: 'hidden'
}))
const barCanvasStyle = computed(() => {
  if (barCategoryCount.value <= 12) return { width: '100%' }
  return { width: `${barMinTotalWidth.value}px`, minWidth: '100%' }
})

function buildOption() {
  const c = props.chart
  if (!c) return null
  const cols = c.columns || []
  const rows = c.rows || []
  const dimIdx = cols.indexOf(c.dimension_field)
  const metricIdxs = (c.metric_fields || []).map((m) => cols.indexOf(m)).filter((i) => i >= 0)
  if (dimIdx < 0 || !metricIdxs.length) return null

  const isSmall = props.size === 'small'

  if (c.chart_type === 'pie') {
    const mIdx = metricIdxs[0]
    // 按值排序，取 top N，其余合并为 Other
    let items = rows.map((r, i) => ({
      name: formatDim(r[dimIdx]),
      value: toNumber(r[mIdx])
    })).sort((a, b) => b.value - a.value)

    if (items.length > PIE_TOP_N) {
      const top = items.slice(0, PIE_TOP_N)
      const otherVal = items.slice(PIE_TOP_N).reduce((s, it) => s + it.value, 0)
      if (otherVal > 0) top.push({ name: 'Other', value: otherVal })
      items = top
    }

    const radius = isSmall ? ['30%', '58%'] : ['35%', '62%']
    const center = isSmall ? ['50%', '44%'] : ['50%', '44%']

    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: {
        bottom: 0,
        type: 'scroll',
        itemWidth: isSmall ? 10 : 14,
        itemHeight: isSmall ? 10 : 14,
        textStyle: { fontSize: isSmall ? 10 : 12 }
      },
      series: [
        {
          type: 'pie',
          radius,
          center,
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 1 },
          label: {
            show: !isSmall,
            formatter: '{b}\n{d}%',
            fontSize: 11
          },
          labelLine: { show: !isSmall },
          data: items
        }
      ],
      color: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#f97316', '#06b6d4', '#84cc16', '#ec4899', '#6b7280']
    }
  }

  const series = metricIdxs.map((mi) => ({
    name: cols[mi],
    type: c.chart_type,
    smooth: c.chart_type === 'line',
    emphasis: { focus: 'series' },
    data: rows.map((r) => toNumber(r[mi])),
    barMaxWidth: isSmall ? 28 : 48,
    ...(c.chart_type === 'bar' ? { barGap: '20%' } : {})
  }))

  const categories = rows.map((r) => formatDim(r[dimIdx]))
  const labelRotate = categories.length > 8 ? 35 : 0

  return {
    tooltip: { trigger: 'axis' },
    legend: {
      show: metricIdxs.length > 1,
      bottom: 0,
      type: 'scroll',
      textStyle: { fontSize: isSmall ? 10 : 12 }
    },
    grid: {
      left: isSmall ? 36 : 48,
      right: 12,
      top: 12,
      bottom: metricIdxs.length > 1 ? (isSmall ? 32 : 40) : (isSmall ? 20 : 28),
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: categories,
      axisLabel: {
        interval: 0,
        rotate: labelRotate,
        formatter: (v) => shorten(v, isSmall ? 8 : 12),
        fontSize: isSmall ? 10 : 12
      }
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#eee' } },
      axisLabel: { fontSize: isSmall ? 10 : 12 }
    },
    series,
    color: ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6']
  }
}

function toNumber(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
function formatDim(v) {
  if (v === null || v === undefined) return '空'
  return String(v)
}
function shorten(s, n) {
  s = String(s)
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

async function render() {
  if (!isGraphical.value) {
    disposeInstance()
    return
  }
  await nextTick()
  if (!chartEl.value) return
  // 确保容器有尺寸再初始化；尺寸为 0 时按递增间隔重试（最多 7 次，覆盖刷新/重入场景）
  const rect = chartEl.value.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) {
    const delay = _RETRY_DELAYS[_renderRetries]
    if (delay !== undefined) {
      _renderRetries++
      setTimeout(render, delay)
    }
    return
  }
  _renderRetries = 0 // 渲染成功后重置计数
  if (!instance) {
    instance = echarts.init(chartEl.value)
  }
  const opt = buildOption()
  if (!opt) {
    instance.clear()
    return
  }
  instance.setOption(opt, true)
  instance.resize()
}

function disposeInstance() {
  if (instance) {
    instance.dispose()
    instance = null
  }
}

function setupObservers() {
  if (!chartEl.value) return
  // ResizeObserver: 容器大小变化时重绘
  if (window.ResizeObserver) {
    resizeObs = new ResizeObserver(() => {
      if (instance) instance.resize()
      else render()
    })
    resizeObs.observe(chartEl.value)
  } else {
    window.addEventListener('resize', onWinResize)
  }
  // IntersectionObserver: 元素从不可见变为可见时重新渲染（解决历史消息重入问题）
  if (window.IntersectionObserver) {
    intersectionObs = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          render()
        }
      },
      { threshold: 0 }
    )
    intersectionObs.observe(chartEl.value)
  }
}

onMounted(() => {
  render()
  setupObservers()
})

onBeforeUnmount(() => {
  if (resizeObs) resizeObs.disconnect()
  if (intersectionObs) intersectionObs.disconnect()
  window.removeEventListener('resize', onWinResize)
  disposeInstance()
})

function onWinResize() {
  if (instance) instance.resize()
}

watch(
  () => props.chart,
  () => {
    _renderRetries = 0
    render()
  },
  { deep: true }
)
</script>

<style scoped>
.xq-chart {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 12px 14px 14px;
  margin-bottom: 12px;
}
.xq-chart-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.xq-chart-tag {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  color: #fff;
  font-weight: 500;
}
.tag-bar { background: linear-gradient(135deg, #3b82f6, #1d4ed8); }
.tag-line { background: linear-gradient(135deg, #10b981, #059669); }
.tag-pie { background: linear-gradient(135deg, #f59e0b, #d97706); }
.tag-table { background: linear-gradient(135deg, #8b5cf6, #6d28d9); }

.xq-chart-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #111827;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.xq-chart-explain {
  font-size: 12.5px;
  color: #64748b;
  margin-bottom: 8px;
  line-height: 1.55;
}

/* 柱状图横向滚动容器 */
.xq-chart-bar-wrap {
  width: 100%;
  position: relative;
}
.xq-chart-canvas {
  width: 100%;
  height: 320px;
}

/* 饼图：正方形 */
.xq-chart-pie-wrap {
  width: 100%;
  aspect-ratio: 1 / 1;
  max-height: 360px;
}
.xq-chart-pie-canvas {
  width: 100%;
  height: 100%;
}

.xq-chart-table {
  margin-top: 6px;
}

/* ========== 小卡片样式 ========== */
.xq-chart--small {
  padding: 10px 10px 10px;
  margin-bottom: 0;
  border-radius: 10px;
  background: #fafbff;
  border-color: #eef1f7;
}
.xq-chart--small .xq-chart-tag {
  font-size: 14px;
  padding: 0;
  background: transparent !important;
  color: inherit;
}
.xq-chart--small .xq-chart-title {
  font-size: 12px;
}
.xq-chart--small .xq-chart-explain {
  font-size: 11px;
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
/* 小柱状图：扁矩形（宽:高 ≈ 2:1） */
.xq-chart--small .xq-chart-canvas {
  height: 160px;
}
/* 小饼图：正方形 */
.xq-chart--small .xq-chart-pie-wrap {
  max-height: 200px;
}
.xq-chart--small :deep(.el-table) {
  font-size: 11.5px;
}
.xq-chart--small :deep(.el-table__inner-wrapper) {
  max-height: 160px;
  overflow: auto;
}
</style>
