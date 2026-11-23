import request from '@/utils/request'
export const listSystemLogs = params => request({ url: '/system-logs', method: 'get', params })
