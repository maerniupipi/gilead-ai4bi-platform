import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { compileScript, parse } from 'vue/compiler-sfc'
import { transformWithEsbuild } from 'vite'
import * as vue from 'vue'
import * as contracts from '../src/pages/agent-platform/workflow/workflowContracts.js'
import * as atomic from '../src/pages/agent-platform/workflow/atomicCapabilities.js'
import * as helpers from '../src/pages/agent-platform/workflow/workflowPersistence.js'

globalThis.document = { activeElement: null, title: '' }
globalThis.HTMLElement = class {}

const copy = value => JSON.parse(JSON.stringify(value))
const graph = () => ({
  nodes: [{ id: 'start', type: 'wfCard', position: { x: 0, y: 0 }, data: { kind: 'start', label: '开始' } },
    { id: 'output', type: 'wfCard', position: { x: 300, y: 0 }, data: { kind: 'output', label: '输出', description: '', output_config: { content_template: 'original' } } }],
  edges: [{ id: 'edge', type: 'wfPlus', source: 'start', target: 'output' }]
})
function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
const conflict = () => Object.assign(new Error('版本已变更'), { code: 'DUPLICATE' })

const source = await readFile(new URL('../src/pages/agent-platform/workflow/AgentWorkflowDesign.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const { code } = await transformWithEsbuild(compileScript(descriptor, { id: 'workflow-editor-state' }).content, 'WorkflowDesign.js', { format: 'cjs' })

function createPage(overrides = {}) {
  let remote = { workflow: graph(), workflow_rev: 1, undo_stack: null }
  const writes = [], notices = [], guards = []
  const api = {
    getWorkflow: async () => copy(remote),
    putWorkflow: async (appId, versionId, body) => {
      writes.push(copy(body))
      if (body.expected_rev !== remote.workflow_rev) throw conflict()
      remote = { workflow: { nodes: copy(body.nodes), edges: copy(body.edges) }, workflow_rev: remote.workflow_rev + 1 }
      return copy(remote)
    },
    ...overrides
  }
  const modules = {
    vue: { ...vue, onMounted() {}, onUnmounted() {}, provide() {} },
    'vue-router': { useRoute: () => ({ query: {} }), useRouter: () => ({}), onBeforeRouteLeave: guard => guards.push(guard), onBeforeRouteUpdate() {} },
    '@vue-flow/core': { useVueFlow: () => ({ fitView: async () => true, dimensions: vue.ref({ width: 0, height: 0 }) }), useNodesInitialized: () => vue.ref(false) },
    '@vue-flow/background': {}, '@vue-flow/controls': {}, '@vue-flow/minimap': {},
    'element-plus': { ElMessage: Object.fromEntries(['success', 'warning', 'error'].map(type => [type, message => notices.push({ type, message })])), ElMessageBox: {} },
    '@element-plus/icons-vue': {}, '@/api/agentApp': api,
    '@/api/modelProvider': { getModelProviders: async () => [] }, '@/api/autobi': {}, '@/api/knowledgeBase': {},
    './atomicCapabilities.js': atomic, './workflowContracts.js': contracts, './workflowPersistence.js': helpers
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(id => {
    if (id.endsWith('.vue') || id.endsWith('.css')) return {}
    assert.ok(Object.hasOwn(modules, id), `Unexpected import: ${id}`)
    return modules[id]
  }, module, module.exports)
  const scope = vue.effectScope()
  const page = scope.run(() => module.exports.default.setup({ appId: '1', versionId: '1' }, { expose() {} }))
  page.app.value = { versions: [{ id: 1, status: 'designing' }] }
  page.loading.value = false
  page.suppressSave.value = false
  page.applyWorkflowResponse(copy(remote))
  const edit = (value, field = 'content_template') => {
    if (field === 'description') page.nodes.value[1].data.description = value
    else page.nodes.value[1].data.output_config[field] = value
    page.hasUnsavedChanges.value = true
  }
  return { page, writes, notices, guards, edit, scope, setRemote(value) { remote = copy(value) }, getRemote: () => copy(remote) }
}

test('rapid edits and concurrent save requests serialize and retain the newest edit', async () => {
  const first = deferred()
  const writes = []
  const fixture = createPage({ putWorkflow: async (id, vid, body) => {
    writes.push(copy(body))
    if (writes.length === 1) await first.promise
    return { workflow: { nodes: body.nodes, edges: body.edges }, workflow_rev: body.expected_rev + 1 }
  } })
  fixture.edit('first')
  const save = fixture.page.persistWorkflow()
  fixture.edit('newest')
  const second = fixture.page.persistWorkflow()
  assert.equal(writes.length, 1)
  first.resolve()
  assert.deepEqual(await Promise.all([save, second]), [true, true])
  assert.deepEqual(writes.map(w => w.expected_rev), [1, 2])
  assert.equal(writes[1].nodes[1].data.output_config.content_template, 'newest')
  assert.equal(fixture.page.hasUnsavedChanges.value, false)
  fixture.scope.stop()
})

test('selection and measured dimensions do not cause another revision while saving', async () => {
  const first = deferred()
  const fixture = createPage({ putWorkflow: async (id, vid, body) => {
    fixture.writes.push(copy(body))
    await first.promise
    return { workflow: { nodes: body.nodes, edges: body.edges }, workflow_rev: body.expected_rev + 1 }
  } })
  fixture.edit('saved')
  const save = fixture.page.persistWorkflow()
  Object.assign(fixture.page.nodes.value[1], { selected: true, dimensions: { width: 250, height: 70 }, computedPosition: { x: 300, y: 0, z: 1000 } })
  first.resolve()
  assert.equal(await save, true)
  assert.equal(fixture.writes.length, 1)
  assert.equal('selected' in fixture.writes[0].nodes[1], false)
  fixture.scope.stop()
})

test('blurring an unchanged editor after load does not create a dirty history entry', () => {
  const fixture = createPage()
  fixture.page.pushHistory()
  assert.equal(fixture.page.hasUnsavedChanges.value, false)
  assert.equal(fixture.page.canUndo.value, false)
  fixture.scope.stop()
})

test('editing a lab with a query mapping preserves its binding and exposes SQL', async () => {
  const fixture = createPage()
  fixture.page.nodes.value.push({ id: 'lab', data: { kind: 'lab', label: '实验室', lab_config: {
    project_id: 1, input_mapping: [{ target_field: 'query', source_mode: 'ref', source_ref: '输出.content' }]
  } } })
  fixture.page.selectedNodeId.value = 'lab'
  await vue.nextTick()
  assert.equal(fixture.page.labContentMode.value, 'ref')
  assert.equal(fixture.page.labContentRef.value, '输出.content')
  assert.ok(fixture.page.labOutputVars.value.includes('sql'))
  fixture.page.commitLabConfig()
  const config = fixture.page.nodes.value.find(node => node.id === 'lab').data.lab_config
  assert.equal(config.input_mapping[0].source_ref, '输出.content')
  assert.ok(config.output_vars.includes('sql'))
  fixture.scope.stop()
})

for (const kind of ['lab', 'agent']) {
  test(`${kind} SSE progress and result switches save independently and reload`, async () => {
    const fixture = createPage()
    const configKey = `${kind}_config`
    const commit = kind === 'lab' ? 'commitLabConfig' : 'commitAgentSseConfig'
    fixture.page.nodes.value.push({ id: kind, data: { kind, label: kind, [configKey]: {} } })
    fixture.page.selectedNodeId.value = kind
    await vue.nextTick()
    assert.equal(fixture.page[`${kind}SseOutputThoughts`].value, true)
    assert.equal(fixture.page[`${kind}SseOutputResults`].value, true)
    fixture.page[`${kind}SseOutputResults`].value = false
    fixture.page[commit]()
    let config = fixture.page.nodes.value.find(node => node.id === kind).data[configKey]
    assert.equal(config.sse_output_thoughts, true)
    assert.equal(config.sse_output_results, false)
    fixture.page.selectedNodeId.value = 'output'
    await vue.nextTick()
    fixture.page.selectedNodeId.value = kind
    await vue.nextTick()
    assert.equal(fixture.page[`${kind}SseOutputResults`].value, false)
    fixture.page[`${kind}SseOutputThoughts`].value = false
    fixture.page[commit]()
    config = fixture.page.nodes.value.find(node => node.id === kind).data[configKey]
    assert.equal(config.sse_output_thoughts, false)
    assert.equal(config.sse_output_results, false)
    fixture.scope.stop()
  })
}

test('a lost acknowledgement recovers automatically and saves later edits', async () => {
  const wait = deferred()
  const fixture = createPage({ putWorkflow: async (id, vid, body) => {
    fixture.writes.push(copy(body))
    if (fixture.writes.length === 1) {
      fixture.setRemote({ workflow: { nodes: body.nodes, edges: body.edges }, workflow_rev: 2 })
      await wait.promise
      throw conflict()
    }
    return { workflow: { nodes: body.nodes, edges: body.edges }, workflow_rev: body.expected_rev + 1 }
  } })
  fixture.edit('already committed')
  const save = fixture.page.persistWorkflow()
  fixture.edit('edited while awaiting acknowledgement')
  wait.resolve()
  assert.equal(await save, true)
  assert.equal(fixture.writes.at(-1).expected_rev, 2)
  assert.equal(fixture.writes.at(-1).nodes[1].data.output_config.content_template, 'edited while awaiting acknowledgement')
  assert.equal(fixture.notices.length, 0)
  fixture.scope.stop()
})

test('unrelated remote edits merge automatically without losing either change', async () => {
  const fixture = createPage()
  const remote = fixture.getRemote()
  remote.workflow_rev = 2
  remote.workflow.nodes[1].position.x = 600
  fixture.setRemote(remote)
  fixture.edit('local template')
  assert.equal(await fixture.page.persistWorkflow(), true)
  assert.equal(fixture.page.nodes.value[1].position.x, 600)
  assert.equal(fixture.getRemote().workflow.nodes[1].data.output_config.content_template, 'local template')
  assert.equal(fixture.notices.length, 0)
  fixture.scope.stop()
})

test('merging a remote node move does not reset a focused inspector draft', async () => {
  const fixture = createPage()
  fixture.page.selectedNodeId.value = 'output'
  await vue.nextTick()
  fixture.page.outputTemplateDraft.value = 'uncommitted typing'
  const remote = fixture.getRemote()
  remote.workflow_rev = 2
  remote.workflow.nodes[1].position.x = 600
  fixture.setRemote(remote)
  fixture.edit('local description', 'description')
  assert.equal(await fixture.page.persistWorkflow(), true)
  await vue.nextTick()
  assert.equal(fixture.page.outputTemplateDraft.value, 'uncommitted typing')
  fixture.scope.stop()
})

test('remote inspector updates wait until the focused field has committed its draft', async () => {
  const fixture = createPage()
  fixture.page.selectedNodeId.value = 'output'
  await vue.nextTick()
  fixture.page.outputTemplateDraft.value = 'pending template'
  fixture.edit('local position', 'description')
  const remote = fixture.getRemote()
  remote.workflow_rev = 2
  remote.workflow.nodes[1].data.label = 'remote label'
  fixture.setRemote(remote)
  const focused = new globalThis.HTMLElement()
  focused.closest = () => ({})
  document.activeElement = focused
  try {
    assert.equal(await fixture.page.persistWorkflow(), false)
    assert.equal(fixture.page.outputTemplateDraft.value, 'pending template')
    assert.equal(fixture.page.hasUnsavedChanges.value, true)
    assert.equal(fixture.notices.length, 0)
  } finally {
    document.activeElement = null
  }
  fixture.edit('pending template')
  assert.equal(await fixture.page.persistWorkflow(), true)
  assert.equal(fixture.getRemote().workflow.nodes[1].data.label, 'remote label')
  assert.equal(fixture.getRemote().workflow.nodes[1].data.output_config.content_template, 'pending template')
  fixture.scope.stop()
})

test('a true conflict keeps local work and the route guard does not discard it', async () => {
  const fixture = createPage()
  const remote = fixture.getRemote()
  remote.workflow_rev = 2
  remote.workflow.nodes[1].data.output_config.content_template = 'remote template'
  fixture.setRemote(remote)
  fixture.edit('local template')
  assert.equal(await fixture.guards[0](), false)
  assert.equal(fixture.page.nodes.value[1].data.output_config.content_template, 'local template')
  assert.equal(fixture.getRemote().workflow.nodes[1].data.output_config.content_template, 'remote template')
  assert.equal(fixture.page.hasUnsavedChanges.value, true)
  fixture.scope.stop()
})

test('matching undo history remains available, and unchanged graphs require no save', async () => {
  const fixture = createPage()
  const before = fixture.page.cloneState()
  fixture.edit('latest')
  const latest = fixture.page.cloneState()
  fixture.page.applyWorkflowResponse({ workflow: latest, workflow_rev: 5, undo_stack: { states: [before, latest], index: 1 } })
  assert.equal(fixture.page.canUndo.value, true)
  fixture.page.hasUnsavedChanges.value = true
  assert.equal(await fixture.page.persistWorkflow(), true)
  assert.equal(fixture.writes.length, 0)
  fixture.scope.stop()
})

test('persistent conflicts have bounded retries and cannot erase the local graph', async () => {
  const fixture = createPage({ putWorkflow: async () => { fixture.writes.push({}); throw conflict() } })
  fixture.edit('local')
  assert.equal(await fixture.page.persistWorkflow(), false)
  assert.equal(fixture.writes.length, 3)
  assert.equal(fixture.page.nodes.value[1].data.output_config.content_template, 'local')
  assert.equal(fixture.page.autosavePaused.value, true)
  fixture.scope.stop()
})

test('merge handles independent additions and rejects delete/edit or dangling edges', () => {
  const base = graph(), local = graph(), remote = graph()
  local.nodes.push({ id: 'local', data: { kind: 'script' } })
  remote.nodes.push({ id: 'remote', data: { kind: 'script' } })
  const merged = helpers.mergeWorkflows(base, local, remote)
  assert.deepEqual(merged.conflicts, [])
  assert.deepEqual(new Set(merged.workflow.nodes.map(n => n.id)), new Set(['start', 'output', 'local', 'remote']))
  const deleted = graph()
  deleted.nodes.pop()
  deleted.edges = []
  local.nodes[1].data.description = 'edited'
  assert.ok(helpers.mergeWorkflows(base, local, deleted).conflicts.length)
  const linked = graph()
  linked.edges.push({ id: 'new-edge', source: 'start', target: 'output' })
  assert.ok(helpers.mergeWorkflows(base, linked, deleted).conflicts.includes('edges.new-edge'))
  const sameLabel = graph()
  sameLabel.nodes[0].data.label = '输出'
  assert.ok(helpers.mergeWorkflows(base, graph(), sameLabel).conflicts.includes('nodes.output.data.label'))
})

test('stale undo history never replaces the current server graph on load', async () => {
  const fixture = createPage()
  const remote = fixture.getRemote()
  remote.workflow.nodes[1].data.output_config.content_template = 'latest on server'
  remote.undo_stack = { states: [graph()], index: 0 }
  fixture.page.applyWorkflowResponse(remote)
  await vue.nextTick()
  assert.equal(fixture.page.nodes.value[1].data.output_config.content_template, 'latest on server')
  assert.equal(fixture.page.history.value.at(-1).nodes[1].data.output_config.content_template, 'latest on server')
  fixture.scope.stop()
})
