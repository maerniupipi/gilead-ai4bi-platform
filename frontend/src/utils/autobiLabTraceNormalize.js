/**
 * Redis GET /api/autobi/lab/traces/:id 返回体 → 实验室调试卡片 / 中间区展示
 */

/** @param {object|null} trace */
export function normalizeTraceStepsToRows(trace) {
  const steps = trace?.steps
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
}

/**
 * 从完整 trace 提取对话区展示：SQL、执行结果、图表、总结
 * @param {object|null} trace
 */
export function extractTurnDisplayFromTrace(trace) {
  const steps = trace?.steps
  if (!Array.isArray(steps)) {
    return {
      rewrittenQuery: '',
      generatedSql: '',
      sqlData: null,
      chartSpec: null,
      biSummary: ''
    }
  }
  const byId = Object.fromEntries(steps.map(s => [s.step_id, s]))
  const s4 = byId[4]?.response
  const s14 = byId[14]?.response
  const s15 = byId[15]?.response
  const s16 = byId[16]?.response
  const s17 = byId[17]?.response
  const s18 = byId[18]?.response
  const rw =
    (s4 && (s4.rewritten_query != null ? String(s4.rewritten_query).trim() : '')) || ''
  return {
    rewrittenQuery: rw,
    generatedSql: (s15 && s15.sql) || (s14 && s14.sql) || '',
    sqlData: s16 && typeof s16 === 'object' ? s16 : null,
    chartSpec: (s18 && s18.chart_spec) != null ? s18.chart_spec : null,
    biSummary: (s17 && s17.content) || ''
  }
}

/** 是否所有步骤都已结束（无 running / pending） */
export function tracePipelineFinished(trace) {
  const steps = trace?.steps
  if (!Array.isArray(steps) || steps.length === 0) return false
  return steps.every(s => s.status === 'done' || s.status === 'error')
}
