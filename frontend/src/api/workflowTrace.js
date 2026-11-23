import request from '../utils/request'

/**
 * 统一查询 trace（先查工作流表，再查实验室表）
 * @param {string} traceId
 */
export function getTrace(traceId) {
  return request({
    url: `/agent_apps/traces/${encodeURIComponent(traceId)}`,
    method: 'get'
  })
}

/**
 * 列表/搜索工作流运行日志
 * @param {object} params - { keyword, app_name, status, date_from, date_to, skip, limit }
 */
export function listTraces(params = {}) {
  return request({
    url: '/agent_apps/traces',
    method: 'get',
    params
  })
}

/**
 * 按应用筛选的工作流运行日志
 * @param {number} appId
 * @param {object} params - { status, skip, limit }
 */
export function listAppTraces(appId, params = {}) {
  return request({
    url: `/agent_apps/${appId}/traces`,
    method: 'get',
    params
  })
}
