import request from '@/utils/request'

/**
 * 获取审计日志列表
 */
export function getAuditLogs(params = {}) {
  return request.get('/audit-logs', { params })
}

/**
 * 获取审计日志详情
 */
export function getAuditLog(logId) {
  return request.get(`/audit-logs/${logId}`)
}
