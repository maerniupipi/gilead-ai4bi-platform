import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { compileScript, parse } from 'vue/compiler-sfc'
import { transformWithEsbuild } from 'vite'
import * as vue from 'vue'
import * as icons from '../src/utils/agentAppIcon.js'

globalThis.document = { title: '' }
const copy = value => JSON.parse(JSON.stringify(value))
const workflow = { nodes: [{ id: 's', data: { kind: 'start' } }], edges: [] }
const payload = () => ({ format: 'chat-bi-agent-export', formatVersion: 1,
  app: { id: 999, name: '来源工作流' }, versionMeta: { name: 'v1', status: 'online' },
  workflow: copy(workflow), workflow_rev: 42, undo_stack: { states: [copy(workflow)], index: 0 } })

const utilitySource = await readFile(new URL('../src/utils/agentAppExport.js', import.meta.url), 'utf8')
const utilityCode = (await transformWithEsbuild(utilitySource, 'agentAppExport.js', { format: 'cjs' })).code
const utilityModule = { exports: {} }
new Function('require', 'module', 'exports', utilityCode)(() => icons, utilityModule, utilityModule.exports)
const utils = utilityModule.exports

const source = await readFile(new URL('../src/pages/agent-platform/AgentAppVersions.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const { code } = await transformWithEsbuild(compileScript(descriptor, { id: 'version-import' }).content, 'AgentAppVersions.js', { format: 'cjs' })

function createPage(overrides = {}) {
  const writes = [], notices = []
  const api = { createVersion: async (id, body) => {
    writes.push({ id, body: copy(body) })
    return { id, name: '目标工作流', versions: [
      { id: 2, name: body.name, status: 'designing', mode: '导入', is_output: false },
      { id: 1, name: 'v1', status: 'online', is_output: true }] }
  }, ...overrides }
  const modules = {
    vue: { ...vue, onMounted() {} },
    'vue-router': { useRouter: () => ({ push() {}, replace() {} }) },
    'element-plus': { ElMessage: Object.fromEntries(['success', 'warning', 'error'].map(type =>
      [type, message => notices.push({ type, message })])), ElMessageBox: {} },
    '@element-plus/icons-vue': {}, '@/api/agentApp': api, '@/utils/agentAppExport': utils
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(id => {
    assert.ok(Object.hasOwn(modules, id), `Unexpected import: ${id}`)
    return modules[id]
  }, module, module.exports)
  const scope = vue.effectScope()
  const page = scope.run(() => module.exports.default.setup({ appId: '7' }, { expose() {} }))
  page.app.value = { id: 7, name: '目标工作流', versions: [{ id: 1, name: 'v1', status: 'online', is_output: true }] }
  return { page, writes, notices, scope }
}

function eventFor(data, name = 'workflow.json') {
  return { target: { value: name, files: [{ name, text: async () => JSON.stringify(data) }] } }
}

test('parser supports exported packages, bare graphs and wrapped graphs', () => {
  for (const data of [payload(), workflow, { workflow }]) {
    assert.deepEqual(utils.parseImportPayload(JSON.stringify(data)).workflow, workflow)
  }
})

test('malformed exports cannot silently become empty imported versions', () => {
  for (const graph of [null, [], {}, { nodes: [], edges: 'bad' }, { nodes: [null], edges: [] }, { nodes: [], edges: [false] }]) {
    assert.throws(() => utils.parseImportPayload(JSON.stringify({ ...payload(), workflow: graph })))
  }
})

test('file selection proposes an unused version name and keeps source metadata for review', async () => {
  const f = createPage()
  const event = eventFor(payload())
  await f.page.onImportFile(event)
  assert.equal(event.target.value, '')
  assert.equal(f.page.importVisible.value, true)
  assert.equal(f.page.importFileName.value, 'workflow.json')
  assert.equal(f.page.importVersionName.value, 'v1-导入')
  assert.deepEqual(f.page.importPayload.value.workflow, workflow)
  assert.equal(f.writes.length, 0)
  f.scope.stop()
})

test('import uses one request for the selected workflow and keeps its old output version', async () => {
  const f = createPage()
  await f.page.onImportFile(eventFor(payload()))
  f.page.filterName.value = 'old-filter'
  f.page.filterStatus.value = 'online'
  await f.page.submitImportVersion()
  assert.deepEqual(f.writes, [{ id: 7, body: { name: 'v1-导入', workflow,
    undo_stack: payload().undo_stack } }])
  assert.equal(f.page.app.value.name, '目标工作流')
  assert.equal(f.page.app.value.versions.find(v => v.id === 1).is_output, true)
  assert.equal(f.page.importVisible.value, false)
  assert.equal(f.page.filterName.value, '')
  assert.equal(f.page.filterStatus.value, '')
  assert.equal(f.page.currentPage.value, 1)
  f.scope.stop()
})

test('invalid file or duplicate name sends no create request', async () => {
  const f = createPage()
  await f.page.onImportFile(eventFor({ ...payload(), workflow: null }))
  assert.equal(f.page.importVisible.value, false)
  assert.equal(f.notices.at(-1).type, 'error')
  await f.page.onImportFile(eventFor(payload()))
  f.page.importVersionName.value = 'v1'
  await f.page.submitImportVersion()
  assert.equal(f.writes.length, 0)
  assert.equal(f.page.importVisible.value, true)
  assert.match(f.notices.at(-1).message, /已存在/)
  f.scope.stop()
})

test('request failure keeps the file and name ready to retry; concurrent submits are ignored', async () => {
  let fail = true, finish
  const writes = []
  const f = createPage({ createVersion: async (id, body) => {
    writes.push(copy(body))
    await new Promise(resolve => { finish = resolve })
    if (fail) throw new Error('保存失败')
    return { id, name: '目标工作流', versions: [{ id: 2, name: body.name }] }
  } })
  await f.page.onImportFile(eventFor(payload()))
  const request = f.page.submitImportVersion()
  await f.page.submitImportVersion()
  assert.equal(writes.length, 1)
  finish()
  await request
  assert.equal(f.page.importVisible.value, true)
  assert.equal(f.page.importVersionName.value, 'v1-导入')
  assert.deepEqual(f.page.importPayload.value.workflow, workflow)
  assert.equal(f.page.importSubmitting.value, false)
  fail = false
  const retry = f.page.submitImportVersion()
  finish()
  await retry
  assert.equal(f.page.importVisible.value, false)
  f.scope.stop()
})

test('suggested names remain within the version name limit after repeated imports', () => {
  const value = payload()
  value.versionMeta.name = '长'.repeat(64)
  const names = [{ name: value.versionMeta.name }]
  for (let i = 0; i < 3; i++) {
    const name = utils.suggestImportVersionName(value, names)
    assert.ok(name.length <= 64)
    assert.ok(!names.some(v => v.name === name))
    names.push({ name })
  }
})
