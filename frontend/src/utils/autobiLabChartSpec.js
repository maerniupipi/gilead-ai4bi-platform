/**
 * 实验室第 18 步：解析模型返回的图表 JSON，并生成 ECharts option（纯对象，不含 echarts 引用）。
 */
import { formatChartValue } from './formatChartValue.js'

function toNumber(v) {
  if (v == null || v === '') return NaN
  if (typeof v === 'number' && !Number.isNaN(v)) return v
  const n = Number(String(v).replace(/,/g, ''))
  return Number.isFinite(n) ? n : NaN
}

/**
 * 从 LLM 文本中提取并解析图表 JSON
 * @param {string} text
 * @returns {object|null}
 */
export function parseChartSpecFromLlm(text) {
  if (!text || !String(text).trim()) return null
  const s = String(text).trim()
  let jsonStr = null
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fence) jsonStr = fence[1].trim()
  else {
    const start = s.indexOf('{')
    const end = s.lastIndexOf('}')
    if (start >= 0 && end > start) jsonStr = s.slice(start, end + 1)
  }
  if (!jsonStr) return null
  try {
    const o = JSON.parse(jsonStr)
    return normalizeChartSpec(o)
  } catch {
    return null
  }
}

function normalizeChartSpec(o) {
  if (!o || typeof o !== 'object') return null
  let xaxis = o.xaxis
  if (typeof xaxis === 'string') xaxis = xaxis ? [xaxis] : []
  if (!Array.isArray(xaxis)) xaxis = []
  let yaxis = o.yaxis
  if (typeof yaxis === 'string') yaxis = yaxis ? [yaxis] : []
  if (!Array.isArray(yaxis)) yaxis = []
  const rawType = (o.type || o.primary || 'D').toString().toUpperCase()
  const letter = rawType.match(/[ABCD]/)
  const type = letter ? letter[0] : 'D'
  return {
    type,
    xaxis,
    yaxis,
    title: o.title != null ? String(o.title) : '',
    error: o.error != null ? String(o.error) : null,
    detail: o.detail != null ? String(o.detail) : null
  }
}

export function resolveSqlColumnKeys(requestedKeys, columns) {
  const cols = columns || []
  const lowerMap = new Map(cols.map(c => [String(c).toLowerCase(), c]))
  return (requestedKeys || [])
    .map(k => {
      if (k == null || k === '') return null
      const ks = String(k)
      if (cols.includes(ks)) return ks
      return lowerMap.get(ks.toLowerCase()) || null
    })
    .filter(Boolean)
}

export function buildChartDataset(spec, sqlData) {
  const columns = sqlData?.columns || []
  const rows = sqlData?.rows || []
  let xkeys = resolveSqlColumnKeys(spec?.xaxis, columns)
  let ykeys = resolveSqlColumnKeys(spec?.yaxis, columns)

  if (!xkeys.length && columns.length) xkeys = [columns[0]]
  if (!ykeys.length && columns.length > 1) {
    const numericCols = columns.filter(c => rows.some(r => Number.isFinite(toNumber(r[c]))))
    ykeys = numericCols.length ? numericCols : [columns[1]]
  }

  const categories = rows.map(row =>
    xkeys.map(k => (row[k] != null ? String(row[k]) : '')).join(' / ') || '(空)'
  )

  const seriesForMetrics = ykeys.map(y => ({
    name: y,
    data: rows.map(r => {
      const v = toNumber(r[y])
      return Number.isFinite(v) ? v : 0
    })
  }))

  return { xkeys, ykeys, categories, seriesForMetrics, rows, columns }
}

export function buildBarLineOptions(spec, sqlData, chartType) {
  const ds = buildChartDataset(spec, sqlData)
  const t = chartType === 'line' ? 'line' : 'bar'
  const hasTitle = spec?.title && String(spec.title).trim()
  return {
    title: hasTitle ? { text: spec.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
    tooltip: { trigger: 'axis', valueFormatter: formatChartValue },
    legend: { bottom: 0 },
    grid: { left: 56, right: 24, top: hasTitle ? 40 : 28, bottom: 52 },
    xAxis: {
      type: 'category',
      data: ds.categories,
      axisLabel: { rotate: ds.categories.some(c => c.length > 10) ? 28 : 0 }
    },
    yAxis: { type: 'value', axisLabel: { formatter: formatChartValue } },
    series: ds.seriesForMetrics.map(s => ({
      ...s,
      type: t,
      label: { formatter: params => formatChartValue(params.value) },
      emphasis: { focus: 'series' }
    }))
  }
}

export function buildPieOptions(spec, sqlData) {
  const ds = buildChartDataset(spec, sqlData)
  const y = ds.ykeys[0] || ds.columns[1] || ds.columns[0]
  const xk = ds.xkeys[0]
  const data = ds.rows.map((row, i) => ({
    name: String(xk != null ? row[xk] ?? ds.categories[i] : ds.categories[i]),
    value: Number.isFinite(toNumber(row[y])) ? toNumber(row[y]) : 0
  }))
  const hasTitle = spec?.title && String(spec.title).trim()
  return {
    title: hasTitle ? { text: spec.title, left: 'center', textStyle: { fontSize: 14 } } : undefined,
    tooltip: { trigger: 'item', valueFormatter: formatChartValue },
    legend: { bottom: 0, type: 'scroll' },
    series: [
      {
        type: 'pie',
        radius: '56%',
        center: ['50%', '46%'],
        data,
        emphasis: { itemStyle: { shadowBlur: 10 } },
        label: { formatter: params => `${params.name}: ${formatChartValue(params.percent)}%` }
      }
    ]
  }
}

/** 模型建议的图表类型 → 默认选中的 tab */
export function chartTypeToTabKey(type) {
  const m = { A: 'bar', B: 'line', C: 'pie', D: 'table' }
  return m[type] || 'bar'
}
