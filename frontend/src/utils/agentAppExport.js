/** 工作流应用 JSON 导出/导入约定（与后端无强耦合，便于备份与迁移） */

import { DEFAULT_AGENT_APP_ICON } from '@/utils/agentAppIcon'

export const EXPORT_FORMAT = 'chat-bi-agent-export'
export const EXPORT_FORMAT_VERSION = 1

/**
 * @param {object} opts
 * @param {object} opts.app - AgentAppSummary | { name, icon, description }
 * @param {object} opts.versionMeta - 选中版本的元信息
 * @param {object} opts.workflowGetOut - getWorkflow 返回 { workflow, workflow_rev, undo_stack }
 */
export function buildExportPayload({ app, versionMeta, workflowGetOut }) {
  const wf = workflowGetOut?.workflow
  return {
    format: EXPORT_FORMAT,
    formatVersion: EXPORT_FORMAT_VERSION,
    exportedAt: new Date().toISOString(),
    app: {
      name: app.name,
      icon: app.icon || DEFAULT_AGENT_APP_ICON,
      description: app.description ?? null
    },
    versionMeta: {
      name: versionMeta.name,
      status: versionMeta.status,
      mode: versionMeta.mode
    },
    workflow: wf && typeof wf === 'object' ? wf : { nodes: [], edges: [] },
    undo_stack: workflowGetOut?.undo_stack ?? null,
    workflow_rev: workflowGetOut?.workflow_rev ?? 0
  }
}

export function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], {
    type: 'application/json;charset=utf-8'
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function safeFilenamePart(s) {
  return String(s || 'agent')
    .replace(/[/\\?%*:|"<>]/g, '_')
    .trim()
    .slice(0, 64) || 'agent'
}

const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value)

function importWorkflow(workflow, allowMissingEdges = false) {
  if (!isObject(workflow) || !Array.isArray(workflow.nodes)) {
    throw new Error('无效的工作流：nodes 必须是数组')
  }
  const edges = workflow.edges === undefined && allowMissingEdges ? [] : workflow.edges
  if (!Array.isArray(edges) || workflow.nodes.some(node => !isObject(node)) || edges.some(edge => !isObject(edge))) {
    throw new Error('无效的工作流：nodes、edges 必须是对象数组')
  }
  return { nodes: workflow.nodes, edges }
}

export function suggestImportVersionName(payload, versions = []) {
  const base = String(payload?.versionMeta?.name || '导入版本').trim().slice(0, 64) || '导入版本'
  const names = new Set(versions.map(version => version.name))
  if (!names.has(base)) return base
  for (let index = 1; ; index++) {
    const suffix = index === 1 ? '-导入' : `-导入${index}`
    const name = base.slice(0, 64 - suffix.length) + suffix
    if (!names.has(name)) return name
  }
}

/**
 * @param {string} text - JSON 文件文本
 * @returns {ReturnType<buildExportPayload> 兼容结构}
 */
export function parseImportPayload(text) {
  const data = JSON.parse(text)
  if (data && data.format === EXPORT_FORMAT) {
    if (!isObject(data.app) || !isObject(data.workflow)) {
      throw new Error('无效的导出文件：缺少 app 或 workflow')
    }
    if (data.formatVersion != null && data.formatVersion !== EXPORT_FORMAT_VERSION) {
      throw new Error('不支持的导出文件版本，请使用当前系统导出的 JSON')
    }
    return { ...data, workflow: importWorkflow(data.workflow) }
  }
  // 顶层即 nodes/edges（裸画布）
  if (
    data &&
    Array.isArray(data.nodes) &&
    Array.isArray(data.edges)
  ) {
    return {
      format: EXPORT_FORMAT,
      formatVersion: EXPORT_FORMAT_VERSION,
      app: { name: '导入的工作流', icon: DEFAULT_AGENT_APP_ICON, description: null },
      versionMeta: { name: 'v1.0', status: 'designing', mode: '融合编排' },
      workflow: importWorkflow(data),
      undo_stack: null
    }
  }
  if (data && data.workflow && typeof data.workflow === 'object' && Array.isArray(data.workflow.nodes)) {
    return {
      format: EXPORT_FORMAT,
      formatVersion: EXPORT_FORMAT_VERSION,
      app: data.app || { name: '导入的工作流', icon: DEFAULT_AGENT_APP_ICON, description: null },
      versionMeta: data.versionMeta || {
        name: 'v1.0',
        status: 'designing',
        mode: '融合编排'
      },
      workflow: importWorkflow(data.workflow, true),
      undo_stack: data.undo_stack ?? null
    }
  }
  throw new Error('无法识别的 JSON：请使用本系统导出的配置文件或包含 nodes/edges 的画布 JSON')
}
