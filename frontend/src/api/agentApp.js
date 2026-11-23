import request from '@/utils/request'
import { getUserIdFromToken, getCurrentSpaceId, getCurrentUser } from '@/utils/auth'
import { consumeWorkflowStream } from './workflowSse.js'

function parseSseChunk(buffer) {
  const events = []
  const buf = buffer.replace(/\r\n/g, '\n')
  const parts = buf.split('\n\n')
  const rest = parts.pop() ?? ''
  for (const part of parts) {
    for (const line of part.split('\n')) {
      if (!line.startsWith('data:')) continue
      const raw = line.slice(5).trim()
      if (!raw || raw === '[DONE]') continue
      try {
        events.push(JSON.parse(raw))
      } catch {
        events.push({ type: 'parse_error', raw })
      }
    }
  }
  return { events, rest }
}

const agentAppApi = {
  listAgentFolders() {
    return request({ url: '/agent_apps/folders', method: 'get' })
  },

  createAgentFolder(data) {
    return request({ url: '/agent_apps/folders', method: 'post', data })
  },

  updateAgentFolder(folderId, data) {
    return request({ url: `/agent_apps/folders/${folderId}`, method: 'put', data })
  },

  deleteAgentFolder(folderId) {
    return request({ url: `/agent_apps/folders/${folderId}`, method: 'delete' })
  },

  moveAgentFolder(folderId, data) {
    return request({ url: `/agent_apps/folders/${folderId}/move`, method: 'post', data })
  },

  listAgentApps(params) {
    return request({
      url: '/agent_apps',
      method: 'get',
      params
    })
  },

  getAgentApp(id) {
    return request({
      url: `/agent_apps/${id}`,
      method: 'get'
    })
  },

  createAgentApp(data) {
    return request({
      url: '/agent_apps',
      method: 'post',
      data
    })
  },

  updateAgentApp(id, data) {
    return request({
      url: `/agent_apps/${id}`,
      method: 'put',
      data
    })
  },

  deleteAgentApp(id) {
    return request({
      url: `/agent_apps/${id}`,
      method: 'delete'
    })
  },

  createVersion(appId, data) {
    return request({
      url: `/agent_apps/${appId}/versions`,
      method: 'post',
      data
    })
  },

  publishVersion(appId, versionId) {
    return request({
      url: `/agent_apps/${appId}/versions/${versionId}/publish`,
      method: 'post'
    })
  },

  onlineVersion(appId, versionId) {
    return request({
      url: `/agent_apps/${appId}/versions/${versionId}/online`,
      method: 'post'
    })
  },

  offlineVersion(appId, versionId) {
    return request({
      url: `/agent_apps/${appId}/versions/${versionId}/offline`,
      method: 'post'
    })
  },

  setOutputVersion(appId, versionId) {
    return request({
      url: `/agent_apps/${appId}/output-version`,
      method: 'put',
      data: { version_id: versionId }
    })
  },

  deleteVersion(appId, versionId) {
    return request({
      url: `/agent_apps/${appId}/versions/${versionId}`,
      method: 'delete'
    })
  },

  getWorkflow(appId, versionId) {
    return request({
      url: `/agent_apps/${appId}/versions/${versionId}/workflow`,
      method: 'get'
    })
  },

  putWorkflow(appId, versionId, data) {
    return request({
      url: `/agent_apps/${appId}/versions/${versionId}/workflow`,
      method: 'put',
      data
    })
  },

  runWorkflow(appId, versionId, data) {
    return request({
      url: `/agent_apps/${appId}/versions/${versionId}/run`,
      method: 'post',
      data: data || { inputs: {} },
      timeout: 0
    })
  },

  async runWorkflowStream(appId, versionId, data, onChunk, onNodeProgress, signal) {
    const headers = { 'Content-Type': 'application/json', Accept: 'text/event-stream' }
    const userId = getUserIdFromToken()
    const user = getCurrentUser()
    if (userId) headers['X-User-Id'] = String(userId)
    if (user?.username) headers['X-Username'] = user.username
    const spaceId = getCurrentSpaceId()
    const query = spaceId ? `?space_id=${encodeURIComponent(spaceId)}` : ''
    const response = await fetch(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/agent_apps/${appId}/versions/${versionId}/run/stream${query}`, {
      method: 'POST', headers, credentials: 'include',
      body: JSON.stringify(data || { inputs: {} }), signal
    })
    if (!response.ok) {
      const raw = await response.text()
      let message = raw
      try {
        const error = JSON.parse(raw)
        message = error.message || error.detail || raw
      } catch { /* preserve response text */ }
      throw new Error(typeof message === 'string' ? message || `HTTP ${response.status}` : JSON.stringify(message))
    }
    return consumeWorkflowStream(response.body, { onChunk, onNodeProgress })
  },

  async streamExternalAgentChat(data, options = {}) {
    const { signal, onEvent } = options
    const res = await fetch(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/external/agent-chat/sse`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream'
      },
      credentials: 'include',
      body: JSON.stringify(data),
      signal
    })

    if (!res.ok) {
      let msg = `API 调用失败 (${res.status})`
      try {
        const t = await res.text()
        try { const j = JSON.parse(t); if (j?.message) msg = j.message; else if (j?.detail) msg = j.detail } catch { if (t) msg = t.slice(0, 500) }
      } catch {
        /* ignore */
      }
      throw new Error(msg)
    }

    const reader = res.body?.getReader()
    if (!reader) {
      throw new Error('响应不支持流式读取')
    }

    const decoder = new TextDecoder()
    let carry = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      carry += decoder.decode(value, { stream: true })
      const { events, rest } = parseSseChunk(carry)
      carry = rest
      for (const ev of events) {
        onEvent?.(ev)
      }
    }

    if (carry.trim()) {
      const { events } = parseSseChunk(`${carry}\n\n`)
      for (const ev of events) {
        onEvent?.(ev)
      }
    }
  },

  getRunTrace(appId, runId) {
    return request({
      url: `/agent_apps/${appId}/runs/${runId}`,
      method: 'get',
      timeout: 0
    })
  },

  /** AI 工作流创建助手对话（长耗时） */
  aiCreatorChat(data) {
    return request({
      url: '/agent_apps/ai-chat',
      method: 'post',
      data,
      timeout: 0
    })
  },

  /** 非流式调用外部工作流 */
  runExternalAgentChat(data) {
    return request({
      url: '/external/agent-chat',
      method: 'post',
      data,
      timeout: 0
    })
  },

  /** 将 AI 输出的 workflow_design 转为画布 JSON */
  aiCreatorBuildWorkflow(data) {
    return request({
      url: '/agent_apps/ai-creator/build-workflow',
      method: 'post',
      data
    })
  },

  getAgentVersionParams(appId, versionId) {
    return request({
      url: `/agent_apps/${appId}/versions/${versionId}/params`,
      method: 'get'
    })
  }
}

export default agentAppApi
