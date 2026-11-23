/**
 * 实验中心实验室 HTTP 网关（与对外接口一致）
 * POST /api/autobi/gateway/v2/lab → SSE
 */

function parseSseChunk(buffer) {
  const events = []
  const buf = buffer.replace(/\r\n/g, '\n')
  const parts = buf.split('\n\n')
  const rest = parts.pop() ?? ''
  for (const part of parts) {
    for (const line of part.split('\n')) {
      if (line.startsWith('data:')) {
        const raw = line.slice(5).trim()
        if (!raw) continue
        try {
          events.push(JSON.parse(raw))
        } catch {
          events.push({ type: 'parse_error', raw })
        }
      }
    }
  }
  return { events, rest }
}

/**
 * @param {{ content: string, id: string, features?: object }} body
 * @param {{ signal?: AbortSignal, onEvent?: (ev: object) => void }} options
 * @returns {Promise<void>}
 */
export async function streamAutobiLabGateway(body, options = {}) {
  const { signal, onEvent } = options
  const res = await fetch(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/autobi/gateway/v2/lab`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    credentials: 'include',
    body: JSON.stringify({
      content: body.content,
      id: body.id,
      features: body.features ?? undefined,
      metadata: body.metadata ?? undefined
    }),
    signal
  })

  if (!res.ok) {
    let msg = `网关请求失败 (${res.status})`
    try {
      const t = await res.text()
      try { const j = JSON.parse(t); if (j?.message) msg = j.message } catch { if (t) msg = t.slice(0, 500) }
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
    const { events } = parseSseChunk(carry + '\n\n')
    for (const ev of events) {
      onEvent?.(ev)
    }
  }
}
