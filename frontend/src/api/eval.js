import request from '@/utils/request'

const BASE_URL = '/spaces'

/**
 * 获取评测文件夹树
 */
export function getEvalFolders(spaceId) {
  return request.get(`${BASE_URL}/${spaceId}/eval/folders`)
}

/**
 * 创建评测文件夹
 */
export function createEvalFolder(spaceId, data) {
  return request.post(`${BASE_URL}/${spaceId}/eval/folders`, data)
}

/**
 * 更新评测文件夹
 */
export function updateEvalFolder(spaceId, folderId, data) {
  return request.put(`${BASE_URL}/${spaceId}/eval/folders/${folderId}`, data)
}

/**
 * 删除评测文件夹
 */
export function deleteEvalFolder(spaceId, folderId) {
  return request.delete(`${BASE_URL}/${spaceId}/eval/folders/${folderId}`)
}

/**
 * 移动评测文件夹
 */
export function moveEvalFolder(folderId, spaceId, data) {
  return request.post(`${BASE_URL}/${spaceId}/eval/folders/${folderId}/move`, data)
}

/**
 * 获取评测集列表
 */
export function getEvalSuites(spaceId, params = {}) {
  return request.get(`${BASE_URL}/${spaceId}/eval/suites`, { params })
}

/**
 * 获取评测集详情
 */
export function getEvalSuite(spaceId, suiteId) {
  return request.get(`${BASE_URL}/${spaceId}/eval/suites/${suiteId}`)
}

/**
 * 创建评测集
 */
export function createEvalSuite(spaceId, data) {
  return request.post(`${BASE_URL}/${spaceId}/eval/suites`, data)
}

/**
 * 更新评测集
 */
export function updateEvalSuite(spaceId, suiteId, data) {
  return request.put(`${BASE_URL}/${spaceId}/eval/suites/${suiteId}`, data)
}

/**
 * 删除评测集
 */
export function deleteEvalSuite(spaceId, suiteId) {
  return request.delete(`${BASE_URL}/${spaceId}/eval/suites/${suiteId}`)
}

/**
 * 复制评测集
 */
export function copyEvalSuite(spaceId, suiteId) {
  return request.post(`${BASE_URL}/${spaceId}/eval/suites/${suiteId}/copy`)
}

/**
 * 导出评测集
 */
export function exportEvalSuite(spaceId, suiteId) {
  return request.get(`${BASE_URL}/${spaceId}/eval/suites/${suiteId}/export`)
}

// ========== 标签 ==========
/**
 * 获取标签列表
 */
export function getEvalTags(spaceId) {
  return request.get(`${BASE_URL}/${spaceId}/eval/tags`)
}

/**
 * 创建标签
 */
export function createEvalTag(spaceId, data) {
  return request.post(`${BASE_URL}/${spaceId}/eval/tags`, data)
}

/**
 * 更新标签
 */
export function updateEvalTag(spaceId, tagId, data) {
  return request.put(`${BASE_URL}/${spaceId}/eval/tags/${tagId}`, data)
}

/**
 * 删除标签
 */
export function deleteEvalTag(spaceId, tagId) {
  return request.delete(`${BASE_URL}/${spaceId}/eval/tags/${tagId}`)
}

// ========== 任务统计 ==========

/**
 * 获取任务统计概览（按状态分组）
 */
export function getEvalTaskStats(spaceId, params = {}) {
  return request.get(`/eval/tasks/stats`, { params: { space_id: spaceId, ...params } })
}

// ========== 任务 ==========
/**
 * 获取任务列表
 */
export function getEvalTasks(spaceId, params = {}) {
  return request.get(`/spaces/${spaceId}/eval/tasks`, { params })
}

/**
 * 获取任务详情
 */
export function getEvalTask(taskId, spaceId) {
  return request.get(`/eval/tasks/${taskId}`, { params: { space_id: spaceId } })
}

/**
 * 创建任务
 */
export function createEvalTask(spaceId, data) {
  return request.post(`/spaces/${spaceId}/eval/tasks`, data)
}

/**
 * 更新任务
 */
export function updateEvalTask(taskId, spaceId, data) {
  return request.put(`/eval/tasks/${taskId}`, data, { params: { space_id: spaceId } })
}

/**
 * 启动任务
 */
export function startEvalTask(taskId, spaceId) {
  return request.post(`/eval/tasks/${taskId}/start`, null, { params: { space_id: spaceId } })
}

/**
 * 暂停任务
 */
export function pauseEvalTask(taskId, spaceId) {
  return request.post(`/eval/tasks/${taskId}/pause`, null, { params: { space_id: spaceId } })
}

/**
 * 恢复任务
 */
export function resumeEvalTask(taskId, spaceId) {
  return request.post(`/eval/tasks/${taskId}/resume`, null, { params: { space_id: spaceId } })
}

/**
 * 取消任务
 */
export function cancelEvalTask(taskId, spaceId) {
  return request.post(`/eval/tasks/${taskId}/cancel`, null, { params: { space_id: spaceId } })
}

/**
 * 重试失败项
 */
export function retryFailedEvalTask(taskId, spaceId) {
  return request.post(`/eval/tasks/${taskId}/retry-failed`, null, { params: { space_id: spaceId } })
}

/**
 * 删除任务
 */
export function deleteEvalTask(taskId, spaceId) {
  return request.delete(`/eval/tasks/${taskId}`, { params: { space_id: spaceId } })
}

/**
 * 获取任务概览
 */
export function getEvalTaskSummary(taskId, spaceId) {
  return request.get(`/eval/tasks/${taskId}/summary`, { params: { space_id: spaceId } })
}

/**
 * 获取任务子任务列表
 */
export function getEvalTaskSubTasks(taskId, spaceId) {
  return request.get(`/eval/tasks/${taskId}/sub-tasks`, { params: { space_id: spaceId } })
}

/**
 * 导出任务结果
 */
export function exportEvalTaskResults(taskId, spaceId) {
  return request.get(`/eval/tasks/${taskId}/export`, { params: { space_id: spaceId } })
}

/**
 * 失败归档
 */
export function archiveFailedEvalTask(taskId, spaceId) {
  return request.post(`/eval/tasks/${taskId}/archive-failed`, null, { params: { space_id: spaceId } })
}

/**
 * 生成任务报告
 */
export function generateEvalTaskReport(taskId, spaceId) {
  return request.get(`/eval/tasks/${taskId}/report`, { params: { space_id: spaceId } })
}

// ========== 用例 ==========
/**
 * 获取用例列表
 */
export function getEvalCases(suiteId, params = {}) {
  return request.get(`/eval/suites/${suiteId}/cases`, { params })
}

/**
 * 创建用例
 */
export function createEvalCase(suiteId, data) {
  return request.post(`/eval/suites/${suiteId}/cases`, data)
}

/**
 * 批量创建用例
 */
export function batchCreateEvalCases(suiteId, data) {
  return request.post(`/eval/suites/${suiteId}/cases/batch`, data)
}

/**
 * 更新用例
 */
export function updateEvalCase(caseId, suiteId, data) {
  return request.put(`/eval/cases/${caseId}`, data, { params: { suite_id: suiteId } })
}

/**
 * 删除用例
 */
export function deleteEvalCase(caseId, suiteId) {
  return request.delete(`/eval/cases/${caseId}`, { params: { suite_id: suiteId } })
}

/**
 * 批量更新用例
 */
export function batchUpdateEvalCases(suiteId, caseIds, data) {
  return request.post(`/eval/suites/${suiteId}/cases/batch-update`, { case_ids: caseIds, ...data })
}

/**
 * 批量删除用例
 */
export function batchDeleteEvalCases(suiteId, caseIds) {
  return request.post(`/eval/suites/${suiteId}/cases/batch-delete`, { case_ids: caseIds })
}

/**
 * 导出用例
 */
export function exportEvalCases(suiteId) {
  return request.get(`/eval/suites/${suiteId}/cases/export`)
}

/**
 * 下载导入模板
 */
export function getImportTemplate() {
  return request.get('/eval/suites/import-template')
}

/**
 * 导入预览
 */
export function previewImport(suiteId, data) {
  return request.post(`/eval/suites/${suiteId}/cases/import/preview`, data)
}

/**
 * 执行导入
 */
export function executeImport(suiteId, data) {
  return request.post(`/eval/suites/${suiteId}/cases/import`, data)
}

/**
 * LLM 生成用例
 */
export function generateEvalCases(suiteId, data) {
  return request.post(`/eval/suites/${suiteId}/cases/generate`, data)
}

// ========== 参考答案 ==========
/**
 * 获取参考答案列表
 */
export function getGroundTruths(caseId) {
  return request.get(`/eval/cases/${caseId}/ground-truths`)
}

/**
 * 创建参考答案
 */
export function createGroundTruth(caseId, data) {
  return request.post(`/eval/cases/${caseId}/ground-truths`, data)
}

/**
 * 更新参考答案
 */
export function updateGroundTruth(gtId, data) {
  return request.put(`/eval/ground-truths/${gtId}`, data)
}

/**
 * 删除参考答案
 */
export function deleteGroundTruth(gtId) {
  return request.delete(`/eval/ground-truths/${gtId}`)
}

// ========== 输出模板 ==========
/**
 * 获取输出模板列表
 */
export function getOutputTemplates(suiteId) {
  return request.get(`/eval/suites/${suiteId}/templates`)
}

/**
 * 创建输出模板
 */
export function createOutputTemplate(suiteId, data) {
  return request.post(`/eval/suites/${suiteId}/templates`, data)
}

/**
 * 更新输出模板
 */
export function updateOutputTemplate(templateId, data) {
  return request.put(`/eval/templates/${templateId}`, data)
}

/**
 * 删除输出模板
 */
export function deleteOutputTemplate(templateId) {
  return request.delete(`/eval/templates/${templateId}`)
}

/**
 * 设为默认模板
 */
export function setDefaultTemplate(templateId, suiteId) {
  return request.put(`/eval/templates/${templateId}/set-default`, null, { params: { suite_id: suiteId } })
}

// ========== 运行记录 ==========
/**
 * 获取子任务运行记录
 */
export function getSubTaskRuns(subTaskId, params = {}) {
  return request.get(`/eval/sub-tasks/${subTaskId}/runs`, { params })
}

/**
 * 获取运行记录详情
 */
export function getRunDetail(runId) {
  return request.get(`/eval/runs/${runId}`)
}

/**
 * 人工标注
 */
export function manualCorrectRun(runId, data) {
  return request.put(`/eval/runs/${runId}/manual`, data)
}

/**
 * 批量重新对比
 * @param {number[]} runIds - 运行记录 ID 数组
 */
export function batchRecompare(runIds) {
  return request.post('/eval/runs/batch-recompare', runIds)
}

/**
 * 获取对比详情
 */
export function getComparison(runId) {
  return request.get(`/eval/comparisons/${runId}`)
}

// ========== 统计 ==========
// ========== 分享 ==========
/**
 * 生成/复用分享 token
 */
export function issueEvalShare(spaceId, suiteId, rotate = false) {
  return request.post(`/spaces/${spaceId}/eval/suites/${suiteId}/share`, { rotate })
}

/**
 * 撤销分享 token
 */
export function revokeEvalShare(spaceId, suiteId) {
  return request.delete(`/spaces/${spaceId}/eval/suites/${suiteId}/share`)
}

// ===================== 对比模板 =====================

export function getComparisonTemplates(spaceId, params = {}) {
  return request.get(`/spaces/${spaceId}/eval/comparison-templates`, { params })
}

export function createComparisonTemplate(spaceId, data) {
  return request.post(`/spaces/${spaceId}/eval/comparison-templates`, data)
}

export function getComparisonTemplate(spaceId, templateId) {
  return request.get(`/spaces/${spaceId}/eval/comparison-templates/${templateId}`)
}

export function updateComparisonTemplate(spaceId, templateId, data) {
  return request.put(`/spaces/${spaceId}/eval/comparison-templates/${templateId}`, data)
}

export function deleteComparisonTemplate(spaceId, templateId) {
  return request.delete(`/spaces/${spaceId}/eval/comparison-templates/${templateId}`)
}

export function cloneComparisonTemplate(spaceId, templateId) {
  return request.post(`/spaces/${spaceId}/eval/comparison-templates/${templateId}/clone`)
}
