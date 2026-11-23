<template>
  <el-dialog :model-value="modelValue" width="min(1240px, 96vw)" top="4vh" class="data-query-dialog" @update:model-value="$emit('update:modelValue', $event)">
    <template #header><div class="query-heading"><span class="query-icon">SQL</span><div><strong>数据查询</strong><p>{{ source?.name }} · {{ source?.database_type }}</p></div></div></template>
    <div class="connection-bar">
      <label>数据库<el-select v-model="database" filterable allow-create default-first-option :loading="catalogLoading" @change="loadCatalog"><el-option v-for="name in databases" :key="name" :label="name" :value="name" /></el-select></label>
      <label v-if="source?.database_type !== 'mysql'">Schema<el-select v-model="schema" clearable filterable allow-create default-first-option><el-option v-for="name in schemas" :key="name" :label="name" :value="name" /></el-select></label>
      <span class="query-hint">默认 LIMIT 100 · 支持只读 SQL</span>
    </div>
    <el-alert v-if="catalogError" :title="catalogError" type="warning" :closable="false" show-icon class="query-alert" />
    <div class="editor-heading"><span>SQL 编辑器</span><span>选中语句优先执行 · Ctrl / ⌘ + Enter</span></div>
    <el-input ref="editor" v-model="sql" type="textarea" :rows="8" resize="vertical" spellcheck="false" aria-label="SQL 查询语句" placeholder="SELECT * FROM your_table" @keydown.ctrl.enter.prevent="execute" @keydown.meta.enter.prevent="execute" />
    <div class="execute-bar"><el-button type="primary" :icon="CaretRight" :loading="running" :disabled="!sql.trim() || !database" @click="execute">执行查询</el-button><el-button :disabled="!sql" @click="copy(sql)">复制 SQL</el-button><span>允许查询和查看执行计划，禁止数据与表结构的增删改。</span></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="query-alert" />
    <section v-if="result" class="query-results">
      <div class="result-heading"><strong>查询结果 <el-tag size="small" type="info">{{ result.row_count }} 行</el-tag></strong><span>{{ result.elapsed_ms }} ms <el-button link type="primary" @click="copyRows">复制结果</el-button></span></div>
      <p v-if="result.default_limit_applied || result.truncated" class="limit-note">{{ result.truncated ? '结果超过本次展示上限，已截取。' : '本次 SQL 已自动补充 LIMIT 100。' }}</p>
      <el-table :data="result.rows" border stripe max-height="360" size="small" empty-text="查询成功，没有符合条件的数据">
        <el-table-column v-for="column in result.columns" :key="column.key" :prop="column.key" :label="column.name" min-width="150" show-overflow-tooltip><template #default="{ row }"><span :class="{ 'null-value': row[column.key] == null }">{{ cell(row[column.key]) }}</span></template></el-table-column>
      </el-table>
      <el-collapse class="executed-sql"><el-collapse-item title="实际执行 SQL" name="sql"><pre>{{ result.sql }}</pre></el-collapse-item></el-collapse>
    </section>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CaretRight } from '@element-plus/icons-vue'
import dataSourceApi from '@/api/dataSource'
const props = defineProps({ modelValue: Boolean, source: Object })
defineEmits(['update:modelValue'])
const database = ref(''), schema = ref('public'), databases = ref([]), schemas = ref([])
const sql = ref(''), editor = ref(), result = ref(null), error = ref(''), catalogError = ref('')
const running = ref(false), catalogLoading = ref(false)
let serial = 0, catalogSerial = 0
const cell = value => value == null ? 'NULL' : typeof value === 'object' ? JSON.stringify(value) : String(value)
watch(() => [props.modelValue, props.source?.id], () => {
  serial++; catalogSerial++; running.value = false
  if (props.modelValue && props.source) {
    database.value = props.source.default_database || ''
    databases.value = database.value ? [database.value] : []
    schema.value = props.source.database_type === 'mysql' ? '' : 'public'
    schemas.value = []; result.value = null; error.value = ''; catalogError.value = ''; sql.value = ''
    loadCatalog()
  }
})
async function loadCatalog() {
  const current = ++catalogSerial
  catalogLoading.value = true; catalogError.value = ''
  try {
    const data = await dataSourceApi.queryCatalog(props.source.id, database.value)
    if (current !== catalogSerial) return
    databases.value = [...new Set([database.value, ...data.databases].filter(Boolean))]
    schemas.value = data.schemas
    if (schemas.value.length && !schemas.value.includes(schema.value)) schema.value = schemas.value[0]
  } catch (failure) { if (current === catalogSerial) catalogError.value = '未能列出库和 Schema，可直接输入名称后查询：' + failure.message }
  finally { if (current === catalogSerial) catalogLoading.value = false }
}
async function execute() {
  if (running.value || !sql.value.trim() || !database.value) return
  const area = editor.value?.textarea
  const selected = area && area.selectionEnd > area.selectionStart ? sql.value.slice(area.selectionStart, area.selectionEnd) : sql.value
  const current = ++serial
  running.value = true; error.value = ''; result.value = null
  try {
    const data = await dataSourceApi.query(props.source.id, { sql: selected, database: database.value, schema_name: schema.value || null })
    if (current === serial) result.value = data
  } catch (failure) { if (current === serial) error.value = failure.message || '查询失败' }
  finally { if (current === serial) running.value = false }
}
async function copy(value) {
  try { await navigator.clipboard.writeText(value); ElMessage.success('已复制') }
  catch { ElMessage.warning('复制失败，请手动选择内容复制') }
}
function copyRows() {
  const data = result.value
  copy([data.columns.map(c => c.name).join('\t'), ...data.rows.map(row => data.columns.map(c => cell(row[c.key])).join('\t'))].join('\n'))
}
</script>

<style scoped>
.query-heading { display:flex; align-items:center; gap:14px; }.query-heading strong { font-size:19px; }.query-heading p { margin:5px 0 0; color:#83909e; font-size:12px; }.query-icon { font:600 13px/44px ui-monospace,monospace; width:50px; text-align:center; border-radius:9px; color:var(--brand-primary,#06a9b9); background:#e7f8fa; }
.connection-bar { display:flex; align-items:center; gap:20px; flex-wrap:wrap; padding:16px 18px; background:#f6f8fa; border:1px solid #e9edf1; border-radius:8px; margin-bottom:20px; }.connection-bar label { display:flex; align-items:center; gap:10px; font-size:13px; }.connection-bar .el-select { width:240px; }.query-hint { margin-left:auto; color:#81909e; font-size:12px; }
.editor-heading,.result-heading { display:flex; align-items:center; justify-content:space-between; margin:14px 0 10px; }.editor-heading { font-weight:600; font-size:13px; }.editor-heading span:last-child { font-weight:400; color:#95a0ac; font-size:12px; }
:deep(.el-textarea__inner) { font:14px/1.75 ui-monospace,SFMono-Regular,Consolas,monospace; padding:15px 18px; background:#fafcfd; tab-size:2; }
.execute-bar { display:flex; align-items:center; flex-wrap:wrap; gap:8px; margin:14px 0 22px; }.execute-bar > span { margin-left:auto; color:#94a0ac; font-size:12px; }.query-alert { margin:12px 0; }.query-results { border-top:1px solid #e7edf2; padding-top:8px; }.result-heading > span { color:#7e8d9b; font-size:12px; }.result-heading .el-tag { margin-left:8px; }.limit-note { font-size:12px; color:#9a792b; }.null-value { color:#a5adb8; font-style:italic; }.executed-sql { margin-top:12px; }.executed-sql pre { white-space:pre-wrap; overflow-wrap:anywhere; font:12px/1.7 ui-monospace,monospace; }
@media(max-width:700px) { .connection-bar .el-select { width:190px; }.query-hint,.execute-bar > span { margin-left:0; }.editor-heading { align-items:flex-start; flex-direction:column; gap:6px; } }
</style>
