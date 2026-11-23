import { workflowOutputText } from '../pages/agent-platform/workflow/workflowContracts.js'

/** Decode SSE across arbitrary UTF-8 chunk boundaries and surface server failures. */
export async function consumeWorkflowStream(body, { onChunk, onNodeProgress } = {}) {
  if (!body?.getReader) throw new Error('响应不支持流式读取')
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let carry = ''
  let finalEvent = null
  const consume = raw => {
    const data = raw.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n').trim()
    if (!data || data === '[DONE]') return
    let event
    try { event = JSON.parse(data) } catch { throw new Error('流式响应格式无效') }
    if (event.node_id && (event.status || event.error)) onNodeProgress?.({ ...event, status: event.error ? 'error' : event.status })
    if (event.error) throw new Error(event.error)
    if (event.status === 'done' && !event.node_id) {
      finalEvent = event
      onChunk?.(workflowOutputText(event.output))
    }
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      carry += done ? decoder.decode() : decoder.decode(value, { stream: true })
      const parts = carry.split(/\r?\n\r?\n/)
      carry = parts.pop() || ''
      parts.forEach(consume)
      if (done) break
    }
    if (carry.trim()) consume(carry)
    if (!finalEvent) throw new Error('连接已结束，但未收到执行结果，请重试或检查执行日志')
    return finalEvent
  } catch (error) {
    await reader.cancel().catch(() => {})
    throw error
  } finally {
    reader.releaseLock()
  }
}
