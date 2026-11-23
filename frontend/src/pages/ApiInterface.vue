<template>
  <div class="api-interface-page">
    <PageHeader :breadcrumbs="[{ label: 'API 接口' }]" />

    <div class="content-wrap">
      <aside class="api-sidebar">
        <div class="sidebar-title">接口文档</div>
        <el-input v-model="keyword" placeholder="搜索接口" clearable class="api-search">
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <nav class="api-menu">
          <button
            v-for="item in filteredApis"
            :key="item.key"
            type="button"
            class="api-menu-item"
            :class="{ 'is-active': item.key === activeKey }"
            @click="selectApi(item.key)"
          >
            <span class="method">{{ item.method }}</span>
            <span class="menu-text">
              <strong>{{ item.title }}</strong>
              <small>{{ item.path }}</small>
            </span>
          </button>
        </nav>
      </aside>

      <main class="api-main">
        <section class="api-doc">
          <div class="api-heading">
            <div>
              <div class="api-eyebrow">{{ activeApi.group }}</div>
              <h2>{{ activeApi.title }}</h2>
              <p>{{ activeApi.summary }}</p>
            </div>
            <el-tag type="success" effect="plain">{{ activeApi.method }}</el-tag>
          </div>

          <div class="endpoint-line">
            <code>{{ activeApi.path }}</code>
            <el-button :icon="DocumentCopy" text type="primary" @click="copyText(activeApi.path)">复制路径</el-button>
          </div>

          <section class="doc-section">
            <h3>适用场景</h3>
            <ul>
              <li v-for="item in activeApi.scenarios" :key="item">{{ item }}</li>
            </ul>
          </section>

          <section class="doc-section">
            <h3>调用说明</h3>
            <p v-for="item in activeApi.notes" :key="item">{{ item }}</p>
          </section>

          <section class="doc-section">
            <h3>请求参数</h3>
            <el-table :data="activeApi.params" border size="small" class="doc-table">
              <el-table-column prop="field" label="字段" width="150" />
              <el-table-column prop="type" label="类型" width="130" />
              <el-table-column prop="required" label="必填" width="80" />
              <el-table-column prop="desc" label="说明" min-width="260" />
            </el-table>
          </section>

          <section class="doc-section">
            <h3>响应说明</h3>
            <el-table :data="activeApi.responseRows" border size="small" class="doc-table">
              <el-table-column prop="field" label="字段/事件" width="150" />
              <el-table-column prop="type" label="类型" width="130" />
              <el-table-column prop="desc" label="说明" min-width="260" />
            </el-table>
          </section>

          <section class="doc-section">
            <h3>请求示例</h3>
            <pre class="code-block">{{ curlCommand }}</pre>
          </section>

          <section class="doc-section">
            <h3>流式接口返回示例</h3>
            <p v-if="activeApi.streamPath" class="example-path">接口：<code>{{ activeApi.streamPath }}</code></p>
            <pre class="code-block">{{ activeApi.streamResponseExample }}</pre>
          </section>

          <section class="doc-section">
            <h3>非流式接口返回示例</h3>
            <p v-if="activeApi.nonStreamPath" class="example-path">接口：<code>{{ activeApi.nonStreamPath }}</code></p>
            <p v-else class="example-path">当前后端未暴露独立非流式 HTTP 路径；以下为调用方聚合流式事件后的推荐返回形态。</p>
            <pre class="code-block">{{ activeApi.nonStreamResponseExample }}</pre>
          </section>
        </section>

        <aside class="debug-panel">
          <div class="debug-head">
            <div>
              <h3>接口调试</h3>
              <p>已填入默认参数，可直接修改后发送。</p>
            </div>
            <el-button :icon="Refresh" text @click="resetBody">重置</el-button>
          </div>

          <el-form label-position="top" @submit.prevent>
            <el-form-item label="调试地址">
              <el-input v-model="debugUrl" class="mono-input" />
            </el-form-item>
            <el-form-item label="请求体 JSON">
              <el-input
                v-model="debugBody"
                type="textarea"
                :rows="15"
                spellcheck="false"
                class="json-editor"
              />
            </el-form-item>
          </el-form>

          <div class="debug-actions">
            <el-button :disabled="!running" @click="abortRequest">停止</el-button>
            <el-button :icon="DocumentCopy" @click="copyText(debugBody)">复制请求体</el-button>
            <el-button type="primary" :loading="running" @click="sendDebug">发送调试</el-button>
          </div>

          <div class="result-head">
            <span>调试结果</span>
            <el-tag v-if="statusText" size="small" :type="statusType">{{ statusText }}</el-tag>
          </div>
          <pre class="result-box">{{ resultText || '暂无响应' }}</pre>
        </aside>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentCopy, Refresh, Search } from '@element-plus/icons-vue'

const backendOrigin = import.meta.env.VITE_BACKEND_ORIGIN || window.location.origin

const apiDocs = [
  {
    key: 'lab',
    group: 'ChatBI 实验室',
    title: '实验室问答接口',
    method: 'POST',
    path: '/api/autobi/gateway/v2/lab',
    streamPath: '/api/autobi/gateway/v2/lab',
    nonStreamPath: '',
    summary: '以实验室项目的 API ID 发起一次自然语言数据分析，后端按实验室流水线执行，并通过 SSE 返回追踪 ID 与总结增量。',
    scenarios: [
      '第三方系统希望把 ChatBI 实验室能力嵌入自己的页面或工作台。',
      '需要用固定实验室项目、固定知识库和固定提示词配置，批量发起业务问题分析。',
      '需要通过 trace_id 回查本次请求的 SQL、表格、模型入参和各步骤调试日志。'
    ],
    notes: [
      'id 不是数据库自增主键，而是实验室项目卡片上的 10 位 API ID。缺少或填错时会返回 API ID 无效或找不到项目。',
      'features 是扩展参数对象。若实验室提示词中存在 {{region}}、{{date_range}} 这类占位符，传入同名 key 后会先完成替换，再执行流水线。',
      '接口响应是 text/event-stream。前端调试区会逐条解析 data 行；命令行建议使用 curl -N 避免缓冲。'
    ],
    params: [
      { field: 'content', type: 'string', required: '是', desc: '用户自然语言问题，例如“今年华东区销售额同比变化如何？”' },
      { field: 'id', type: 'string', required: '是', desc: '实验室项目 API ID，通常为 10 位字母数字。' },
      { field: 'features', type: 'object', required: '否', desc: '扩展参数。可用于提示词占位符替换、网关调用来源标识和业务上下文透传。' },
      { field: 'metadata', type: 'object', required: '否', desc: '旧字段名，后端仍兼容；新接入建议使用 features。' }
    ],
    responseRows: [
      { field: 'trace_id', type: 'SSE 事件', desc: '首个事件通常返回本次流水线追踪 ID，可用于查询实验室调试日志。' },
      { field: 'summary', type: 'SSE 事件', desc: '数据总结正文增量。按 delta 顺序拼接即可得到完整回答。' },
      { field: 'error', type: 'SSE 事件', desc: '流水线执行失败或项目配置不完整时返回错误说明。' },
      { field: 'done', type: 'SSE 事件', desc: '流结束标记。收到后本次请求结束。' }
    ],
    defaultBody: {
      content: '今年华东区的销售额同比变化如何？请给出关键原因和建议。',
      id: 'AB12CD34EF',
      features: {
        region: '华东区',
        date_range: '今年',
        caller: 'api-doc-debug'
      }
    },
    streamResponseExample: `data: {"type":"trace_id","trace_id":"550e8400-e29b-41d4-a716-446655440000"}

data: {"type":"summary","delta":"华东区今年销售额同比增长"}

data: {"type":"summary","delta":"，主要由重点客户复购带动。"}

data: {"type":"done"}`,
    nonStreamResponseExample: `{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "summary": "华东区今年销售额同比增长，主要由重点客户复购带动。",
  "error": null,
  "done": true
}`
  },
  {
    key: 'lab-bailian',
    group: 'ChatBI 实验室',
    title: '实验室百炼接口',
    method: 'POST',
    path: '/api/autobi/gateway/v2/lab-bailian',
    streamPath: '/api/autobi/gateway/v2/lab-bailian',
    nonStreamPath: '',
    summary: '复用实验室同源流水线，将 trace、SQL、数据、图表和总结包装成百炼兼容的 SSE data 流格式，适合接入期望百炼消息结构的外部应用。',
    scenarios: [
      '外部调用方已经按百炼消息协议渲染 progress、text、sql_citations、data_citations 或 markdown 图表。',
      '需要在实验室分析结果外层保留 app_id、created_time、token 统计、finish 和 status_code 等百炼风格字段。',
      '希望复用实验室配置和 API ID，但输出结构与普通实验室网关区分。'
    ],
    notes: [
      '入参与普通实验室问答接口一致，仍通过 id 指定实验室项目 API ID，通过 content 指定自然语言问题。',
      '接口内部会执行同一条实验室流水线，再把内部事件转换为百炼格式。message.type 可能包括 progress、sql_citations、data_citations、lab_render、markdown、text、statistics。',
      'finish=true 的 statistics 事件表示流结束。若项目未配置知识库，返回 status_code=FAILED 的百炼格式错误事件。'
    ],
    params: [
      { field: 'content', type: 'string', required: '是', desc: '用户自然语言问题。' },
      { field: 'id', type: 'string', required: '是', desc: '实验室项目 API ID，通常为 10 位字母数字。' },
      { field: 'features', type: 'object', required: '否', desc: '扩展参数。可用于提示词占位符替换、调用来源标识和业务上下文透传。' },
      { field: 'metadata', type: 'object', required: '否', desc: '旧字段名，后端仍兼容；新接入建议使用 features。' }
    ],
    responseRows: [
      { field: 'id', type: 'string', desc: '本次百炼流式响应 ID，同一次请求内保持一致。' },
      { field: 'app_id', type: 'string', desc: '实验室项目 ID 字符串。' },
      { field: 'message.type=progress', type: '事件类型', desc: '流水线进度信息，features.progress 中保存进度文案。' },
      { field: 'message.type=sql_citations', type: '事件类型', desc: 'SQL 引用，features.sql_citations 中包含 query 和 sql。' },
      { field: 'message.type=data_citations', type: '事件类型', desc: '数据引用，features.data_citations 中包含 query 和 data。' },
      { field: 'message.type=markdown', type: '事件类型', desc: '图表 markdown 块，content 中包含 bar/line/pie 代码块。' },
      { field: 'message.type=text', type: '事件类型', desc: '总结文本增量。' },
      { field: 'finish', type: 'boolean', desc: '是否结束。statistics 事件通常 finish=true。' },
      { field: 'status_code', type: 'string', desc: 'SUCCESS 或 FAILED。' }
    ],
    defaultBody: {
      content: '今年华东区的销售额同比变化如何？请给出图表和结论。',
      id: 'AB12CD34EF',
      features: {
        region: '华东区',
        date_range: '今年',
        caller: 'api-doc-bailian-debug'
      }
    },
    streamResponseExample: `data: {"id":"8f6c3b6d0b1f4d8a9f0b0c1d2e3f4a5b","app_id":"12","created_time":1770000000000,"model":"","version":"default","message":{"role":"assistant","content":"","type":"progress","features":{"progress":"正在生成 SQL"},"action_id":"a1b2c3"},"index":1,"prompt_tokens":28,"finish":false,"status_code":"SUCCESS","completion_tokens":0,"total_tokens":28}

data: {"id":"8f6c3b6d0b1f4d8a9f0b0c1d2e3f4a5b","app_id":"12","created_time":1770000000500,"model":"","version":"default","message":{"role":"assistant","content":"","type":"sql_citations","features":{"sql_citations":[{"query":"今年华东区的销售额同比变化如何？","sql":"SELECT month, sales_amount FROM sales WHERE region = '华东区'"}]},"action_id":"a1b2c3"},"index":2,"prompt_tokens":28,"finish":false,"status_code":"SUCCESS","completion_tokens":0,"total_tokens":28}

data: {"id":"8f6c3b6d0b1f4d8a9f0b0c1d2e3f4a5b","app_id":"12","created_time":1770000001200,"model":"","version":"default","message":{"role":"assistant","content":"华东区今年销售额同比增长，主要由重点客户复购带动。","type":"text","features":{},"action_id":"a1b2c3"},"index":3,"prompt_tokens":28,"finish":false,"status_code":"SUCCESS","completion_tokens":28,"total_tokens":56}

data: {"id":"8f6c3b6d0b1f4d8a9f0b0c1d2e3f4a5b","app_id":"12","created_time":1770000001800,"model":"","version":"default","message":{"role":"assistant","content":"","type":"statistics","features":{"first_token_rt":420,"tokens_per_sec":18.2,"total_tokens":56,"response_time":1800},"action_id":"a1b2c3"},"index":4,"prompt_tokens":28,"finish":true,"status_code":"SUCCESS","completion_tokens":28,"total_tokens":56}`,
    nonStreamResponseExample: `{
  "id": "8f6c3b6d0b1f4d8a9f0b0c1d2e3f4a5b",
  "app_id": "12",
  "status_code": "SUCCESS",
  "finish": true,
  "messages": [
    {
      "type": "progress",
      "content": "",
      "features": { "progress": "正在生成 SQL" }
    },
    {
      "type": "sql_citations",
      "content": "",
      "features": {
        "sql_citations": [
          {
            "query": "今年华东区的销售额同比变化如何？",
            "sql": "SELECT month, sales_amount FROM sales WHERE region = '华东区'"
          }
        ]
      }
    },
    {
      "type": "text",
      "content": "华东区今年销售额同比增长，主要由重点客户复购带动。",
      "features": {}
    }
  ],
  "statistics": {
    "first_token_rt": 420,
    "tokens_per_sec": 18.2,
    "total_tokens": 56,
    "response_time": 1800
  }
}`
  },
  {
    key: 'agent',
    group: '工作流平台',
    title: '工作流对话接口',
    method: 'POST',
    path: '/api/external/agent-chat/sse',
    streamPath: '/api/external/agent-chat/sse',
    nonStreamPath: '/api/external/agent-chat',
    summary: '对外调用已配置的工作流应用，按指定版本或当前版本运行工作流，并以 SSE 推送进度、文本、图表和结束事件。',
    scenarios: [
      '业务系统需要把已发布的工作流能力接入自己的聊天窗口或运营后台。',
      '希望固定调用某个版本进行灰度测试，或不传 version_id 直接使用当前版本。',
      '需要把用户问题和额外变量传入工作流节点，例如 question、input、conversation_id 或自定义字段。',
    ],
    notes: [
      'app_id 必填。version_id 可为空，后端会读取该工作流的当前版本；若传入 version_id，则必须属于该 app。',
      'message 会自动补齐到 inputs.question、inputs.input、inputs.user_message 和 inputs.message 中，已有同名 inputs 不会被覆盖。',
      'SSE 每条 data 中包含 data.messages。message.type 可能是 progress、text、chart_citations、sql_citations、data_citations 等，调用方应按 type 做展示兼容。',
      '如不需要流式输出，可调用非流式接口 /api/external/agent-chat，返回完整 answer、session_id 和 question_id。'
    ],
    params: [
      { field: 'app_id', type: 'number', required: '是', desc: '工作流应用 ID。' },
      { field: 'version_id', type: 'number/null', required: '否', desc: '工作流版本 ID；不传或传 null 时使用当前版本。' },
      { field: 'message', type: 'string', required: '是', desc: '用户输入的问题或指令。' },
      { field: 'conversation_id', type: 'string', required: '否', desc: '外部会话 ID。传入后可把多轮请求归到同一会话。' },
      { field: 'caller', type: 'string', required: '否', desc: '调用方标识，会写入调用日志，便于排查来源。' },
      { field: 'inputs', type: 'object', required: '否', desc: '附加输入变量，会传入工作流。' },
      { field: 'stream', type: 'boolean', required: '否', desc: '建议传 true。当前 SSE 地址按流式方式返回。' }
    ],
    responseRows: [
      { field: 'data.end', type: 'boolean', desc: '是否为本轮结束事件。true 表示流结束。' },
      { field: 'data.messages[]', type: 'array', desc: '工作流消息列表。每条消息包含 type、content、features、actionId。' },
      { field: 'message.type=progress', type: '事件类型', desc: '执行进度，例如“工作流执行中...”或节点进度。' },
      { field: 'message.type=text', type: '事件类型', desc: '工作流文本回复，按顺序拼接展示。' },
      { field: 'message.type=chart_citations', type: '事件类型', desc: '图表引用，features.chart_citations 中包含图表配置。' },
      { field: 'outSessionId', type: 'string', desc: '本次外部会话 ID。未传 conversation_id 时由后端生成。' }
    ],
    defaultBody: {
      app_id: 1,
      version_id: null,
      message: '你好，请简单介绍一下你能做什么。',
      conversation_id: 'demo-session-001',
      caller: 'api-doc-debug',
      stream: true,
      inputs: {
        input: '你好，请简单介绍一下你能做什么。',
        question: '你好，请简单介绍一下你能做什么。',
        channel: 'api-docs'
      }
    },
    streamResponseExample: `data: {"id":"0","event":"false","data":{"end":false,"messages":[{"type":"progress","content":"","features":{"progress":"工作流执行中..."}}],"outSessionId":"demo-session-001","questionId":1770000000000,"role":"assistant"}}

data: {"id":"1","event":"false","data":{"end":false,"messages":[{"type":"text","content":"你好，我可以帮你完成数据查询、分析和业务流程处理。","features":{}}],"outSessionId":"demo-session-001","questionId":1770000000000,"role":"assistant"}}

data: {"id":"2","event":"true","data":{"end":true,"messages":[{"type":"text","content":"","features":{}}],"outSessionId":"demo-session-001","questionId":1770000000000,"role":"assistant"}}`,
    nonStreamResponseExample: `{
  "answer": "你好，我可以帮你完成数据查询、分析和业务流程处理。",
  "session_id": "demo-session-001",
  "question_id": 1770000000000
}`
  }
]

const keyword = ref('')
const activeKey = ref(apiDocs[0].key)
const debugUrl = ref(apiDocs[0].path)
const debugBody = ref(JSON.stringify(apiDocs[0].defaultBody, null, 2))
const running = ref(false)
const resultText = ref('')
const statusText = ref('')
let controller = null

const filteredApis = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return apiDocs
  return apiDocs.filter(item => `${item.group}${item.title}${item.path}`.toLowerCase().includes(k))
})

const activeApi = computed(() => apiDocs.find(item => item.key === activeKey.value) || apiDocs[0])

const curlCommand = computed(() => {
  let normalizedBody = debugBody.value || '{}'
  try {
    normalizedBody = JSON.stringify(JSON.parse(normalizedBody))
  } catch {
    normalizedBody = debugBody.value || '{}'
  }
  const body = normalizedBody
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\$/g, '\\$')
    .replace(/`/g, '\\`')
  return `curl -N -X ${activeApi.value.method} "${backendOrigin}${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}${activeApi.value.path}" \\\n  -H "Content-Type: application/json" \\\n  -H "Accept: text/event-stream" \\\n  -d "${body}"`
})

const statusType = computed(() => {
  if (statusText.value.startsWith('2')) return 'success'
  if (statusText.value) return 'danger'
  return 'info'
})

watch(activeApi, (api) => {
  debugUrl.value = api.path
  debugBody.value = JSON.stringify(api.defaultBody, null, 2)
  resultText.value = ''
  statusText.value = ''
})

function selectApi(key) {
  activeKey.value = key
}

function resetBody() {
  debugUrl.value = activeApi.value.path
  debugBody.value = JSON.stringify(activeApi.value.defaultBody, null, 2)
  resultText.value = ''
  statusText.value = ''
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.error('复制失败')
  )
}

function parseSseBuffer(buffer) {
  const parts = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = parts.pop() || ''
  const events = []
  for (const part of parts) {
    const dataLines = part
      .split('\n')
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trim())
    if (!dataLines.length) continue
    const raw = dataLines.join('\n')
    if (!raw || raw === '[DONE]') continue
    try {
      events.push(JSON.stringify(JSON.parse(raw), null, 2))
    } catch {
      events.push(raw)
    }
  }
  return { events, rest }
}

async function sendDebug() {
  let payload
  try {
    payload = JSON.parse(debugBody.value)
  } catch (e) {
    ElMessage.error(`请求体不是合法 JSON：${e.message}`)
    return
  }

  resultText.value = ''
  statusText.value = ''
  running.value = true
  controller = new AbortController()

  try {
    const rawTarget = debugUrl.value.trim() || activeApi.value.path
    const target = /^https?:\/\//i.test(rawTarget) ? rawTarget : `${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}${rawTarget}`
    const res = await fetch(target, {
      method: activeApi.value.method,
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream'
      },
      credentials: 'include',
      body: JSON.stringify(payload),
      signal: controller.signal
    })
    statusText.value = `${res.status} ${res.statusText || ''}`.trim()

    const contentType = res.headers.get('content-type') || ''
    if (!res.ok) {
      resultText.value = await res.text()
      return
    }

    if (!contentType.includes('text/event-stream')) {
      resultText.value = await res.text()
      return
    }

    const reader = res.body?.getReader()
    if (!reader) {
      resultText.value = '当前浏览器不支持流式读取响应。'
      return
    }
    const decoder = new TextDecoder()
    let carry = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      carry += decoder.decode(value, { stream: true })
      const { events, rest } = parseSseBuffer(carry)
      carry = rest
      for (const event of events) {
        resultText.value += `${event}\n\n`
      }
    }
    if (carry.trim()) {
      const { events } = parseSseBuffer(`${carry}\n\n`)
      for (const event of events) {
        resultText.value += `${event}\n\n`
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      resultText.value += '\n请求已停止。'
    } else {
      resultText.value = e.message || '请求失败'
      statusText.value = '请求失败'
    }
  } finally {
    running.value = false
    controller = null
  }
}

function abortRequest() {
  controller?.abort()
}
</script>

<style scoped>
.api-interface-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.content-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}

.api-sidebar {
  width: 282px;
  flex: 0 0 282px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px 14px;
  border-right: 1px solid #e5e7eb;
  background: #f8fafc;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.api-search {
  width: 100%;
}

.api-menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
}

.api-menu-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  width: 100%;
  padding: 11px;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
}

.api-menu-item:hover,
.api-menu-item.is-active {
  background: #fff;
  border-color: var(--el-color-primary-light-7);
}

.method {
  flex: 0 0 auto;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
}

.menu-text {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.menu-text strong {
  font-size: 14px;
  color: #1f2937;
}

.menu-text small {
  font-size: 12px;
  color: #64748b;
  word-break: break-all;
  line-height: 1.35;
}

.api-main {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  overflow: hidden;
}

.api-doc {
  min-width: 0;
  overflow-y: auto;
  padding: 24px 28px 36px;
}

.api-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 18px;
  border-bottom: 1px solid #e5e7eb;
}

.api-eyebrow {
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--el-color-primary);
  font-weight: 600;
}

.api-heading h2 {
  margin: 0 0 8px;
  font-size: 24px;
  line-height: 1.25;
  color: #111827;
}

.api-heading p {
  margin: 0;
  max-width: 760px;
  font-size: 14px;
  line-height: 1.7;
  color: #4b5563;
}

.endpoint-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 18px 0 6px;
  padding: 12px 14px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}

.endpoint-line code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: var(--el-color-primary-dark-2);
  word-break: break-all;
}

.doc-section {
  padding: 22px 0;
  border-bottom: 1px solid #edf2f7;
}

.doc-section h3 {
  margin: 0 0 12px;
  font-size: 17px;
  color: #111827;
}

.doc-section p,
.doc-section li {
  font-size: 14px;
  line-height: 1.75;
  color: #4b5563;
}

.doc-section p {
  margin: 0 0 10px;
}

.doc-section ul {
  margin: 0;
  padding-left: 20px;
}

.example-path {
  color: #64748b;
}

.example-path code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: var(--el-color-primary-dark-2);
}

.doc-table {
  width: 100%;
}

.code-block,
.result-box {
  margin: 0;
  padding: 14px;
  border-radius: 8px;
  background: #111827;
  color: #d1d5db;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  overflow: auto;
}

.debug-panel {
  min-width: 0;
  overflow-y: auto;
  padding: 20px;
  border-left: 1px solid #e5e7eb;
  background: #fbfdff;
}

.debug-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.debug-head h3 {
  margin: 0 0 6px;
  font-size: 18px;
  color: #111827;
}

.debug-head p {
  margin: 0;
  font-size: 13px;
  color: #64748b;
}

.mono-input :deep(.el-input__inner),
.json-editor :deep(.el-textarea__inner) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.debug-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 16px;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #111827;
}

.result-box {
  min-height: 220px;
  max-height: 420px;
}

@media (max-width: 1180px) {
  .api-main {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .api-doc,
  .debug-panel {
    overflow: visible;
  }

  .debug-panel {
    border-left: none;
    border-top: 1px solid #e5e7eb;
  }
}

@media (max-width: 760px) {
  .content-wrap {
    flex-direction: column;
    overflow-y: auto;
  }

  .api-sidebar {
    width: auto;
    flex: 0 0 auto;
    border-right: none;
    border-bottom: 1px solid #e5e7eb;
  }

  .api-doc {
    padding: 18px;
  }
}
</style>
