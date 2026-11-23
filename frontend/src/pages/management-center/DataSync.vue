<template>
  <div class="sync-page">
    <header class="sync-heading">
      <div><p class="eyebrow">平台 · 数据管理</p><h1>数据同步</h1><p class="subtitle">管理已配置的数据同步任务，查看执行计划、进度和运行记录。</p></div>
      <el-button :icon="Refresh" :loading="loading" @click="refresh()">刷新</el-button>
    </header>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon />
    <div class="sync-summary"><span><i :class="{ live: runningCount }" />{{ runningCount }} 个任务排队或执行中</span><span>{{ enabledCount }} / {{ tasks.length }} 个定时计划已启用</span><span class="refresh-note">每 5 秒更新</span></div>

    <section class="task-grid" aria-label="同步任务">
      <article v-for="task in tasks" :key="task.id" class="task-card">
        <div class="task-top"><span class="table-code">{{ task.id.toUpperCase() }}</span><el-tag :type="task.active_run_id ? 'primary' : task.configuration.ready ? 'success' : 'warning'" size="small">{{ task.active_run_id ? '任务进行中' : task.configuration.ready ? '可执行' : '待配置' }}</el-tag></div>
        <h2>{{ task.name }}</h2><p class="target-name">{{ task.configuration.target_table }}</p>
        <div class="schedule-line"><el-icon><Clock /></el-icon><span>{{ task.schedule_enabled ? task.cron_expression : '定时执行未启用' }}</span><small v-if="task.schedule_enabled">{{ task.timezone }}</small></div>
        <div class="next-time">下次执行 <strong>{{ task.next_run_at ? formatTime(task.next_run_at, task.timezone) : '—' }}</strong></div>
        <div v-if="task.last_run" class="last-run" @click="openDetail(task.last_run.id)"><span>最近执行</span><el-tag :type="statusType(task.last_run.status)" size="small">{{ statusLabel(task.last_run.status) }}</el-tag><span>{{ number(task.last_run.fetched_rows) }} 行</span><el-icon><ArrowRight /></el-icon></div>
        <div v-else class="last-run empty-last">暂无执行记录</div>
        <p v-if="!task.configuration.ready" class="config-warning">{{ task.configuration.message }}</p>
        <div class="task-actions"><el-button @click="editTask(task)">配置计划</el-button><el-button type="primary" :icon="VideoPlay" :loading="starting === task.id" :disabled="Boolean(task.active_run_id) || !task.configuration.ready" @click="start(task)">立即同步</el-button></div>
      </article>
    </section>

    <section class="runs-panel">
      <div class="runs-heading"><div><h2>同步记录</h2><p>手动执行与定时执行统一留存，可查看阶段和处理行数。</p></div>
        <div class="filters"><el-select v-model="filters.task_id" placeholder="全部数据" clearable aria-label="筛选同步数据" @change="changeFilter"><el-option v-for="task in tasks" :key="task.id" :value="task.id" :label="task.name" /></el-select>
          <el-select v-model="filters.status" placeholder="全部状态" clearable aria-label="筛选运行状态" @change="changeFilter"><el-option v-for="(label, value) in statuses" :key="value" :value="value" :label="label" /></el-select></div>
      </div>
      <el-table :data="runs" stripe empty-text="暂无同步记录，配置完成后可立即同步或启用定时计划">
        <el-table-column prop="task_name" label="同步任务" min-width="140" />
        <el-table-column label="触发方式" width="100"><template #default="{ row }">{{ row.trigger_type === 'manual' ? '手动执行' : '定时执行' }}</template></el-table-column>
        <el-table-column label="状态 / 阶段" min-width="180"><template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag><span class="stage-label">{{ stages[row.stage] || '' }}</span></template></el-table-column>
        <el-table-column label="已拉取 / 已入库" min-width="160"><template #default="{ row }"><span class="numeric">{{ number(row.fetched_rows) }} / {{ number(row.status === 'succeeded' ? row.loaded_rows : 0) }}</span></template></el-table-column>
        <el-table-column label="开始时间" min-width="170"><template #default="{ row }">{{ formatTime(row.started_at || row.created_at) }}</template></el-table-column>
        <el-table-column label="耗时" width="95"><template #default="{ row }">{{ duration(row.elapsed_seconds) }}</template></el-table-column>
        <el-table-column label="操作" width="90" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openDetail(row.id)">查看详情</el-button></template></el-table-column>
      </el-table>
      <div class="pagination"><el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="refresh()" /></div>
    </section>

    <el-dialog v-model="editing" title="配置同步计划" width="min(540px, 94vw)" destroy-on-close>
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="任务名称"><el-input v-model="form.name" maxlength="100" /></el-form-item>
        <el-form-item label="定时执行"><el-switch v-model="form.schedule_enabled" /><span class="form-hint">关闭后仍可手动执行</span></el-form-item>
        <el-form-item label="执行规则（Cron）"><el-input v-model="form.cron_expression" placeholder="0 2 * * *" /><div class="cron-presets"><el-button size="small" @click="form.cron_expression = '0 2 * * *'">每天 02:00</el-button><el-button size="small" @click="form.cron_expression = '0 */6 * * *'">每 6 小时</el-button><el-button size="small" @click="form.cron_expression = '0 2 * * 1'">每周一 02:00</el-button></div><small class="field-note">依次填写：分、时、日、月、周。支持 *、范围、列表和步长。</small></el-form-item>
        <el-form-item label="执行时区"><el-select v-model="form.timezone" filterable allow-create default-first-option style="width:100%"><el-option label="北京时间 · Asia/Shanghai" value="Asia/Shanghai" /><el-option label="协调世界时 · UTC" value="UTC" /></el-select></el-form-item>
        <el-alert title="同一张表同时只运行一个任务。上一任务未完成时，到期的计划会记录为已跳过。" type="info" :closable="false" show-icon />
      </el-form>
      <template #footer><el-button @click="editing = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存计划</el-button></template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="同步详情" size="min(700px, 96vw)" @closed="closeDetail">
      <div v-if="detail" class="detail-content">
        <div class="detail-title"><h2>{{ detail.task_name }}</h2><el-tag :type="statusType(detail.status)">{{ statusLabel(detail.status) }}</el-tag></div>
        <p class="run-id">运行编号 {{ detail.id }}</p>
        <div class="phase-strip"><span v-for="(label, index) in phaseNames" :key="label" :class="{ current: phaseIndex(detail.stage) === index, passed: phaseIndex(detail.stage) > index }">{{ label }}</span></div>
        <p class="detail-message" role="status">{{ detail.message }}</p>
        <template v-if="detail.stage === 'staging' && detail.total_rows"><div class="progress-caption"><span>暂存表 COPY 进度</span><span>{{ number(detail.loaded_rows) }} / {{ number(detail.total_rows) }}</span></div><el-progress :percentage="Math.min(100, Math.floor(detail.loaded_rows / detail.total_rows * 100))" /></template>
        <div v-else-if="isActive(detail.status)" class="indeterminate-track" role="progressbar" aria-label="同步进行中，总量待确认" aria-valuetext="数据总量尚未确定"><span /></div>
        <el-progress v-else-if="detail.status === 'succeeded'" :percentage="100" status="success" />
        <div class="detail-metrics"><div><span>已拉取</span><strong>{{ number(detail.fetched_rows) }}</strong></div><div><span>已入库</span><strong>{{ number(detail.status === 'succeeded' ? detail.loaded_rows : 0) }}</strong></div><div><span>已处理页数</span><strong>{{ number(detail.page_no) }}</strong></div></div>
        <el-alert v-if="detail.error" :title="detail.error" type="error" :closable="false" show-icon />
        <el-descriptions :column="1" size="small"><el-descriptions-item label="触发方式">{{ detail.trigger_type === 'manual' ? '手动执行' : '定时执行' }}</el-descriptions-item><el-descriptions-item label="创建时间">{{ formatTime(detail.created_at) }}</el-descriptions-item><el-descriptions-item label="开始时间">{{ formatTime(detail.started_at) }}</el-descriptions-item><el-descriptions-item label="结束时间">{{ formatTime(detail.finished_at) }}</el-descriptions-item><el-descriptions-item label="执行耗时">{{ duration(detail.elapsed_seconds) }}</el-descriptions-item></el-descriptions>
        <h3>执行进度</h3><p v-if="!events.length" class="field-note">{{ detail.status === 'queued' ? '等待工作进程领取任务' : '暂无阶段事件' }}</p>
        <ol class="event-list"><li v-for="event in events" :key="event.id"><time>{{ formatTime(event.created_at) }}</time><strong>{{ stages[event.stage] || statusLabel(event.stage) }}</strong><p>{{ event.message }}</p><small v-if="event.fetched_rows">已拉取 {{ number(event.fetched_rows) }} 行<span v-if="event.loaded_rows"> · 已 COPY {{ number(event.loaded_rows) }} 行</span></small></li></ol>
        <el-button v-if="moreEvents" :loading="detailLoading" @click="refreshDetail()">加载后续进度</el-button>
      </div>
      <el-empty v-else-if="!detailLoading" description="无法读取同步详情" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ArrowRight, Clock, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getSyncRun, listSyncRuns, listSyncTasks, startSyncTask, updateSyncTask } from '@/api/dataSync'

const tasks = ref([]), runs = ref([]), total = ref(0), page = ref(1)
const loading = ref(false), loadError = ref(''), starting = ref(''), saving = ref(false), editing = ref(false)
const detail = ref(null), events = ref([]), detailVisible = ref(false), detailLoading = ref(false), moreEvents = ref(false)
const filters = reactive({ task_id: '', status: '' })
const form = reactive({ id: '', name: '', schedule_enabled: false, cron_expression: '0 2 * * *', timezone: 'Asia/Shanghai' })
const statuses = { queued: '排队中', running: '执行中', succeeded: '成功', failed: '失败', interrupted: '已中断', skipped: '已跳过' }
const stages = { queued: '等待执行', preparing: '准备同步', fetching: '拉取与校验', staging: '写入暂存表', replacing: '提交正式表' }
const phaseNames = ['准备', '拉取与校验', '暂存写入', '正式提交', '完成']
const runningCount = computed(() => tasks.value.filter(task => task.active_run_id).length)
const enabledCount = computed(() => tasks.value.filter(task => task.schedule_enabled).length)
let disposed = false, timer, requestVersion = 0, detailVersion = 0, detailId = ''
const number = value => Number(value || 0).toLocaleString('zh-CN')
const isActive = status => ['queued', 'running'].includes(status)
const statusLabel = status => statuses[status] || status
const statusType = status => ({ succeeded: 'success', failed: 'danger', interrupted: 'warning', running: 'primary' }[status] || 'info')
const phaseIndex = stage => ({ queued: -1, preparing: 0, fetching: 1, staging: 2, replacing: 3, succeeded: 4 }[stage] ?? -1)
function formatTime(value, timeZone = 'Asia/Shanghai') {
  if (!value) return '—'
  return new Date(value * 1000).toLocaleString('zh-CN', { timeZone, hour12: false })
}
function duration(value) {
  const seconds = Math.max(0, Number(value || 0))
  return seconds >= 3600 ? `${Math.floor(seconds / 3600)} 小时 ${Math.floor(seconds % 3600 / 60)} 分` : seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`
}
async function refresh(quiet = false) {
  const version = ++requestVersion
  if (!quiet) loading.value = true
  try {
    const [taskData, runData] = await Promise.all([listSyncTasks(), listSyncRuns({ task_id: filters.task_id || undefined, status: filters.status || undefined, offset: (page.value - 1) * 20, limit: 20 })])
    if (disposed || version !== requestVersion) return
    tasks.value = taskData; runs.value = runData.items; total.value = runData.total; loadError.value = ''
  } catch (error) {
    if (!disposed && version === requestVersion) loadError.value = error.message || '加载同步任务失败'
  } finally {
    if (version === requestVersion) loading.value = false
  }
}
function changeFilter() { page.value = 1; refresh() }
function editTask(task) {
  Object.assign(form, { id: task.id, name: task.name, schedule_enabled: task.schedule_enabled, cron_expression: task.cron_expression, timezone: task.timezone }); editing.value = true
}
async function save() {
  if (!form.name.trim()) return ElMessage.warning('请填写任务名称')
  saving.value = true
  try {
    const { id, ...body } = form
    await updateSyncTask(id, body); editing.value = false; ElMessage.success('同步计划已保存'); await refresh()
  } catch (error) { ElMessage.error(error.message) } finally { saving.value = false }
}
async function start(task) {
  starting.value = task.id
  try {
    const run = await startSyncTask(task.id); ElMessage.success('已进入同步队列'); page.value = 1; await refresh(); await openDetail(run.id)
  } catch (error) { ElMessage.error(error.message) } finally { starting.value = '' }
}
async function openDetail(id) {
  detailVersion++; detailId = id; detail.value = null; events.value = []; moreEvents.value = false; detailVisible.value = true
  await refreshDetail()
}
function closeDetail() { detailVersion++; detailId = ''; detail.value = null; events.value = [] }
async function refreshDetail() {
  if (!detailId || !detailVisible.value) return
  const id = detailId, version = ++detailVersion
  detailLoading.value = true
  try {
    const data = await getSyncRun(id, { after_event_id: events.value.at(-1)?.id || 0, limit: 100 })
    if (disposed || id !== detailId || version !== detailVersion) return
    detail.value = data.run; events.value.push(...data.events); moreEvents.value = data.has_more_events
  } catch (error) { if (!disposed && version === detailVersion) ElMessage.error(error.message) }
  finally { if (version === detailVersion) detailLoading.value = false }
}
async function poll() {
  await Promise.all([refresh(true), detailLoading.value ? Promise.resolve() : refreshDetail()])
  if (!disposed) timer = setTimeout(poll, 5000)
}
onMounted(poll)
onBeforeUnmount(() => { disposed = true; requestVersion++; detailVersion++; clearTimeout(timer) })
</script>

<style scoped>
.sync-page { display:flex; flex-direction:column; gap:22px; padding:4px 0 20px; color:var(--color-gray-900, #192b25); }
.sync-heading,.task-top,.task-actions,.runs-heading,.detail-title,.progress-caption { display:flex; align-items:center; justify-content:space-between; gap:16px; }
.eyebrow { margin:0 0 7px; color:var(--el-color-primary); font-size:12px; font-weight:650; letter-spacing:.1em; }
h1 { margin:0; font-size:28px; font-weight:650; letter-spacing:-.03em; } h2 { margin:0; font-size:18px; font-weight:600; } h3 { margin:8px 0 0; font-size:16px; }
.subtitle,.runs-heading p { margin:8px 0 0; color:var(--color-gray-500, #758079); font-size:13px; line-height:1.6; }
.sync-summary { display:flex; gap:26px; align-items:center; font-size:12px; color:var(--color-gray-500, #758079); }
.sync-summary span:first-child { display:flex; align-items:center; gap:7px; } .sync-summary i { width:7px; height:7px; border-radius:50%; background:#aab3ad; } .sync-summary i.live { background:var(--el-color-primary); }
.refresh-note { margin-left:auto; } .task-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:18px; }
.task-card { padding:22px; border:1px solid var(--color-gray-200, #e4e9e5); background:var(--color-white, #fff); border-radius:12px; display:flex; flex-direction:column; }
.task-top { margin-bottom:18px; }.table-code { font-family:monospace; color:var(--el-color-primary); letter-spacing:.12em; font-size:13px; font-weight:bold; }
.target-name { font-family:monospace; font-size:12px; color:var(--color-gray-400, #8c9890); margin:7px 0 24px; overflow-wrap:anywhere; }
.schedule-line { display:flex; gap:7px; align-items:center; font-size:13px; flex-wrap:wrap; }.schedule-line small { color:var(--color-gray-400, #8c9890); }
.next-time { display:flex; flex-wrap:wrap; gap:10px; color:var(--color-gray-500, #758079); margin:12px 0 20px; font-size:12px; }.next-time strong { font-weight:500; color:var(--color-gray-700, #3d5146); }
.last-run { display:flex; align-items:center; gap:10px; min-height:29px; padding:12px 0; border-top:1px solid var(--color-gray-100, #f0f3f0); font-size:12px; cursor:pointer; }.last-run .el-icon { margin-left:auto; }.empty-last { color:var(--color-gray-400, #8c9890); cursor:default; }
.config-warning { color:#a66b14; font-size:12px; line-height:1.6; overflow-wrap:anywhere; margin:4px 0 16px; }.task-actions { margin-top:auto; padding-top:12px; }.task-actions .el-button { flex:1; margin-left:0; }
.runs-panel { border:1px solid var(--color-gray-200, #e4e9e5); border-radius:12px; overflow:hidden; background:var(--color-white, #fff); }.runs-heading { padding:22px; }.runs-heading h2 { font-size:17px; }.filters { display:flex; gap:10px; }.filters .el-select { width:145px; }.stage-label { margin-left:8px; font-size:12px; color:var(--color-gray-500, #758079); }.numeric { font-variant-numeric:tabular-nums; }.pagination { padding:18px; display:flex; justify-content:flex-end; }
.cron-presets { display:flex; gap:6px; margin:10px 0 5px; flex-wrap:wrap; }.cron-presets .el-button { margin:0; }.field-note,.form-hint { color:var(--color-gray-500, #758079); font-size:12px; line-height:1.7; }.form-hint { margin-left:12px; }
.detail-content { display:flex; flex-direction:column; gap:18px; }.run-id { margin:0; font-family:monospace; font-size:12px; color:var(--color-gray-400, #8c9890); overflow-wrap:anywhere; }.phase-strip { display:flex; gap:4px; }.phase-strip span { flex:1; padding:9px 3px; background:var(--color-gray-100, #f3f6f3); text-align:center; font-size:11px; color:var(--color-gray-400, #8c9890); }.phase-strip .current { background:var(--brand-chatbi-soft, #edf8f1); color:var(--el-color-primary); font-weight:600; }.phase-strip .passed { color:var(--el-color-primary); border-bottom:2px solid var(--el-color-primary); }.detail-message { margin:0; font-size:13px; line-height:1.6; }.detail-metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; padding:18px; border:1px solid var(--color-gray-200, #e4e9e5); border-radius:8px; }.detail-metrics div { display:flex; flex-direction:column; gap:8px; }.detail-metrics span { font-size:12px; color:var(--color-gray-500, #758079); }.detail-metrics strong { font-size:21px; font-weight:600; font-variant-numeric:tabular-nums; }.progress-caption { font-size:12px; color:var(--color-gray-500, #758079); }
.event-list { padding:0 0 0 15px; margin:0; list-style:none; }.event-list li { position:relative; padding:0 0 22px 20px; border-left:1px solid var(--color-gray-200, #e4e9e5); }.event-list li::before { content:''; width:7px; height:7px; background:var(--el-color-primary); border-radius:50%; position:absolute; left:-4px; top:5px; }.event-list time { display:block; color:var(--color-gray-400, #8c9890); font-size:11px; margin-bottom:5px; }.event-list strong { font-size:12px; }.event-list p { margin:5px 0; font-size:13px; overflow-wrap:anywhere; line-height:1.6; }.event-list small { color:var(--color-gray-500, #758079); font-size:11px; }
.indeterminate-track { height:6px; background:var(--color-gray-100, #f3f6f3); border-radius:8px; overflow:hidden; }.indeterminate-track span { display:block; width:35%; height:100%; background:var(--el-color-primary); border-radius:8px; animation:sync-progress 2s ease-in-out infinite; } @keyframes sync-progress { from { transform:translateX(-100%); } to { transform:translateX(386%); } }
@media(max-width:1100px) { .task-grid { grid-template-columns:1fr; }.runs-heading { align-items:flex-start; flex-direction:column; }.sync-summary { flex-wrap:wrap; gap:10px 20px; }.refresh-note { margin-left:0; } }
@media(prefers-reduced-motion:reduce) { .indeterminate-track span, :deep(.el-progress-bar__inner) { animation:none !important; } }
</style>
