import request from '../utils/request'
import axios from 'axios'

/**
 * 拼出分享页完整 URL（独立端口 share.html + hash 路由，与主站隔离）。
 * 优先级：VITE_XLSX_QA_SHARE_ORIGIN → 后端 share_public_base_url → 当前 hostname + VITE_XLSX_QA_SHARE_PORT（默认 3840）
 */
export function buildXlsxQaShareUrl(token, serverSuggestedBase) {
  const raw = import.meta.env.VITE_XLSX_QA_SHARE_ORIGIN?.trim()
  if (raw) {
    return `${raw.replace(/\/$/, '')}/share.html#/${encodeURIComponent(token)}`
  }
  const sug = (serverSuggestedBase || '').trim()
  if (sug) {
    const origin = sug.replace(/\/$/, '').replace(/#.*$/, '')
    if (origin) return `${origin}/share.html#/${encodeURIComponent(token)}`
  }
  if (typeof window !== 'undefined') {
    const sharePort = import.meta.env.VITE_XLSX_QA_SHARE_PORT?.trim() || '3840'
    const { protocol, hostname } = window.location
    return `${protocol}//${hostname}:${sharePort}/share.html#/${encodeURIComponent(token)}`
  }
  return `/share.html#/${encodeURIComponent(token)}`
}

/**
 * 免登录分享接口：路径前缀 /api/xlsx-qa/share/{token}/...
 */
export function createXlsxQaShareApi(token) {
  const enc = encodeURIComponent(token)
  const root = `/xlsx-qa/share/${enc}`
  return {
    getModule() {
      return request({ url: `${root}/module`, method: 'get' })
    },
    listConversations() {
      return request({ url: `${root}/conversations`, method: 'get' })
    },
    createConversation(data = {}) {
      return request({ url: `${root}/conversations`, method: 'post', data })
    },
    deleteConversation(convId) {
      return request({ url: `${root}/conversations/${convId}`, method: 'delete' })
    },
    listMessages(convId) {
      return request({ url: `${root}/conversations/${convId}/messages`, method: 'get' })
    },
    uploadDocument(file, { onProgress } = {}) {
      const form = new FormData()
      form.append('file', file)
      return request({
        url: `${root}/documents`,
        method: 'post',
        data: form,
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 5 * 60 * 1000,
        onUploadProgress: (e) => {
          if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
        },
      })
    },
    getDocumentDownloadUrl(docId) {
      return request({ url: `${root}/documents/${docId}/download`, method: 'get' })
    },
    previewDocument(docId, limit = 20) {
      return request({ url: `${root}/documents/${docId}/preview`, method: 'get', params: { limit } })
    },
    previewSheet(docId, sheetId, limit = 20) {
      return request({ url: `${root}/documents/${docId}/sheets/${sheetId}/preview`, method: 'get', params: { limit } })
    },
    exportConversationPpt(convId, data = {}) {
      return request({ url: `${root}/conversations/${convId}/export-ppt`, method: 'post', data })
    },
    exportConversationPdf(convId, data = {}) {
      return request({
        url: `${root}/conversations/${convId}/export-pdf`,
        method: 'post',
        data,
        responseType: 'blob',
        timeout: 120 * 1000,
      })
    },
    exportInsightPdf() {
      return request({
        url: `${root}/insight/export-pdf`,
        method: 'post',
        responseType: 'blob',
        timeout: 120 * 1000,
      })
    },
    exportInsightPpt() {
      return request({
        url: `${root}/insight/export-ppt`,
        method: 'post',
        timeout: 30 * 1000,
      })
    },
    listPptHistory() {
      return request({ url: `${root}/ppt-history`, method: 'get' })
    },
    getPptHistoryDownloadUrl(historyId) {
      return request({ url: `${root}/ppt-history/${historyId}/download`, method: 'get' })
    },
    deletePptHistory(historyId) {
      return request({ url: `${root}/ppt-history/${historyId}`, method: 'delete' })
    },
  }
}
