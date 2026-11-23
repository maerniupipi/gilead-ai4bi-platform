/**
 * 通用 SSE 客户端（支持命名事件 + JSON data）
 *
 * 后端事件规约：
 *   event: <name>\n
 *   data:  <json-string>\n\n
 *
 * 使用：
 *   await streamSse('/api/xlsx-qa/conversations/1/ask', {
 *     method: 'POST',
 *     body: { question: '...' },
 *     onEvent: (evt, data) => { ... },
 *     signal
 *   })
 */

/**
 * 把 raw SSE buffer 解析成 [{ event, data }] 数组，返回未消费剩余。
 */
function parseNamedSse(buffer) {
  const events = []
  const buf = buffer.replace(/\r\n/g, '\n')
  const parts = buf.split('\n\n')
  const rest = parts.pop() ?? ''
  for (const part of parts) {
    let evt = 'message'
    const dataLines = []
    for (const line of part.split('\n')) {
      if (!line) continue
      if (line.startsWith('event:')) {
        evt = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).replace(/^\s/, ''))
      }
      // 其它行（id: retry:）忽略
    }
    if (!dataLines.length) continue
    const raw = dataLines.join('\n')
    let data
    try {
      data = JSON.parse(raw)
    } catch {
      data = { _raw: raw }
    }
    events.push({ event: evt, data })
  }
  return { events, rest }
}

/**
 * @param {string} url
 * @param {object} options
 * @param {'GET'|'POST'} [options.method]
 * @param {any} [options.body] —— POST JSON body
 * @param {AbortSignal} [options.signal]
 * @param {(event: string, data: any) => void} options.onEvent
 */
export async function streamSse(url, options = {}) {
  const { method = 'POST', body, signal, onEvent } = options
  const res = await fetch(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    credentials: 'include',
    body: body != null ? JSON.stringify(body) : undefined,
    signal
  })

  if (!res.ok) {
    let msg = `SSE 请求失败 (${res.status})`
    try {
      const t = await res.text()
      try { const j = JSON.parse(t); msg = j?.message || msg } catch { if (t) msg = t.slice(0, 500) }
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error('当前浏览器不支持流式读取')
  const decoder = new TextDecoder()
  let carry = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    carry += decoder.decode(value, { stream: true })
    const { events, rest } = parseNamedSse(carry)
    carry = rest
    for (const e of events) onEvent?.(e.event, e.data)
  }
  if (carry.trim()) {
    const { events } = parseNamedSse(carry + '\n\n')
    for (const e of events) onEvent?.(e.event, e.data)
  }
}

/**
 * XLSX 问答专用 —— 发起一次提问。
 * 事件序列：user_message_saved → plan → sql / sql_result (N 次) → summary → done
 */
export function askXlsxQaStream(convId, payload, { onEvent, signal } = {}) {
  return streamSse(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/xlsx-qa/conversations/${convId}/ask`, {
    method: 'POST',
    body: payload,
    signal,
    onEvent
  })
}

/** 分享页：凭 token 调用免登录 ask SSE */
export function askXlsxQaShareStream(shareToken, convId, payload, { onEvent, signal } = {}) {
  const enc = encodeURIComponent(shareToken)
  return streamSse(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/xlsx-qa/share/${enc}/conversations/${convId}/ask`, {
    method: 'POST',
    body: payload,
    signal,
    onEvent
  })
}

/** 登录态：模块级深度洞察报告 SSE */
export function runInsightStream(moduleId, { onEvent, signal } = {}) {
  return streamSse(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/xlsx-qa/modules/${moduleId}/insight`, {
    method: 'POST',
    body: {},
    signal,
    onEvent
  })
}

export async function fetchInsightReport(moduleId) {
  const res = await fetch(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/xlsx-qa/modules/${moduleId}/insight`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    credentials: 'include'
  })
  if (!res.ok) throw new Error(`获取洞察报告失败 (${res.status})`)
  return unwrapJsonResponse(await res.json())
}

/** 分享页：凭 token 拉取洞察报告 SSE */
export function runInsightShareStream(shareToken, { onEvent, signal } = {}) {
  const enc = encodeURIComponent(shareToken)
  return streamSse(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/xlsx-qa/share/${enc}/insight`, {
    method: 'POST',
    body: {},
    signal,
    onEvent
  })
}

export async function fetchInsightShareReport(shareToken) {
  const enc = encodeURIComponent(shareToken)
  const res = await fetch(`${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/xlsx-qa/share/${enc}/insight`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    credentials: 'include'
  })
  if (!res.ok) throw new Error(`获取洞察报告失败 (${res.status})`)
  return unwrapJsonResponse(await res.json())
}

function unwrapJsonResponse(payload) {
  if (payload && typeof payload === 'object' && 'data' in payload && 'code' in payload) {
    return payload.data
  }
  return payload
}
