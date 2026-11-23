<template>
  <div class="conversations-page">
    <PageHeader :breadcrumbs="[{ label: '管理中心' }, { label: '对话管理' }]">
      <template #actions><el-button :icon="Refresh" @click="loadList">刷新列表</el-button></template>
    </PageHeader>

    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="page-alert" />

    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" @submit.prevent="search">
        <el-form-item label="服务 Key">
          <el-select v-model="filters.key_id" clearable filterable placeholder="全部 Key" class="key-select">
            <el-option v-for="key in keys" :key="key.id" :value="key.id" :label="`${key.name} · ${key.environment.toUpperCase()} · ${key.key_hint}${key.enabled ? '' : '（已停用）'}`" />
            <el-option label="未归属历史" value="unassigned" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户"><el-input v-model="filters.user" clearable placeholder="用户标识" class="user-input" @keyup.enter="search" /></el-form-item>
        <el-form-item label="关键词"><el-input v-model="filters.keyword" clearable placeholder="问题、答案、Session ID 或 TraceID" class="keyword-input" @keyup.enter="search" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" class="short-select">
            <el-option v-for="(name, value) in statusLabels" :key="value" :label="name" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="最近活动">
          <el-date-picker v-model="filters.range" type="datetimerange" range-separator="至" start-placeholder="开始时间" end-placeholder="结束时间" class="date-range" />
        </el-form-item>
        <el-form-item><el-button type="primary" :icon="Search" @click="search">查询</el-button><el-button @click="reset">重置</el-button></el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="records-card" v-loading="loading">
      <div class="records-heading"><strong>会话记录 <span>{{ total }}</span></strong><p>每个 Session 包含多轮问题与答案，点击查看完整对话。</p></div>
      <el-table :data="items" stripe class="session-table" empty-text="暂无符合条件的会话" @row-click="openConversation">
        <el-table-column label="会话 / 首个问题" min-width="300">
          <template #default="{ row }"><div class="session-question">{{ row.first_question || '空会话' }}</div><div class="session-id">{{ row.id }}</div></template>
        </el-table-column>
        <el-table-column label="服务 Key" min-width="190">
          <template #default="{ row }"><div>{{ row.key_name }}</div><div class="secondary">{{ row.environment?.toUpperCase() || '未归属' }} <span v-if="row.key_hint">· {{ row.key_hint }}</span></div><el-tag v-if="row.key_enabled === false" size="small" type="info">已停用</el-tag></template>
        </el-table-column>
        <el-table-column prop="user_id" label="用户标识" min-width="180" show-overflow-tooltip />
        <el-table-column prop="message_count" label="问答轮次" width="95" align="center" />
        <el-table-column label="最近状态" width="100"><template #default="{ row }"><el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="最近活动" width="175"><template #default="{ row }">{{ formatTime(row.last_active_at) }}</template></el-table-column>
        <el-table-column label="操作" width="105" fixed="right"><template #default="{ row }"><el-button link type="primary" @click.stop="openConversation(row)">查看对话</el-button></template></el-table-column>
      </el-table>
      <div class="records-pagination"><span>共 {{ total }} 个会话</span><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[10, 20, 50]" :total="total" layout="sizes, prev, pager, next" @current-change="loadList" @size-change="changeSize" /></div>
    </el-card>

    <el-drawer v-model="detailVisible" size="min(960px, 100vw)" class="conversation-drawer" @close="invalidateDetail" @closed="clearDetail">
      <template #header><div class="drawer-heading"><strong>会话详情</strong><el-button :icon="Refresh" :loading="detailLoading" @click="refreshDetail">刷新对话</el-button></div></template>
      <div v-loading="detailLoading && !messages.length" class="detail-body">
        <el-alert v-if="detailError" :title="detailError" type="error" :closable="false" show-icon class="page-alert" />
        <template v-if="conversation">
          <el-descriptions :column="2" border class="session-meta">
            <el-descriptions-item label="Session ID" :span="2"><code>{{ conversation.id }}</code></el-descriptions-item>
            <el-descriptions-item label="服务 Key">{{ conversation.key_name }} <span class="secondary">{{ conversation.key_hint }}</span></el-descriptions-item>
            <el-descriptions-item label="环境">{{ conversation.environment?.toUpperCase() || '未记录' }}</el-descriptions-item>
            <el-descriptions-item label="用户标识">{{ conversation.user_id || '未记录' }}</el-descriptions-item>
            <el-descriptions-item label="会话执行配置" :span="2">{{ runtimeLabel(conversation.runtime) }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTime(conversation.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="最近活动">{{ formatTime(conversation.last_active_at) }}</el-descriptions-item>
          </el-descriptions>
          <p v-if="conversation.attribution_source !== 'request'" class="history-note">此会话为历史记录；早期未保存的身份信息显示为“未记录”。</p>
          <div class="turns-heading"><h2>问题与答案</h2><span>已加载 {{ messages.length }} / {{ messageTotal }} 轮</span></div>
          <el-empty v-if="!detailLoading && !messages.length" description="此会话暂无问答记录" />
          <article v-for="message in messages" :key="message.id" class="turn-card">
            <header class="turn-header"><strong>第 {{ message.sequence }} 轮</strong><div><span>{{ formatTime(message.created_at) }}</span><el-tag :type="statusType(message.status)" size="small">{{ statusText(message.status) }}</el-tag></div></header>
            <section class="question-block"><div class="role-label">问题</div><p>{{ message.query }}</p></section>
            <section class="answer-block"><div class="role-label">答案</div><div v-if="message.answer" class="answer-text">{{ message.answer }}</div><p v-else class="secondary">{{ message.status === 'running' ? '回答正在生成，稍后刷新可查看结果。' : '此轮未生成答案。' }}</p></section>
            <el-alert v-if="message.error" :title="message.error" type="error" :closable="false" show-icon class="message-error" />
            <el-collapse v-if="message.content.length" class="result-details">
              <el-collapse-item v-for="(result, index) in message.content" :key="index" :name="index" :title="`${resultLabel(result.type)} · ${result.title || '执行结果'}`">
                <pre v-if="result.type === 'sql'" class="sql-preview">{{ result.outputs.sql }}</pre>
                <template v-else>
                  <el-table :data="result.outputs.rows || []" border max-height="340" size="small" empty-text="暂无数据">
                    <el-table-column v-for="column in columnsFor(result)" :key="column.key" :prop="column.key" :label="column.name || column.key" min-width="140" show-overflow-tooltip><template #default="{ row }">{{ cellValue(row[column.key]) }}</template></el-table-column>
                  </el-table>
                  <p class="preview-note">数据预览最多 50 行、30 列<span v-if="result.outputs.total_rows != null">，原结果共 {{ result.outputs.total_rows }} 行</span>。</p>
                </template>
              </el-collapse-item>
            </el-collapse>
            <ConversationDiagnostics :data="message.diagnostics" :message-id="message.id" :task-id="message.task_id" :conversation-id="conversation.id" />
            <footer class="turn-footer"><span>消息 ID：{{ message.id }}</span><span v-if="message.finished_at">耗时 {{ Math.max(0, message.finished_at - message.created_at) }} 秒</span></footer>
          </article>
          <div v-if="messages.length < messageTotal" class="load-more"><el-button :loading="detailLoading" @click="loadMore">加载后续问答</el-button></div>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Refresh, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import ConversationDiagnostics from '@/components/ConversationDiagnostics.vue'
import { listChatBIKeys } from '@/api/chatbiKeys'
import { listChatBIConversations, getChatBIConversation } from '@/api/chatbiConversations'

const filters = reactive({ key_id: '', user: '', keyword: '', status: '', kind: '', range: null })
const keys = ref([]), items = ref([]), total = ref(0), page = ref(1), pageSize = ref(20)
const loading = ref(false), error = ref('')
const detailVisible = ref(false), detailLoading = ref(false), detailError = ref('')
const conversation = ref(null), messages = ref([]), messageTotal = ref(0), messagePage = ref(1)
const selectedId = ref(null)
let listSerial = 0, detailSerial = 0
const statusLabels = { running: '生成中', succeeded: '已完成', failed: '失败', stopped: '已停止', empty: '空会话' }
const statusText = status => statusLabels[status] || status
const statusType = status => ({ running: 'warning', succeeded: 'success', failed: 'danger', stopped: 'info', empty: 'info' })[status] || 'info'
const formatTime = value => value == null ? '—' : new Date(value * 1000).toLocaleString('zh-CN', { hour12: false })
const resultLabel = type => ({ sql: 'SQL', table: '表格', chart: '图表数据' })[type] || '结果'
function runtimeLabel(value) {
  const parts = (value || '').split(':')
  if (parts[0] === 'agent') return `工作流 #${parts[1]} · 版本 #${parts[2] || '未记录'}${parts[3] ? ` · 修订 ${parts[3]}` : ''}`
  return parts[0] === 'autobi' ? `AutoBI 项目 #${parts[1]}` : value || '未记录'
}
const cellValue = value => value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
function columnsFor(result) {
  const values = result.outputs.columns || [...(result.outputs.dimensions || []), ...(result.outputs.series || [])]
  return values.filter((value, index) => values.findIndex(other => other.key === value.key) === index).slice(0, 30)
}
async function loadList() {
  const serial = ++listSerial
  loading.value = true; error.value = ''
  const params = { page: page.value, page_size: pageSize.value }
  for (const key of ['key_id', 'user', 'keyword', 'status', 'kind']) if (filters[key]?.trim()) params[key] = filters[key].trim()
  if (filters.range?.length === 2) { params.start_at = Math.floor(+filters.range[0] / 1000); params.end_at = Math.floor(+filters.range[1] / 1000) }
  try {
    const result = await listChatBIConversations(params)
    if (serial !== listSerial) return
    items.value = result.items; total.value = result.total
  } catch (failure) { if (serial === listSerial) error.value = failure.message || '加载会话失败' }
  finally { if (serial === listSerial) loading.value = false }
}
function search() { page.value = 1; loadList() }
function changeSize() { page.value = 1; loadList() }
function reset() { Object.assign(filters, { key_id: '', user: '', keyword: '', status: '', kind: '', range: null }); search() }
function openConversation(row) {
  selectedId.value = row.id; conversation.value = row; messages.value = []; messageTotal.value = row.message_count
  messagePage.value = 1; detailVisible.value = true; loadDetail(1)
}
async function loadDetail(targetPage) {
  const id = selectedId.value, serial = ++detailSerial
  if (!id) return
  detailLoading.value = true; detailError.value = ''
  try {
    const result = await getChatBIConversation(id, { page: targetPage, page_size: 20 })
    if (serial !== detailSerial || selectedId.value !== id || !detailVisible.value) return
    conversation.value = result.conversation; messageTotal.value = result.total; messagePage.value = targetPage
    messages.value = targetPage === 1 ? result.messages : [...messages.value, ...result.messages.filter(message => !messages.value.some(old => old.id === message.id))]
  } catch (failure) { if (serial === detailSerial) detailError.value = failure.message || '加载问答失败' }
  finally { if (serial === detailSerial) detailLoading.value = false }
}
function refreshDetail() { loadDetail(1) }
function loadMore() { if (!detailLoading.value) loadDetail(messagePage.value + 1) }
function invalidateDetail() { detailSerial++; detailLoading.value = false }
function clearDetail() { selectedId.value = null; conversation.value = null; messages.value = [] }
onMounted(async () => {
  await Promise.all([loadList(), listChatBIKeys().then(result => { keys.value = result }).catch(failure => { error.value = failure.message })])
})
</script>

<style scoped>
.conversations-page { padding: 28px 32px; }
.page-alert { margin-bottom: 18px; }
.filter-card { margin-bottom: 20px; }
.filter-card :deep(.el-form-item) { margin-bottom: 14px; margin-right: 24px; }
.filter-card :deep(.el-card__body) { padding: 24px 24px 10px; }
.key-select { width: 300px; } .user-input { width: 185px; } .keyword-input { width: 250px; } .short-select { width: 130px; } .date-range { width: 360px; }
.records-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
.records-heading strong { font-size: 16px; color: var(--color-gray-900); }
.records-heading strong span { margin-left: 9px; padding: 2px 9px; border-radius: 5px; background: var(--brand-mgmt-soft); color: #a96f0c; font-size: 13px; font-weight: 500; }
.records-heading p, .secondary, .preview-note { color: #8a919e; font-size: 12px; line-height: 1.7; }
.secondary { margin-top: 3px; overflow-wrap: anywhere; }
.session-table :deep(.el-table__row) { cursor: pointer; }
.session-question { color: var(--color-gray-900); line-height: 1.6; font-weight: 500; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.session-id { margin-top: 6px; font: 11px/1.6 ui-monospace, monospace; color: #9097a3; overflow-wrap: anywhere; }
.records-pagination { margin-top: 22px; display: flex; justify-content: space-between; align-items: center; gap: 20px; color: #8a919e; font-size: 13px; }
.drawer-heading { display: flex; justify-content: space-between; align-items: center; gap: 20px; width: 100%; }
.drawer-heading strong { font-size: 18px; color: #252b35; }
.detail-body { min-height: 180px; }
.session-meta { margin-bottom: 18px; } .session-meta code { overflow-wrap: anywhere; }
.history-note { color: #997335; font-size: 12px; margin: 12px 0 20px; line-height: 1.6; }
.turns-heading { display: flex; justify-content: space-between; align-items: center; margin: 28px 0 18px; }
.turns-heading h2 { font-size: 16px; font-weight: 600; }.turns-heading span { color: #8a919e; font-size: 12px; }
.turn-card { border: 1px solid #e8eaef; border-radius: 10px; overflow: hidden; margin-bottom: 22px; background: #fff; }
.turn-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 20px; border-bottom: 1px solid #edf0f3; background: #fafbfc; }
.turn-header strong { font-size: 13px; color: #505968; }.turn-header > div { display: flex; align-items: center; gap: 12px; }.turn-header > div > span:first-child { font-size: 12px; color: #9097a3; }
.question-block { padding: 18px 20px; background: #fffcf6; border-left: 3px solid var(--brand-mgmt); }
.role-label { font-size: 12px; color: #a3772a; font-weight: 600; margin-bottom: 10px; }
.question-block p, .answer-text { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.85; font-size: 14px; color: #303845; }
.answer-block { padding: 20px; }.answer-block .role-label { color: #738394; }
.message-error { margin: 0 20px 18px; width: auto; }
.result-details { margin: 0 20px 18px; border-top: 1px solid #edf0f3; }
.sql-preview { white-space: pre-wrap; overflow-wrap: anywhere; padding: 14px; border-radius: 6px; background: #f5f7fa; color: #39465a; font: 12px/1.8 ui-monospace, monospace; }
.preview-note { margin-top: 10px; }
.turn-footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding: 12px 20px; border-top: 1px solid #edf0f3; color: #99a0aa; font-size: 11px; overflow-wrap: anywhere; }
.load-more { display: flex; justify-content: center; margin: 24px 0; }
@media (max-width: 900px) { .conversations-page { padding: 20px 16px; }.records-heading { align-items: flex-start; flex-direction: column; }.records-pagination { align-items: flex-start; flex-direction: column; }.key-select, .date-range { max-width: 100%; }.turn-header { align-items: flex-start; flex-direction: column; } }
</style>
