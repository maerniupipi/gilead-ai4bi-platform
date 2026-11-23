import request from '../utils/request'

const API_BASE = `${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api`

/**
 * 发送聊天消息（调用 LLM）
 * @param {Object} data - 请求参数
 * @param {number} [timeout=120000] - 超时时间（毫秒），LLM 调用需要较长超时
 */
export const sendChatMessage = (data, timeout = 120000) => {
  return request({
    url: '/chat/send',
    method: 'post',
    data,
    timeout
  })
}

/**
 * 流式发送聊天消息（调用 LLM）
 * @param {Object} data - 请求参数
 * @param {function(string): void} onChunk - 每次接收到内容块时的回调，参数为增量文本
 * @param {AbortSignal} [signal] - 可选的 AbortSignal 用于取消请求
 * @returns {Promise<void>}
 */
export const streamChatMessage = async (data, onChunk, signal) => {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal
  })

  if (!response.ok) {
    const errText = await response.text()
    throw new Error(errText || `HTTP ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const jsonStr = line.slice(6).trim()
        if (jsonStr === '[DONE]') return
        try {
          const parsed = JSON.parse(jsonStr)
          const content = parsed?.choices?.[0]?.delta?.content || ''
          if (content) onChunk(content)
        } catch {
          // 忽略解析错误
        }
      }
    }
  }
}
