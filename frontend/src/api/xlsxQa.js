import request from '../utils/request'

/**
 * XLSX 表格智能问答工具 · 前端 API 客户端
 *
 * 对话接口 (ask) 使用 SSE 流式；不走 axios，参见 utils/xlsxQaSse.js。
 */

const base = '/xlsx-qa'

// ---------- 模块 ----------

export function listXlsxQaModules(params) {
  return request({ url: `${base}/modules`, method: 'get', params })
}

export function getXlsxQaModule(moduleId) {
  return request({ url: `${base}/modules/${moduleId}`, method: 'get' })
}

export function createXlsxQaModule(data) {
  return request({ url: `${base}/modules`, method: 'post', data })
}

export function updateXlsxQaModule(moduleId, data) {
  return request({ url: `${base}/modules/${moduleId}`, method: 'put', data })
}

export function deleteXlsxQaModule(moduleId) {
  return request({ url: `${base}/modules/${moduleId}`, method: 'delete' })
}

/** 生成或复用外链分享 token（opaque，勿当密码传播） */
export function issueXlsxQaShare(moduleId, data = { rotate: false }) {
  return request({ url: `${base}/modules/${moduleId}/share`, method: 'post', data })
}

export function revokeXlsxQaShare(moduleId) {
  return request({ url: `${base}/modules/${moduleId}/share`, method: 'delete' })
}

// ---------- 文档 ----------

export function uploadXlsxQaDocument(moduleId, file, { onProgress, sheetIndices } = {}) {
  const form = new FormData()
  form.append('file', file)
  const params = {}
  if (sheetIndices?.length) params.sheet_indices = sheetIndices.join(',')
  return request({
    url: `${base}/modules/${moduleId}/documents`,
    method: 'post',
    params,
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 5 * 60 * 1000,
    onUploadProgress: (e) => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
}

export function deleteXlsxQaDocument(moduleId, docId) {
  return request({ url: `${base}/modules/${moduleId}/documents/${docId}`, method: 'delete' })
}

export function getXlsxQaDocumentDownloadUrl(moduleId, docId) {
  return request({
    url: `${base}/modules/${moduleId}/documents/${docId}/download`,
    method: 'get',
  })
}

export function previewXlsxQaDocument(moduleId, docId, limit = 20, sheetId = null) {
  return request({
    url: `${base}/modules/${moduleId}/documents/${docId}/preview`,
    method: 'get',
    params: { limit, ...(sheetId != null ? { sheet_id: sheetId } : {}) },
  })
}

export function previewXlsxQaSheet(moduleId, docId, sheetId, limit = 20) {
  return request({
    url: `${base}/modules/${moduleId}/documents/${docId}/sheets/${sheetId}/preview`,
    method: 'get',
    params: { limit },
  })
}

export function regenerateSheetUnderstanding(moduleId, docId, sheetId) {
  return request({
    url: `${base}/modules/${moduleId}/documents/${docId}/sheets/${sheetId}/regenerate`,
    method: 'post',
    timeout: 180000,
  })
}

export function updateSheetUnderstanding(moduleId, docId, sheetId, understandingMd) {
  return request({
    url: `${base}/modules/${moduleId}/documents/${docId}/sheets/${sheetId}/understanding`,
    method: 'patch',
    data: { understanding_md: understandingMd },
  })
}

export function regenerateModuleSummary(moduleId) {
  return request({
    url: `${base}/modules/${moduleId}/regenerate-summary`,
    method: 'post',
    timeout: 180000,
  })
}

export function updateConversationSheets(convId, activeSheetIds) {
  return request({
    url: `${base}/conversations/${convId}/sheets`,
    method: 'patch',
    data: { active_sheet_ids: activeSheetIds },
  })
}

export function regenerateXlsxQaUnderstanding(moduleId, docId) {
  return request({
    url: `${base}/modules/${moduleId}/documents/${docId}/regenerate-understanding`,
    method: 'post',
    timeout: 180000,
  })
}

// ---------- 会话 / 消息 ----------

export function listXlsxQaConversations(moduleId) {
  return request({ url: `${base}/modules/${moduleId}/conversations`, method: 'get' })
}

export function createXlsxQaConversation(moduleId, data = {}) {
  return request({ url: `${base}/modules/${moduleId}/conversations`, method: 'post', data })
}

export function deleteXlsxQaConversation(convId) {
  return request({ url: `${base}/conversations/${convId}`, method: 'delete' })
}

export function listXlsxQaMessages(convId) {
  return request({ url: `${base}/conversations/${convId}/messages`, method: 'get' })
}

// `ask` 是 SSE 流式；参见 utils/xlsxQaSse.js 里的 askXlsxQaStream()

// ---------- 高级设置：提示词 ----------

export function getXlsxQaModulePrompts(moduleId) {
  return request({ url: `${base}/modules/${moduleId}/prompts`, method: 'get' })
}

export function updateXlsxQaModulePrompts(moduleId, data) {
  return request({ url: `${base}/modules/${moduleId}/prompts`, method: 'put', data })
}

// ---------- 知识追加（采纳知识卡片） ----------

export function appendXlsxQaKnowledge(data) {
  return request({ url: `${base}/knowledge/append`, method: 'post', data })
}

// ---------- 会话导出 PPT ----------

export function listPptTemplates() {
  return request({ url: `${base}/ppt-templates`, method: 'get' })
}

/** 获取自定义模板封面预览图 URL */
export function getCustomPptCoverUrl() {
  return `${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api${base}/ppt-templates/custom-cover`
}

// ---------- PPT 异步导出 ----------

export function exportXlsxQaConversationPptAsync(convId, data = {}) {
  return request({
    url: `${base}/conversations/${convId}/export-ppt`,
    method: 'post',
    data,
    timeout: 30 * 1000,
  })
}

export function exportXlsxQaConversationPdf(convId, data = {}) {
  return request({
    url: `${base}/conversations/${convId}/export-pdf`,
    method: 'post',
    data,
    responseType: 'blob',
    timeout: 120 * 1000,
  })
}

export function exportXlsxQaInsightPdf(moduleId) {
  return request({
    url: `${base}/modules/${moduleId}/insight/export-pdf`,
    method: 'post',
    responseType: 'blob',
    timeout: 120 * 1000,
  })
}

export function exportXlsxQaInsightPptAsync(moduleId) {
  return request({
    url: `${base}/modules/${moduleId}/insight/export-ppt`,
    method: 'post',
    timeout: 30 * 1000,
  })
}

export function exportXlsxQaConversationCustomPptAsync(convId, data = {}, logoFile = null) {
  const form = new FormData()
  form.append('payload', JSON.stringify(data || {}))
  if (logoFile) form.append('logo', logoFile)
  return request({
    url: `${base}/conversations/${convId}/export-custom-ppt`,
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 30 * 1000,
  })
}

// ---------- PPT 导出历史 ----------

export function listPptHistory(moduleId) {
  return request({ url: `${base}/modules/${moduleId}/ppt-history`, method: 'get' })
}

export function getPptHistoryDownloadUrl(historyId) {
  return request({ url: `${base}/ppt-history/${historyId}/download`, method: 'get' })
}

export function deletePptHistory(historyId) {
  return request({ url: `${base}/ppt-history/${historyId}`, method: 'delete' })
}

// ---------- 模块 Logo ----------

export function uploadModuleLogo(moduleId, file) {
  const form = new FormData()
  form.append('file', file)
  return request({
    url: `${base}/modules/${moduleId}/logo`,
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getModuleLogo(moduleId) {
  return request({ url: `${base}/modules/${moduleId}/logo`, method: 'get' })
}

export function deleteModuleLogo(moduleId) {
  return request({ url: `${base}/modules/${moduleId}/logo`, method: 'delete' })
}
