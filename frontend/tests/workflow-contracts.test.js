import test from 'node:test'
import assert from 'node:assert/strict'
import { nodeOutputOptions, isValidScriptInputName, typedConstant, renameNodeReferences, buildDebugInputs, nodeConfigurationIssues, workflowOutputText } from '../src/pages/agent-platform/workflow/workflowContracts.js'
import { ATOMIC_CAPABILITIES, buildAtomicInputRows } from '../src/pages/agent-platform/workflow/atomicCapabilities.js'
import { consumeWorkflowStream } from '../src/api/workflowSse.js'

const node = (kind, config = {}) => ({ id: kind, data: { kind, label: kind, ...config } })

test('node output choices match runtime contracts for every node kind', () => {
  const cases = [
    [node('start'), []],
    [node('userInput', { fields: [{ variable: 'question' }] }), ['userInput.question']],
    [node('llm', { llm_config: { output_params: [{ variable: 'invented' }] } }), ['llm.text']],
    [node('script', { script_config: { output_vars: [{ name: 'count' }] } }), ['script.count']],
    [node('lab', { lab_config: { output_vars: ['trace_id'] } }), ['lab.trace_id']],
    [node('lab'), ['lab.trace_id', 'lab.summary', 'lab.sql', 'lab.error']],
    [node('lab', { lab_config: { output_vars: ['summary', 'sql'] } }), ['lab.summary', 'lab.sql']],
    [node('atomic'), ['atomic.results']],
    [node('agent'), ['agent.output', 'agent.content']],
    [node('externalApi'), ['externalApi.status_code', 'externalApi.response_body']],
    [node('selector'), ['selector.branch_handle', 'selector.matched']],
    [node('output'), ['output.content', 'output.metadata']]
  ]
  for (const [item, expected] of cases) assert.deepEqual(nodeOutputOptions(item, [{ key: 'results' }]).map(o => o.value), expected)
})

test('typed constants preserve false/zero and reject wrong JSON shapes', () => {
  assert.equal(typedConstant('false', 'boolean'), false)
  assert.equal(typedConstant('0', 'number'), 0)
  assert.deepEqual(typedConstant('{"x":0}', 'object'), { x: 0 })
  assert.deepEqual(typedConstant('[true,false]', 'LIST<Boolean>'), [true, false])
  assert.throws(() => typedConstant('yes', 'boolean'))
  assert.throws(() => typedConstant('', 'number'))
  assert.throws(() => typedConstant('[1]', 'object'))
  assert.throws(() => typedConstant('["1"]', 'array_number'))
})

test('rename changes references and templates but preserves code, constants and other node names', () => {
  const original = node('script', { script_config: { input_vars: [{ ref: '旧节点.result' }, { source_mode: 'const', const_value: '旧节点.result' }, { ref: '旧节点2.result' }], code: 'return {"x": "旧节点.result"}' }, llm_config: { system_prompt: '值 {{ 旧节点.result }}', context_vars: ['旧节点.result'] }, api_config: { headers: [{ key: 'value', value: '{{旧节点.token}}' }] } })
  const updated = renameNodeReferences([original], '旧节点', '新节点')[0]
  assert.equal(updated.data.script_config.input_vars[0].ref, '新节点.result')
  assert.equal(updated.data.script_config.input_vars[1].const_value, '旧节点.result')
  assert.equal(updated.data.script_config.input_vars[2].ref, '旧节点2.result')
  assert.equal(updated.data.script_config.code, original.data.script_config.code)
  assert.equal(updated.data.llm_config.system_prompt, '值 {{新节点.result}}')
  assert.deepEqual(updated.data.llm_config.context_vars, ['新节点.result'])
  assert.equal(updated.data.api_config.headers[0].value, '{{新节点.token}}')
  assert.equal(original.data.script_config.input_vars[0].ref, '旧节点.result')
})

test('debug inputs use visible field, validate every required field and preserve defaults', () => {
  const nodes = [node('userInput', { fields: [{ variable: 'hidden', hidden: true, default: 'token' }, { variable: 'question', required: true, type: 'string' }, { variable: 'count', required: true, type: 'number', default: 0 }] })]
  assert.deepEqual(buildDebugInputs({ nodes, text: '你好' }), { question: '你好' })
  assert.deepEqual(buildDebugInputs({ nodes, jsonMode: true, json: '{"question":"你好","count":0}' }), { question: '你好', count: 0 })
  assert.throws(() => buildDebugInputs({ nodes, jsonMode: true, json: '{}' }), /question/)
  assert.throws(() => buildDebugInputs({ nodes, jsonMode: true, json: '[]' }), /对象/)
  assert.throws(() => buildDebugInputs({ nodes: [node('userInput', { fields: [{ variable: 'q', required: true }, { variable: 'other', required: true }] })], text: 'hello' }), /JSON/)
})

test('configuration issues report actionable missing config and duplicate output keys', () => {
  assert.match(nodeConfigurationIssues(node('llm'))[0], /模型/)
  assert.match(nodeConfigurationIssues(node('externalApi', { api_config: { base_url: 'example.com' } }))[0], /http/)
  assert.match(nodeConfigurationIssues(node('script', { script_config: { code: 'def main(): pass', output_vars: [{ name: 'x' }, { name: 'x' }] } }))[0], /重复/)
  assert.equal(workflowOutputText({ content: false }), 'false')
  assert.equal(workflowOutputText({ total: 0 }), '{\n  "total": 0\n}')
})

function stream(chunks) {
  return new ReadableStream({ start(controller) { chunks.forEach(chunk => controller.enqueue(new TextEncoder().encode(chunk))); controller.close() } })
}

test('SSE handles chunk boundaries, progress, empty output and final snapshots', async () => {
  const progress = [], output = []
  const result = await consumeWorkflowStream(stream(['data: {"node_id":"x","status":"runn', 'ing","input_snapshot":{"v":0}}\r\n\r\n', 'data:{"node_id":"x","status":"done","output":{"value":false}}\n\n', 'data: {"status":"done","output":"","steps":[]}']), { onNodeProgress: event => progress.push(event), onChunk: text => output.push(text) })
  assert.equal(progress.length, 2)
  assert.equal(progress[0].input_snapshot.v, 0)
  assert.equal(progress[1].output.value, false)
  assert.deepEqual(output, [''])
  assert.equal(result.status, 'done')
})

test('SSE surfaces server errors and unexpected disconnect instead of claiming success', async () => {
  const progress = []
  await assert.rejects(consumeWorkflowStream(stream(['data: {"node_id":"script","error":"脚本编译失败"}\n\n']), { onNodeProgress: e => progress.push(e) }), /脚本编译失败/)
  assert.equal(progress[0].status, 'error')
  await assert.rejects(consumeWorkflowStream(stream(['data: {"node_id":"x","status":"done"}\n\n'])), /未收到执行结果/)
})

test('renaming a dotted-prefix node does not retarget another longer node namespace', () => {
  const nodes = [node('script', { label: 'A' }), node('script', { label: 'A.B', script_config: { input_vars: [{ ref: 'A.B.value' }, { ref: 'A.value' }] } })]
  const changed = renameNodeReferences(nodes, 'A', 'New')
  assert.deepEqual(changed[1].data.script_config.input_vars.map(row => row.ref), ['A.B.value', 'New.value'])
})

test('SSE decoder preserves multibyte Chinese text split across byte chunks', async () => {
  const bytes = new TextEncoder().encode('data: {"status":"done","output":"中文测试"}\n\n')
  const body = new ReadableStream({ start(controller) { for (const byte of bytes) controller.enqueue(Uint8Array.of(byte)); controller.close() } })
  assert.equal((await consumeWorkflowStream(body)).output, '中文测试')
})


test('script parameter names match the restricted Python identifier rules without excluding Chinese', () => {
  for (const name of ['input', 'count2', 'user_name', '用户输入', '值2', 'match', 'case']) assert.equal(isValidScriptInputName(name), true, name)
  for (const name of ['', '_input', '__name__', '2count', 'class', 'for', 'True', 'None', 'async', 'user.name', 'a-b']) assert.equal(isValidScriptInputName(name), false, name)
  const issues = nodeConfigurationIssues(node('script', { script_config: { code: 'def main(): pass', input_vars: [{ name: 'class' }] } }))
  assert.match(issues.join(' '), /Python 关键字/)
})


test('atomic capabilities expose required fields and validate typed constants without rejecting optional blanks/nulls', () => {
  const make = (capability, values = {}) => node('atomic', { atomic_config: { capability, input_vars: buildAtomicInputRows(capability).map(row => ({ ...row, const_value: Object.hasOwn(values, row.key) ? values[row.key] : row.const_value })) } })
  const empty = nodeConfigurationIssues(make('elasticsearch-value-retriever'))
  assert.match(empty.join(' '), /知识库/)
  assert.match(empty.join(' '), /查询内容/)
  assert.doesNotMatch(empty.join(' '), /分数阈值/)
  assert.deepEqual(nodeConfigurationIssues(make('generate-sql', { query: '统计销量', provider_id: '1', model_name: 'model' })), [])
  assert.match(nodeConfigurationIssues(make('generate-sql', { knowledge_base_id: 'null', query: '统计销量', provider_id: '1', model_name: 'model' })).join(' '), /知识库/)
  assert.match(nodeConfigurationIssues(make('execute-sql', { knowledge_base_id: '1' })).join(' '), /SQL/)
  assert.deepEqual(nodeConfigurationIssues(make('ner-retriever', { knowledge_base_id: '1', entity: '["上海"]' })), [])
  assert.match(nodeConfigurationIssues(make('ner-retriever', { knowledge_base_id: '1' })).join(' '), /实体列表/)
  assert.match(nodeConfigurationIssues(make('multi-global-value-meta-retriever', { knowledge_base_id: '1', query: '销量' })).join(' '), /列表项/)
  for (const value of ['abc', '1.5', '0', '201']) assert.match(nodeConfigurationIssues(make('elasticsearch-value-retriever', { knowledge_base_id: '1', query: '销量', top_k: value })).join(' '), /返回条数/)
})

test('switching atomic capability retains only compatible inputs and canonical outputs', () => {
  const old = buildAtomicInputRows('elasticsearch-value-retriever').map(row => ({ ...row, const_value: row.key === 'query' ? '保留的问题' : row.const_value }))
  const next = buildAtomicInputRows('generate-sql', old)
  assert.equal(next.find(row => row.key === 'query').const_value, '保留的问题')
  assert.equal(next.some(row => ['top_k', 'score_threshold'].includes(row.key)), false)
  assert.deepEqual(ATOMIC_CAPABILITIES.find(item => item.value === 'generate-sql').outputs.map(row => row.key), ['sql', 'content', 'prompt_preview'])
  const multi = buildAtomicInputRows('multi-global-value-meta-retriever', [{ key: 'table_name', type: 'STRING', const_value: 'table.column' }])
  assert.equal(multi.find(row => row.key === 'table_name').const_value, '[]')
})
