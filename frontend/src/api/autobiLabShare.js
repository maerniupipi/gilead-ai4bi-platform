import request from '../utils/request'

/**
 * 拼出分享页完整 URL（独立端口 labShare.html + hash 路由，与主站隔离）。
 */
export function buildAutobiLabShareUrl(token, serverSuggestedBase) {
  const raw = import.meta.env.VITE_AUTOBI_LAB_SHARE_ORIGIN?.trim()
  if (raw) {
    return `${raw.replace(/\/$/, '')}/labShare.html#/${encodeURIComponent(token)}`
  }
  const sug = (serverSuggestedBase || '').trim()
  if (sug) {
    const origin = sug.replace(/\/$/, '').replace(/#.*$/, '')
    if (origin) return `${origin}/labShare.html#/${encodeURIComponent(token)}`
  }
  if (typeof window !== 'undefined') {
    const sharePort = import.meta.env.VITE_AUTOBI_LAB_SHARE_PORT?.trim() || '3840'
    const { protocol, hostname } = window.location
    return `${protocol}//${hostname}:${sharePort}/labShare.html#/${encodeURIComponent(token)}`
  }
  return `/labShare.html#/${encodeURIComponent(token)}`
}

/**
 * 免登录分享接口：路径前缀 /api/autobi/share/{token}/...
 */
export function createAutobiLabShareApi(token) {
  const enc = encodeURIComponent(token)
  const root = `/autobi/share/${enc}`
  return {
    getProject() {
      return request({ url: `${root}/project`, method: 'get' })
    },
    getChatState() {
      return request({ url: `${root}/chat-state`, method: 'get', timeout: 30000 })
    },
    saveChatState(body) {
      return request({ url: `${root}/chat-state`, method: 'put', data: body, timeout: 60000 })
    },
    getTrace(traceId) {
      return request({ url: `${root}/traces/${encodeURIComponent(traceId)}`, method: 'get' })
    },
  }
}

/**
 * SSE 网关（分享专用，不走 axios，直接 fetch）
 */
export async function streamAutobiLabShareGateway(token, body, options = {}) {
  const { signal, onEvent } = options
  const enc = encodeURIComponent(token)
  const res = await fetch(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/autobi/share/${enc}/gateway`, {
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
