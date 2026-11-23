import request from '@/utils/request'

const base = '/chatbi/data-sync'
export const listSyncTasks = () => request({ url: `${base}/tasks`, method: 'get' })
export const updateSyncTask = (id, data) => request({ url: `${base}/tasks/${id}`, method: 'put', data })
export const startSyncTask = id => request({ url: `${base}/tasks/${id}/run`, method: 'post' })
export const listSyncRuns = params => request({ url: `${base}/runs`, method: 'get', params })
export const getSyncRun = (id, params) => request({ url: `${base}/runs/${id}`, method: 'get', params })
