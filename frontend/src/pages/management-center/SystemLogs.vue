<template>
  <div class="system-logs-page">
    <PageHeader :breadcrumbs="[{ label: '管理中心' }, { label: '系统日志' }]"><template #actions><el-switch v-model="automatic" active-text="每 10 秒刷新" /><el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button></template></PageHeader>
    <div class="log-intro"><div><strong>系统日志</strong><p>按请求、会话和 TraceID 串联执行过程。数据库仅保留最近 7 天。</p></div><el-tag effect="plain" type="info">最近 7 天</el-tag></div>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="log-alert" />
    <el-alert v-if="dropped" :title="'日志写入暂不可用或队列繁忙，当前进程有 ' + dropped + ' 条未入库；详细信息仍保留在服务日志中。'" type="warning" show-icon :closable="false" class="log-alert" />
    <el-card shadow="never" class="log-filters"><el-form :inline="true" @submit.prevent="search">
      <el-form-item label="时间"><el-date-picker v-model="range" type="datetimerange" start-placeholder="开始时间" end-placeholder="结束时间" :disabled-date="disabledDate" /></el-form-item>
      <el-form-item label="级别"><el-select v-model="filters.level" clearable placeholder="全部" style="width:130px"><el-option v-for="level in levels" :key="level" :label="level" :value="level" /></el-select></el-form-item>
      <el-form-item label="关键词"><el-input v-model="filters.keyword" clearable placeholder="日志、模块、异常信息" @keyup.enter="search" /></el-form-item>
      <el-form-item v-for="item in identityFilters" :key="item.key" :label="item.label"><el-input v-model="filters[item.key]" clearable :placeholder="item.label" @keyup.enter="search" /></el-form-item>
      <el-form-item><el-button type="primary" :icon="Search" @click="search">查询</el-button><el-button @click="reset">重置</el-button></el-form-item>
    </el-form></el-card>
    <el-card shadow="never" class="log-records" v-loading="loading">
      <div class="records-top"><strong>日志记录 <span>{{ total }}</span></strong><span>时间倒序 · 点击查看完整内容</span></div>
      <el-table :data="items" stripe empty-text="暂无符合条件的系统日志" @row-click="selected = $event">
        <el-table-column label="时间" width="190"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="级别" width="95"><template #default="{ row }"><el-tag size="small" :type="levelType(row.level)">{{ row.level }}</el-tag></template></el-table-column>
        <el-table-column prop="logger" label="模块" min-width="190" show-overflow-tooltip />
        <el-table-column prop="message" label="事件" min-width="320" show-overflow-tooltip />
        <el-table-column prop="user_id" label="用户标识" width="120" />
        <el-table-column prop="request_id" label="Request ID" min-width="180" show-overflow-tooltip />
        <el-table-column prop="trace_id" label="TraceID" min-width="180" show-overflow-tooltip />
      </el-table>
      <div class="log-pagination"><span>共 {{ total }} 条</span><el-pagination v-model:current-page="page" v-model:page-size="pageSize" :page-sizes="[20, 50, 100]" :total="total" layout="sizes, prev, pager, next" @current-change="load" @size-change="search" /></div>
    </el-card>
    <el-drawer :model-value="!!selected" title="日志详情" size="min(900px, 96vw)" @update:model-value="!$event && (selected = null)">
      <template v-if="selected"><div class="detail-tools"><el-tag :type="levelType(selected.level)">{{ selected.level }}</el-tag><el-button link type="primary" @click="copy(selected)">复制完整日志</el-button></div>
        <el-descriptions :column="1" border><el-descriptions-item v-for="item in detailFields" :key="item.key" :label="item.label"><code>{{ selected[item.key] || '—' }}</code></el-descriptions-item></el-descriptions>
        <h3>日志内容</h3><pre class="log-code">{{ selected.message }}</pre>
        <template v-if="selected.exception"><h3>异常堆栈</h3><pre class="log-code error-code">{{ selected.exception }}</pre></template>
        <h3>关联参数</h3><pre class="log-code">{{ JSON.stringify(selected.data, null, 2) }}</pre>
      </template>
    </el-drawer>
  </div>
</template>
<script setup>
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader.vue'
import { listSystemLogs } from '@/api/systemLogs'
const route = useRoute(), router = useRouter()
const filters = reactive({ level:'', keyword:'', request_id:'', conversation_id:'', message_id:'', trace_id:'', user_id:'', service:'' })
const identityFilters = [{key:'request_id',label:'Request ID'},{key:'conversation_id',label:'Session ID'},{key:'message_id',label:'Message ID'},{key:'trace_id',label:'TraceID'},{key:'user_id',label:'用户标识'},{key:'service',label:'服务'}]
const detailFields = [{key:'created_at_text',label:'时间'},{key:'instance',label:'实例'},{key:'logger',label:'模块'},...identityFilters]
const levels = ['DEBUG','INFO','WARNING','ERROR','CRITICAL']
const items=ref([]), total=ref(0), page=ref(1), pageSize=ref(50), loading=ref(false), error=ref(''), dropped=ref(0), selected=ref(null), range=ref(null), automatic=ref(false)
let serial=0
const formatTime = value => new Date(value).toLocaleString('zh-CN',{hour12:false})
const levelType = value => ['ERROR','CRITICAL'].includes(value) ? 'danger' : value === 'WARNING' ? 'warning' : value === 'DEBUG' ? 'info' : 'success'
const disabledDate = value => value.getTime() < Date.now()-8*86400000 || value.getTime() > Date.now()
async function load() {
  const current=++serial
  loading.value=true; error.value=''
  const params={page:page.value,page_size:pageSize.value}
  for (const [key,value] of Object.entries(filters)) if (value) params[key]=value
  if (range.value?.length===2) { params.start_at=+range.value[0]; params.end_at=+range.value[1] }
  try {
    const result=await listSystemLogs(params)
    if (current!==serial) return
    items.value=result.items.map(row=>({...row,created_at_text:formatTime(row.created_at)})); total.value=result.total; dropped.value=result.dropped_logs
  } catch (failure) { if (current===serial) error.value=failure.message || '加载日志失败' }
  finally { if (current===serial) loading.value=false }
}
function search() { page.value=1; load() }
function applyRoute() { for (const key of Object.keys(filters)) filters[key]=String(route.query[key] || ''); search() }
function reset() { range.value=null; for (const key of Object.keys(filters)) filters[key]=''; router.replace({query:{}}); search() }
async function copy(value) { try { await navigator.clipboard.writeText(JSON.stringify(value,null,2)); ElMessage.success('已复制') } catch { ElMessage.warning('复制失败，请手动复制') } }
watch(()=>route.query,applyRoute)
const timer=setInterval(()=>{ if(automatic.value && !loading.value) load() },10000)
onMounted(applyRoute)
onUnmounted(()=>{serial++;clearInterval(timer)})
</script>
<style scoped>
.system-logs-page { padding:28px 32px; }.log-intro { display:flex; align-items:center; justify-content:space-between; margin:4px 0 22px; }.log-intro strong { font-size:20px; color:#283441; }.log-intro p { margin:8px 0 0; color:#82909e; font-size:13px; }.log-filters { margin-bottom:20px; }.log-filters :deep(.el-card__body) { padding-bottom:8px; }.log-filters :deep(.el-input) { width:200px; }.log-filters :deep(.el-form-item) { margin-right:20px; }.log-alert { margin-bottom:16px; }.records-top,.log-pagination { display:flex; align-items:center; justify-content:space-between; gap:16px; margin:0 0 18px; }.records-top strong { font-size:15px; }.records-top strong span { padding:3px 9px; background:var(--brand-mgmt-soft,#fff6df); color:#a77816; border-radius:5px; margin-left:8px; }.records-top > span,.log-pagination > span { font-size:12px; color:#8996a3; }.log-pagination { margin:20px 0 0; }.log-records :deep(.el-table__row) { cursor:pointer; }.detail-tools { display:flex; align-items:center; justify-content:space-between; margin-bottom:20px; }.log-code { white-space:pre-wrap; overflow-wrap:anywhere; padding:16px; background:#f5f7fa; border:1px solid #e9edf2; border-radius:7px; font:12px/1.8 ui-monospace,monospace; color:#35465a; }.error-code { background:#fff8f7; color:#a03d36; }code { overflow-wrap:anywhere; }h3 { font-size:14px; margin:24px 0 12px; }@media(max-width:900px) { .system-logs-page { padding:20px 16px; }.log-intro,.records-top,.log-pagination { align-items:flex-start; flex-direction:column; } }
</style>
