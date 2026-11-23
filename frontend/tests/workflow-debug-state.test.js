import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { compileScript, parse } from 'vue/compiler-sfc'
import { transformWithEsbuild } from 'vite'
import * as vue from 'vue'
import * as contracts from '../src/pages/agent-platform/workflow/workflowContracts.js'

globalThis.document = { title: '' }
const source = await readFile(new URL('../src/pages/agent-platform/workflow/AgentWorkflowDebug.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const { code } = await transformWithEsbuild(compileScript(descriptor, { id: 'workflow-debug-state' }).content, 'WorkflowDebug.js', { format: 'cjs' })
const copy = value => JSON.parse(JSON.stringify(value))

function deferred() {
  let resolve
  const promise = new Promise(res => { resolve = res })
  return { promise, resolve }
}

function createDebugPage() {
  const hooks = { activated: [], deactivated: [], unmount: [] }
  const runs = [], notices = [], reads = []
  const result = deferred()
  let fieldName = 'question'
  const modules = {
    vue: { ...vue, onMounted() {}, onActivated: fn => hooks.activated.push(fn), onDeactivated: fn => hooks.deactivated.push(fn), onBeforeUnmount: fn => hooks.unmount.push(fn) },
    'vue-router': { useRoute: () => ({ query: {} }), useRouter: () => ({ replace() {} }) },
    'element-plus': { ElMessage: Object.fromEntries(['warning', 'error'].map(type => [type, text => notices.push({ type, text })])) },
    '@element-plus/icons-vue': {}, './workflowContracts.js': contracts,
    '@/api/agentApp': {
      getAgentApp: async () => ({ name: 'Test', versions: [{ id: 1, name: 'v1' }] }),
      getWorkflow: async () => {
        reads.push(fieldName)
        return { workflow: { nodes: [{ id: 'input', data: { kind: 'userInput', fields: [{ variable: fieldName, required: true }] } }], edges: [] } }
      },
      runWorkflowStream: async (appId, versionId, body, onChunk, onProgress, signal) => {
        runs.push({ body: copy(body), signal })
        onChunk('partial text')
        onProgress({ node_id: 'input', status: 'running', input_snapshot: body.inputs })
        if (runs.length === 1) return result.promise
        return { output: 'next result', steps: [] }
      }
    }
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(id => {
    assert.ok(Object.hasOwn(modules, id), `Unexpected import: ${id}`)
    return modules[id]
  }, module, module.exports)
  const scope = vue.effectScope()
  const page = scope.run(() => module.exports.default.setup({ appId: '1', versionId: '1' }, { expose() {} }))
  return { page, scope, hooks, result, runs, reads, notices, setField(value) { fieldName = value } }
}

test('tab deactivation and reactivation preserve a live stream, messages, drafts and logs', async () => {
  const fixture = createDebugPage()
  await fixture.page.load()
  fixture.hooks.activated[0]()
  fixture.page.streamMode.value = true
  fixture.page.draftText.value = 'first question'
  const run = fixture.page.send()
  fixture.page.draftText.value = 'unsent draft'
  fixture.page.draftJson.value = '{"keep":true}'
  fixture.hooks.deactivated[0]()
  fixture.hooks.activated[0]()
  assert.equal(fixture.runs[0].signal.aborted, false)
  assert.equal(fixture.page.runLoading.value, true)
  assert.equal(fixture.page.messages.value[1].content, 'partial text')
  assert.ok(fixture.page.logLines.value.length)
  fixture.result.resolve({ output: 'complete output', steps: [] })
  await run
  fixture.hooks.deactivated[0]()
  fixture.hooks.activated[0]()
  await vue.nextTick()
  assert.equal(fixture.page.messages.value[0].content, 'first question')
  assert.equal(fixture.page.messages.value[1].content, 'complete output')
  assert.equal(fixture.page.draftText.value, 'unsent draft')
  assert.equal(fixture.page.draftJson.value, '{"keep":true}')
  assert.equal(fixture.page.tracePayload.value.status, 'done')
  assert.ok(fixture.page.logLines.value.length)
  assert.equal(fixture.notices.length, 0)
  fixture.scope.stop()
})

test('the next send refreshes design changes made while the previous test was running', async () => {
  const fixture = createDebugPage()
  await fixture.page.load()
  fixture.hooks.activated[0]()
  fixture.page.streamMode.value = true
  fixture.page.draftText.value = 'old question'
  const run = fixture.page.send()
  fixture.hooks.deactivated[0]()
  fixture.setField('new_question')
  fixture.hooks.activated[0]()
  assert.deepEqual(fixture.reads, ['question'])
  fixture.result.resolve({ output: 'first result', steps: [] })
  await run
  fixture.page.draftText.value = 'new question'
  await fixture.page.send()
  assert.deepEqual(fixture.runs[1].body.inputs, { new_question: 'new question' })
  assert.equal(fixture.page.messages.value.length, 4)
  assert.equal(fixture.page.messages.value[1].content, 'first result')
  assert.equal(fixture.page.messages.value[3].content, 'next result')
  fixture.scope.stop()
})

test('explicitly clearing cancels streaming and ignores its late result', async () => {
  const fixture = createDebugPage()
  await fixture.page.load()
  fixture.page.streamMode.value = true
  fixture.page.draftText.value = 'question'
  const run = fixture.page.send()
  fixture.page.clearChat()
  assert.equal(fixture.runs[0].signal.aborted, true)
  fixture.result.resolve({ output: 'late output', steps: [] })
  await run
  assert.deepEqual(fixture.page.messages.value, [])
  assert.deepEqual(fixture.page.logLines.value, [])
  assert.deepEqual(fixture.page.traceStore.value, {})
  assert.equal(fixture.page.runLoading.value, false)
  fixture.scope.stop()
})

test('leaving the workflow workspace releases the active stream', async () => {
  const fixture = createDebugPage()
  await fixture.page.load()
  fixture.page.streamMode.value = true
  fixture.page.draftText.value = 'question'
  const run = fixture.page.send()
  fixture.hooks.unmount[0]()
  assert.equal(fixture.runs[0].signal.aborted, true)
  fixture.result.resolve({ output: 'late output', steps: [] })
  await run
  assert.notEqual(fixture.page.messages.value.at(-1)?.content, 'late output')
  fixture.scope.stop()
})
