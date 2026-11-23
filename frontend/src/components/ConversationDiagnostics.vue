<template>
  <div class="turn-diagnostics">
    <div class="diagnostic-heading"><strong>请求与执行诊断</strong><el-button link type="primary" @click="openLogs()">查看关联日志</el-button></div>
    <el-empty v-if="!data" description="此轮为历史记录，尚未采集请求与执行参数" :image-size="55" />
    <template v-else>
      <div class="diagnostic-identifiers"><span>Request ID <code>{{ data.request_id || '未采集' }}</code></span><span>Task ID <code>{{ taskId }}</code></span></div>
      <el-collapse>
        <el-collapse-item title="1. 调用接口的原始传递参数" name="request"><div class="json-tools"><el-button link type="primary" @click="copy(data.request)">复制原始请求</el-button></div><pre>{{ pretty(data.request) }}</pre></el-collapse-item>
        <el-collapse-item title="2. 调用智能体时传递的实际参数" name="inputs">
          <p class="diagnostic-note">默认按调用展示去重后的参数；兼容别名、原始完整参数可展开查看。相同根调用的入口采集与工作流采集合并展示。</p>
          <el-empty v-if="!calls.length" description="尚未调用智能体，或本轮未采集到调用参数" :image-size="50" />
          <section v-for="(call,index) in calls" :key="call.id" class="invocation">
            <div class="invocation-title"><strong>{{ index+1 }} · {{ callLabel(call.kind) }}</strong><span>{{ targetLabel(call) }}</span><el-button link type="primary" @click="copy(call.inputs)">复制完整入参</el-button></div>
            <p v-if="call.trace_id" class="diagnostic-note">TraceID <code>{{ call.trace_id }}</code></p>
            <pre>{{ pretty(call.compact.values) }}</pre>
            <details v-if="Object.keys(call.compact.compatibilityContext).length"><summary>兼容历史上下文</summary><pre>{{ pretty(call.compact.compatibilityContext) }}</pre></details>
            <template v-if="call.input_usage">
              <el-table :data="call.input_usage.fields.filter(row=>row.status!=='possible_context')" size="small" border empty-text="未发现直接引用的入口字段">
                <el-table-column prop="name" label="参数" min-width="120" />
                <el-table-column label="使用情况" min-width="125"><template #default="{row}">{{ inputUseLabel(row.status) }}</template></el-table-column>
                <el-table-column label="使用节点" min-width="190"><template #default="{row}">{{ [...new Set([...row.declared_by,...row.referenced_by])].join('、') }}</template></el-table-column>
              </el-table>
              <details><summary>可能由脚本、上下文或下游使用的字段</summary><p class="diagnostic-note">{{ call.input_usage.note }}</p><div class="context-fields"><el-tag v-for="row in call.input_usage.fields.filter(row=>row.status==='possible_context')" :key="row.name" type="info" size="small">{{ row.name }}</el-tag></div></details>
            </template>
            <p v-else class="diagnostic-note">此调用尚未采集画布引用分析；不能据此判断字段未使用。</p>
            <details v-if="call.compact.aliases.length"><summary>重复值及兼容别名（{{ call.compact.aliases.length }}）</summary><ul><li v-for="alias in call.compact.aliases" :key="alias.field"><code>{{ alias.field }}</code> → {{ alias.same_as }}</li></ul></details>
            <details><summary>原始完整调用 JSON</summary><pre>{{ pretty(rawCall(call.id)) }}</pre></details>
          </section>
        </el-collapse-item>
        <el-collapse-item title="3. 智能体与实验室 TraceID" name="traces">
          <el-table :data="data.traces || []" size="small" border empty-text="尚未生成 TraceID">
            <el-table-column label="类型" width="95"><template #default="{row}">{{ row.kind==='lab'?'实验室':'智能体' }}</template></el-table-column>
            <el-table-column prop="trace_id" label="TraceID" min-width="290"><template #default="{row}"><el-button link type="primary" @click="openTrace(row)">{{ row.trace_id }}</el-button><el-button link type="primary" @click="copy(row.trace_id)">复制</el-button></template></el-table-column>
            <el-table-column prop="parent_trace_id" label="父 TraceID" min-width="250" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column label="日志" width="75"><template #default="{row}"><el-button link type="primary" @click="openLogs(row.trace_id)">查看</el-button></template></el-table-column>
          </el-table>
        </el-collapse-item>
        <el-collapse-item :title="`模型调用与耗时（${modelCalls.length} 次）`" name="models">
          <p class="diagnostic-note">总结等呈现调用使用流式，中间调用使用非流式；非流式不提供首分片或首段正文时间。供应商未返回 token 用量时显示未返回。</p>
          <el-table :data="modelCalls" size="small" border empty-text="尚未采集模型调用耗时">
            <el-table-column type="expand"><template #default="{row}"><pre>{{ pretty(row) }}</pre></template></el-table-column>
            <el-table-column label="模型 / 节点" min-width="160"><template #default="{row}">{{ row.model }}<div class="diagnostic-note">{{ row.node_label || row.stage || row.operation }}</div></template></el-table-column>
            <el-table-column label="模式" width="80"><template #default="{row}">{{ row.stream ? '流式' : '非流式' }}</template></el-table-column>
            <el-table-column label="首分片" min-width="85"><template #default="{row}">{{ millis(row.first_chunk_ms) }}</template></el-table-column>
            <el-table-column label="首段正文" min-width="95"><template #default="{row}">{{ millis(row.first_content_ms) }}</template></el-table-column>
            <el-table-column label="总耗时" min-width="85"><template #default="{row}">{{ millis(row.elapsed_ms) }}</template></el-table-column>
            <el-table-column prop="chunk_count" label="分片" width="65" />
            <el-table-column label="Tokens" min-width="85"><template #default="{row}">{{ row.token_usage?.total_tokens ?? '未返回' }}</template></el-table-column>
            <el-table-column prop="status" label="状态" width="90" />
          </el-table>
          <details><summary>模型原始请求（{{ modelRequests.length }} 次）</summary><section v-for="call in modelRequests" :key="call.id"><div class="json-tools"><el-button link type="primary" @click="copy(call)">复制模型请求</el-button></div><pre>{{ pretty(call) }}</pre></section></details>
        </el-collapse-item>
        <el-collapse-item title="执行版本、权限、耗时与失败信息" name="execution"><div class="json-tools"><el-button link type="primary" @click="copy(data.execution)">复制完整执行信息</el-button></div><pre>{{ pretty(executionSummary) }}</pre></el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { analysisCalls, inputUseLabel } from './conversationDiagnosticView'
const props=defineProps({data:Object,messageId:String,conversationId:String,taskId:String})
const router=useRouter()
const calls=computed(()=>analysisCalls(props.data?.invocations))
const modelCalls=computed(()=>props.data?.execution?.model_calls || [])
const modelRequests=computed(()=>(props.data?.invocations || []).filter(call=>call.kind==='model'))
const executionSummary=computed(()=>{const {model_calls,...rest}=props.data?.execution || {};return rest})
const pretty=value=>JSON.stringify(value,null,2)
const millis=value=>typeof value==='number'?`${value} ms`:'未采集'
const callLabel=value=>({agent:'智能体入口',workflow:'工作流调用',nested_agent:'嵌套智能体',lab:'实验室调用'})[value] || value
const targetLabel=call=>[call.app_id?`工作流 #${call.app_id}`:call.project_id?`实验室 #${call.project_id}`:'',call.version_id?`版本 #${call.version_id}`:''].filter(Boolean).join(' · ')
const rawCall=id=>(props.data?.invocations || []).find(call=>call.id===id)
function openLogs(traceId) { router.push({path:'/management/system-logs',query:{message_id:props.messageId,conversation_id:props.conversationId,...(traceId?{trace_id:traceId}:{})}}) }
function openTrace(row) { router.push(row.kind==='lab' ? '/autobi/lab/trace/'+row.trace_id : '/agent-platform/traces/'+row.trace_id) }
async function copy(value) { try { await navigator.clipboard.writeText(typeof value==='string'?value:pretty(value)); ElMessage.success('已复制') } catch { ElMessage.warning('复制失败，请手动复制') } }
</script>
<style scoped>
.turn-diagnostics { margin:0 20px 20px; padding-top:16px; border-top:1px solid #e9edf2; }.diagnostic-heading,.invocation-title,.json-tools { display:flex; align-items:center; justify-content:space-between; gap:12px; }.diagnostic-heading { margin-bottom:12px; font-size:13px; color:#4e6074; }.diagnostic-identifiers { display:flex; flex-wrap:wrap; gap:8px 22px; font-size:11px; color:#8995a2; margin-bottom:10px; }code { color:#64758a; font:11px/1.7 ui-monospace,monospace; overflow-wrap:anywhere; }.diagnostic-identifiers code { margin-left:6px; }.invocation { margin:10px 0 22px; border-bottom:1px solid #e9edf2; padding-bottom:12px; }.invocation-title { justify-content:flex-start; font-size:12px; }.invocation-title > span { flex:1; color:#8c99a5; overflow-wrap:anywhere; }.json-tools { justify-content:flex-end; }.diagnostic-note { color:#7c899a; font-size:12px; line-height:1.7; }.context-fields { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }details { margin-top:10px; font-size:12px; }summary { cursor:pointer; color:#537188; }li { line-height:1.9; }pre { max-height:440px; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; background:#f6f8fa; border:1px solid #e9edf1; padding:14px; border-radius:6px; color:#384b61; font:12px/1.75 ui-monospace,monospace; }
</style>
