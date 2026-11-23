<template>
  <el-dialog
    :model-value="modelValue"
    title="接口文档"
    fullscreen
    append-to-body
    destroy-on-close
    class="autobi-api-docs-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="api-docs-root">
      <aside class="api-docs-nav">
        <el-input
          v-model="navFilter"
          class="api-docs-search"
          placeholder="请输入关键词搜索"
          clearable
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <nav class="api-docs-tree">
          <div class="tree-folder">
            <div class="tree-folder-title">RAG</div>
            <button
              type="button"
              class="tree-leaf is-active"
              @click="scrollTo('section-overview')"
            >
              实验中心问答
            </button>
          </div>
          <div class="tree-folder is-muted">
            <div class="tree-folder-title">更多接口</div>
            <p class="tree-hint">后续将在此挂载其他接口文档；从项目卡片进入会自动带上 API ID。</p>
          </div>
        </nav>
      </aside>

      <main ref="mainScrollRef" class="api-docs-main" @scroll.passive="onMainScroll">
        <div class="api-docs-toolbar">
          <span />
          <el-button type="primary" plain :icon="DocumentCopy" @click="copyCurl">复制 curl</el-button>
        </div>

        <article class="api-docs-article">
          <section id="section-overview" class="doc-section">
            <h2>接口概述</h2>
            <p>
              <strong>实验中心 · 实验室网关</strong>用于以外部 HTTP 方式发起一次问答流水线：请求体中的
              <code>content</code> 为用户自然语言问题；
              <code>id</code> 为项目在系统内分配的 <strong>10 位 API 调用 ID</strong>（与控制台数字主键不同）；
              <code>features</code> 为可选字典，用于传入扩展参数（旧字段名 <code>metadata</code> 仍兼容）。
            </p>
            <p>
              若您在「设置」中的提示词里使用了形如 <code v-pre>{{ variable_name }}</code> 的占位符，可在
              <code>features</code> 中传入<strong>同名键</strong>：流水线加载各阶段 prompt 时，若占位符键存在于
              <code>features</code> 则先做替换，其余占位符仍按实验室原有逻辑填充。
            </p>
            <p>
              响应为 <strong>SSE（text/event-stream）</strong>：仅流式返回本次请求的 <code>trace_id</code>（便于用日志页排查）与「数据总结」正文增量；完整 18 步请求/响应与实验室一致写入 Redis。
            </p>
          </section>

          <section id="section-prereq" class="doc-section">
            <h2>前提条件</h2>
            <ul>
              <li>已获得当前项目的 <strong>API ID</strong>（10 位字母数字）。从本页进入时已自动填入下方示例。</li>
              <li>若未从项目卡片打开，请在实验中心列表卡片上查看「API ID」字段，或调用后台「获取项目详情」接口读取 <code>api_access_id</code>。</li>
              <li>生产环境请配置鉴权（如 <code>Authorization</code> / APP_KEY）；以下为本地示例，可按网关要求补充请求头。</li>
            </ul>
            <p>
              <el-link type="primary" :underline="false" disabled>（查看 APP_KEY）</el-link>
              <span class="muted"> — 接入网关后在此链向密钥说明</span>
            </p>
          </section>

          <section id="section-url" class="doc-section">
            <h2>接口调用地址</h2>
            <div class="doc-code-block mono">{{ apiBaseUrl }}</div>
          </section>

          <section id="section-params-in" class="doc-section">
            <h2>入参描述</h2>
            <p>请求体为 JSON，字段如下：</p>
            <el-table :data="paramInRows" border size="small" class="doc-table">
              <el-table-column prop="field" label="字段" width="140" />
              <el-table-column prop="type" label="数据类型" width="120" />
              <el-table-column prop="required" label="必填" width="72" />
              <el-table-column prop="desc" label="描述" min-width="200" />
            </el-table>

            <h3 class="sub-h3">编辑调用参数</h3>
            <el-form label-position="top" class="doc-form">
              <el-form-item label="content（用户问题）">
                <el-input
                  v-model="formContent"
                  type="textarea"
                  :rows="3"
                  placeholder="请输入要分析的业务问题，将写入 JSON 的 content 字段"
                />
              </el-form-item>
              <el-form-item label="id（API 调用 ID，10 位）">
                <el-input v-model="resolvedApiId" readonly class="mono-input">
                  <template v-if="!resolvedApiId" #append>
                    <span class="warn-text">未获取到 ID</span>
                  </template>
                </el-input>
              </el-form-item>
              <el-form-item label="features（键值对，可为空）">
                <div class="meta-rows">
                  <div v-for="(row, idx) in metaRows" :key="idx" class="meta-row">
                    <el-input v-model="row.key" placeholder="键 key" class="meta-k" />
                    <el-input v-model="row.value" placeholder="值 value" class="meta-v" />
                    <el-button text type="danger" @click="removeMetaRow(idx)">删除</el-button>
                  </div>
                  <el-button type="primary" link @click="addMetaRow">+ 添加键值</el-button>
                </div>
                <p v-if="placeholderHints.length" class="hint-p">
                  当前项目配置中出现的占位符变量名（供 features 参考）：
                  <el-tag
                    v-for="k in placeholderHints"
                    :key="k"
                    size="small"
                    class="tag-gap"
                    @click="quickFillMetaKey(k)"
                  >
                    {{ k }}
                  </el-tag>
                  <span class="muted">（点击标签可快速新增一行键名）</span>
                </p>
              </el-form-item>
            </el-form>
          </section>

          <section id="section-params-out" class="doc-section">
            <h2>出参描述</h2>
            <p>成功时 HTTP 200，<code>Content-Type: text/event-stream</code>。每条事件为一行 <code>data: &lt;JSON&gt;</code>：</p>
            <el-table :data="paramOutRows" border size="small" class="doc-table">
              <el-table-column prop="field" label="type 字段" width="140" />
              <el-table-column prop="type" label="含义" width="160" />
              <el-table-column prop="desc" label="描述" min-width="200" />
              <el-table-column prop="example" label="示例 payload" min-width="160" />
            </el-table>
          </section>

          <section id="section-req-example" class="doc-section">
            <h2>请求示例</h2>
            <p>根据上方表单自动生成的 curl（可直接复制到终端）：</p>
            <pre class="doc-pre">{{ curlCommand }}</pre>
          </section>

          <section id="section-res-example" class="doc-section">
            <h2>响应示例</h2>
            <pre class="doc-pre">{{ responseExample }}</pre>
          </section>

          <section id="section-status" class="doc-section">
            <h2>状态码说明</h2>
            <el-table :data="statusRows" border size="small" class="doc-table">
              <el-table-column prop="code" label="HTTP" width="100" />
              <el-table-column prop="meaning" label="说明" />
            </el-table>
          </section>
        </article>
      </main>

      <aside class="api-docs-toc">
        <div class="toc-title">文档大纲</div>
        <ul class="toc-list">
          <li
            v-for="item in tocItems"
            :key="item.id"
            :class="{ active: activeToc === item.id }"
          >
            <a href="#" @click.prevent="scrollTo(item.id)">{{ item.label }}</a>
          </li>
        </ul>
      </aside>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, DocumentCopy } from '@element-plus/icons-vue'
import { getAutobiProject } from '../api/autobi'
import { listPlaceholderKeysFromConfig } from '../utils/autobiPlaceholderHints.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** 数字主键，用于拉详情与占位符扫描 */
  projectId: { type: [Number, String], default: null },
  /** 列表已带的 api_access_id，减少闪烁 */
  apiAccessId: { type: String, default: '' },
  projectName: { type: String, default: '' }
})

defineEmits(['update:modelValue'])

const API_BASE_URL = `${window.location.origin}${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api/autobi/gateway/v2/lab`

const loading = ref(false)
const navFilter = ref('')
const mainScrollRef = ref(null)
const activeToc = ref('section-overview')
const detailApiId = ref('')
const placeholderHints = ref([])

const formContent = ref('今年华东区的销售额同比变化如何？')
const metaRows = ref([{ key: '', value: '' }])

const apiBaseUrl = API_BASE_URL

const resolvedApiId = computed(() => props.apiAccessId || detailApiId.value || '')

const featuresObject = computed(() => {
  const o = {}
  for (const r of metaRows.value) {
    const k = (r.key || '').trim()
    if (k) o[k] = r.value ?? ''
  }
  return o
})

const requestBodyJson = computed(() =>
  JSON.stringify(
    {
      content: formContent.value,
      id: resolvedApiId.value,
      features: featuresObject.value
    },
    null,
    2
  )
)

function escapeForDoubleQuotedShell(s) {
  return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\$/g, '\\$').replace(/`/g, '\\`')
}

const curlCommand = computed(() => {
  const body = escapeForDoubleQuotedShell(
    JSON.stringify({
      content: formContent.value,
      id: resolvedApiId.value,
      features: featuresObject.value
    })
  )
  return `curl -N -X POST "${API_BASE_URL}" \\\n  -H "Content-Type: application/json" \\\n  -d "${body}"`
})

const responseExample = computed(
  () => `data: {"type":"trace_id","trace_id":"550e8400-e29b-41d4-a716-446655440000"}

data: {"type":"summary","delta":"根据"}

data: {"type":"summary","delta":"查询结果"}

data: {"type":"done"}`
)

const paramInRows = [
  { field: 'content', type: 'string', required: '是', desc: '用户自然语言问题' },
  { field: 'id', type: 'string', required: '是', desc: '10 位 API 调用 ID（api_access_id），非数据库自增 id' },
  {
    field: 'features',
    type: 'object',
    required: '否',
    desc: '扩展参数；键若与提示词中 {{键名}} 同名则预先替换。兼容旧字段 metadata'
  }
]

const paramOutRows = [
  {
    field: 'trace_id',
    type: '首包',
    desc: '本次流水线追踪 UUID，可用「审计日志」页按 ID 查询全量步骤',
    example: '{"type":"trace_id","trace_id":"..."}'
  },
  {
    field: 'summary',
    type: '多次',
    desc: '数据总结正文增量，按顺序拼接即为完整总结',
    example: '{"type":"summary","delta":"..."}'
  },
  {
    field: 'error',
    type: '可选',
    desc: '流水线失败时的说明',
    example: '{"type":"error","message":"..."}'
  },
  { field: 'done', type: '结束', desc: '流结束标记', example: '{"type":"done"}' }
]

const statusRows = [
  { code: '200', meaning: 'HTTP 成功，仍需结合 body.code 判断业务是否成功' },
  { code: '400', meaning: '参数错误（如缺少 content / id）' },
  { code: '401', meaning: '未授权或 APP_KEY 无效' },
  { code: '500', meaning: '服务端异常' }
]

const tocItems = [
  { id: 'section-overview', label: '接口概述' },
  { id: 'section-prereq', label: '前提条件' },
  { id: 'section-url', label: '接口调用地址' },
  { id: 'section-params-in', label: '入参描述' },
  { id: 'section-params-out', label: '出参描述' },
  { id: 'section-req-example', label: '请求示例' },
  { id: 'section-res-example', label: '响应示例' },
  { id: 'section-status', label: '状态码说明' }
]

function addMetaRow() {
  metaRows.value.push({ key: '', value: '' })
}

function removeMetaRow(i) {
  metaRows.value.splice(i, 1)
  if (!metaRows.value.length) metaRows.value.push({ key: '', value: '' })
}

function quickFillMetaKey(k) {
  const empty = metaRows.value.find(r => !(r.key || '').trim())
  if (empty) {
    empty.key = k
  } else {
    metaRows.value.push({ key: k, value: '' })
  }
}

function scrollTo(sectionId) {
  const root = mainScrollRef.value
  if (!root) return
  const el = root.querySelector(`#${sectionId}`)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onMainScroll() {
  const root = mainScrollRef.value
  if (!root) return
  const y = root.scrollTop + 120
  for (let i = tocItems.length - 1; i >= 0; i--) {
    const id = tocItems[i].id
    const el = root.querySelector(`#${id}`)
    if (el && el.offsetTop <= y) {
      activeToc.value = id
      break
    }
  }
}

async function loadDetail() {
  if (props.projectId == null) return
  loading.value = true
  try {
    const d = await getAutobiProject(props.projectId)
    if (d.api_access_id) detailApiId.value = d.api_access_id
    placeholderHints.value = listPlaceholderKeysFromConfig(d.config_json)
  } catch {
    ElMessage.warning('加载项目详情失败，API ID 可能不完整')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.modelValue,
  v => {
    if (v && props.projectId != null) {
      detailApiId.value = props.apiAccessId || ''
      loadDetail()
    }
  }
)

function copyCurl() {
  navigator.clipboard.writeText(curlCommand.value).then(
    () => ElMessage.success('已复制 curl'),
    () => ElMessage.error('复制失败')
  )
}
</script>

<style scoped>
.api-docs-root {
  display: flex;
  height: calc(100vh - 120px);
  min-height: 480px;
  background: #f6f8fc;
  border-radius: 0 0 8px 8px;
  overflow: hidden;
}

.api-docs-nav {
  width: 240px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid #ebeef5;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.api-docs-search {
  width: 100%;
}

.api-docs-tree {
  flex: 1;
  overflow-y: auto;
  font-size: 13px;
}

.tree-folder {
  margin-bottom: 16px;
}

.tree-folder.is-muted {
  opacity: 0.75;
}

.tree-folder-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  padding-left: 4px;
}

.tree-leaf {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #606266;
  cursor: pointer;
  font-size: 13px;
}

.tree-leaf:hover {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.tree-leaf.is-active {
  color: var(--el-color-primary);
  font-weight: 600;
  background: var(--el-color-primary-light-9);
}

.tree-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  padding: 0 4px;
}

.api-docs-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 0 28px 32px;
  background: #fff;
  margin: 0 1px;
}

.api-docs-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  position: sticky;
  top: 0;
  background: #fff;
  z-index: 2;
  border-bottom: 1px solid #ebeef5;
}

.api-docs-article {
  max-width: 820px;
}

.doc-section {
  padding: 20px 0;
  border-bottom: 1px solid #ebeef5;
}

.doc-section:last-child {
  border-bottom: none;
}

.doc-section h2 {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.sub-h3 {
  margin: 20px 0 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.doc-section p {
  margin: 0 0 10px;
  font-size: 14px;
  line-height: 1.7;
  color: #606266;
}

.doc-section ul {
  margin: 0 0 10px 18px;
  color: #606266;
  line-height: 1.7;
  font-size: 14px;
}

.doc-code-block {
  background: #f4f4f5;
  padding: 12px 14px;
  border-radius: 6px;
  font-size: 13px;
  color: #303133;
  word-break: break-all;
}

.doc-code-block.mono,
.mono-input :deep(.el-input__inner) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.doc-table {
  margin-top: 12px;
  width: 100%;
}

.doc-pre {
  margin: 12px 0 0;
  padding: 14px;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.doc-form {
  margin-top: 8px;
  max-width: 640px;
}

.meta-rows {
  width: 100%;
}

.meta-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.meta-k {
  width: 160px;
}

.meta-v {
  flex: 1;
}

.hint-p {
  margin-top: 10px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

.tag-gap {
  margin: 2px 4px 2px 0;
  cursor: pointer;
}

.muted {
  color: #909399;
  font-size: 13px;
}

.warn-text {
  color: #e6a23c;
  font-size: 12px;
}

.api-docs-toc {
  width: 200px;
  flex-shrink: 0;
  background: #fafbfc;
  border-left: 1px solid #ebeef5;
  padding: 16px 12px;
}

.toc-title {
  font-weight: 600;
  font-size: 13px;
  color: #303133;
  margin-bottom: 12px;
}

.toc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-left: 2px solid #e4e7ed;
}

.toc-list li {
  margin: 0;
  padding: 0;
  position: relative;
}

.toc-list li a {
  display: block;
  padding: 6px 8px 6px 12px;
  font-size: 12px;
  color: #606266;
  text-decoration: none;
  border-radius: 0 4px 4px 0;
}

.toc-list li a:hover {
  color: var(--el-color-primary);
  background: rgba(31, 184, 204, 0.08);
}

.toc-list li.active a {
  color: var(--el-color-primary);
  font-weight: 600;
  background: rgba(31, 184, 204, 0.1);
}

.toc-list li.active::before {
  content: '';
  position: absolute;
  left: -2px;
  top: 4px;
  bottom: 4px;
  width: 2px;
  background: var(--el-color-primary);
  border-radius: 1px;
}
</style>

<style>
.autobi-api-docs-dialog .el-dialog__header {
  padding: 14px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-right: 0;
}

.autobi-api-docs-dialog .el-dialog__body {
  padding: 0 !important;
  max-height: 100vh;
  overflow: hidden;
}
</style>
