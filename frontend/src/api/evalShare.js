import request from '../utils/request'

/**
 * 拼出评测分享页完整 URL（独立端口 evalShare.html + hash 路由，与主站隔离）。
 * 优先级：VITE_EVAL_SHARE_ORIGIN → 后端 share_public_base_url → 当前 hostname + VITE_EVAL_SHARE_PORT（默认 3840）
 */
export function buildEvalShareUrl(token, serverSuggestedBase) {
  const raw = import.meta.env.VITE_EVAL_SHARE_ORIGIN?.trim()
  if (raw) {
    return `${raw.replace(/\/$/, '')}/evalShare.html#/${encodeURIComponent(token)}`
  }
  const sug = (serverSuggestedBase || '').trim()
  if (sug) {
    const origin = sug.replace(/\/$/, '').replace(/#.*$/, '')
    if (origin) return `${origin}/evalShare.html#/${encodeURIComponent(token)}`
  }
  if (typeof window !== 'undefined') {
    const sharePort = import.meta.env.VITE_EVAL_SHARE_PORT?.trim() || '3840'
    const { protocol, hostname } = window.location
    return `${protocol}//${hostname}:${sharePort}/evalShare.html#/${encodeURIComponent(token)}`
  }
  return `/evalShare.html#/${encodeURIComponent(token)}`
}

/**
 * 免登录分享接口：路径前缀 /api/eval/share/{token}/...
 */
export function createEvalShareApi(token) {
  const enc = encodeURIComponent(token)
  const root = `/eval/share/${enc}`
  return {
    getSuite() {
      return request({ url: `${root}/suite`, method: 'get' })
    },
    listCases(params = {}) {
      return request({ url: `${root}/cases`, method: 'get', params })
    },
    listTasks(params = {}) {
      return request({ url: `${root}/tasks`, method: 'get', params })
    },
    getTask(taskId) {
      return request({ url: `${root}/tasks/${taskId}`, method: 'get' })
    },
    getTaskSubTasks(taskId) {
      return request({ url: `${root}/tasks/${taskId}/sub-tasks`, method: 'get' })
    },
    getTaskSummary(taskId) {
      return request({ url: `${root}/tasks/${taskId}/summary`, method: 'get' })
    },
    getTaskStatistics(taskId) {
      return request({ url: `${root}/tasks/${taskId}/statistics`, method: 'get' })
    },
    getTaskReport(taskId) {
      return request({ url: `${root}/tasks/${taskId}/report`, method: 'get' })
    },
    listRuns(subTaskId, params = {}) {
      return request({ url: `${root}/sub-tasks/${subTaskId}/runs`, method: 'get', params })
    },
    getRun(runId) {
      return request({ url: `${root}/runs/${runId}`, method: 'get' })
    },
    getComparison(runId) {
      return request({ url: `${root}/comparisons/${runId}`, method: 'get' })
    },
    updateCase(caseId, data) {
      return request({ url: `${root}/cases/${caseId}`, method: 'put', data })
    },
    deleteCase(caseId) {
      return request({ url: `${root}/cases/${caseId}`, method: 'delete' })
    },
    createCase(data) {
      return request({ url: `${root}/cases`, method: 'post', data })
    },
  }
}
