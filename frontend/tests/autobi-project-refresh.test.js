import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { transformWithEsbuild } from 'vite'
import * as vue from 'vue'
import * as payload from '../src/utils/autobiPayload.js'
import * as prompts from '../src/utils/autobiDefaultPrompts.js'
import * as transfer from '../src/utils/autobiProjectExport.js'

// Exercise the page's actual setup handlers without a browser or a second test framework.
const source = await readFile(new URL('../src/pages/AutoBIList.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const script = compileScript(descriptor, { id: 'autobi-project-refresh' })
const { code } = await transformWithEsbuild(script.content, 'AutoBIList.js', { format: 'cjs' })

const copy = value => JSON.parse(JSON.stringify(value))

function project(id = 1, folderId = 10, prompt = 'original prompt') {
  return {
    id,
    name: `Project ${id}`,
    description: '',
    folder_id: folderId,
    knowledge_base_id: 20,
    config_json: {
      knowledge_base_id: 20,
      disclaimer_acceptance: { rewrite: true, sql: true, summary: true, chart: true },
      model_bindings: {
        nl2sql: { provider_id: 1, model_name: 'sql-model' },
        bi_summary: { provider_id: 1, model_name: 'summary-model' }
      },
      request: {
        messages: [{ role: 'user', content: 'keep this message' }],
        stream: true,
        advanced_config: {
          knowledge_rewrite_config: { enable: false },
          nl2sql_config: { prompt },
          chart_drawing_config: { enable: false },
          multi_rewrite_config: { enable: true, prompt: 'keep this hidden setting' }
        }
      }
    }
  }
}

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function createPage(overrides = {}, initialProjects = [project()]) {
  const stored = new Map(initialProjects.map(row => [row.id, copy(row)]))
  const messages = []
  const updates = []
  const reads = []
  const imports = []
  const exports = []
  const downloads = []
  const folderRows = [{ id: 10, name: 'First' }, { id: 11, name: 'Second' }]
  const api = {
    listAutobiFolders: async () => copy(folderRows),
    listAutobiProjects: async ({ folder_id }) => copy([...stored.values()].filter(row => row.folder_id === folder_id)),
    getAutobiProject: async id => { reads.push(id); return copy(stored.get(Number(id))) },
    updateAutobiProject: async (id, data) => {
      updates.push({ id, data: copy(data) })
      const row = { ...stored.get(Number(id)), ...copy(data) }
      stored.set(Number(id), row)
      return copy(row)
    },
    createAutobiProject: async data => {
      const row = { ...project(Math.max(...stored.keys(), 0) + 1), ...copy(data) }
      stored.set(row.id, row)
      return copy(row)
    },
    importAutobiProject: async data => {
      imports.push(copy(data))
      const row = { id: Math.max(...stored.keys(), 0) + 1, name: data.name, description: data.payload.project.description,
        folder_id: data.folder_id, knowledge_base_id: null,
        config_json: { ...copy(data.payload.config_json), knowledge_base_id: null, model_bindings: {} } }
      stored.set(row.id, row)
      return copy(row)
    },
    exportAutobiProject: async id => {
      exports.push(id)
      return labPayload(stored.get(id))
    },
    ...overrides
  }
  const modules = {
    vue: { ...vue, onMounted() {} },
    'element-plus': {
      ElMessage: Object.fromEntries(['success', 'warning', 'error'].map(type => [type, text => messages.push({ type, text })])),
      ElMessageBox: {}
    },
    '@element-plus/icons-vue': {},
    '../api/autobi': api,
    '../api/modelProvider': { getModelProviders: async () => [] },
    '../api/knowledgeBase': { getKnowledgeBaseList: async () => [] },
    '../api/agentApp': { listAgentApps: async () => [] },
    '../utils/autobiPayload': payload,
    '../utils/autobiProjectExport': transfer,
    '../utils/agentAppExport': {
      downloadJson: (filename, value) => downloads.push({ filename, value: copy(value) }),
      safeFilenamePart: name => name
    },
    '../utils/autobiDefaultPrompts': prompts
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(id => {
    if (id.endsWith('.vue')) return {}
    assert.ok(Object.hasOwn(modules, id), `Unexpected import: ${id}`)
    return modules[id]
  }, module, module.exports)
  const page = module.exports.default.setup({}, { expose() {} })
  page.folders.value = copy(folderRows)
  page.selectedFolderId.value = 10
  page.modelProviders.value = [{ id: 1, name: 'Test provider', models: 'sql-model,summary-model' }]
  page.knowledgeBaseList.value = [{ id: 20, name: 'Test knowledge base' }]
  page.agentApps.value = [{ id: 1, versions: [] }]
  return { page, stored, messages, updates, reads, imports, exports, downloads }
}

function labPayload(row = project()) {
  return { format: 'chat-bi-lab-export', formatVersion: 1,
    project: { name: row.name, description: row.description }, config_json: copy(row.config_json) }
}

function fileEvent(value, name = 'laboratory.json') {
  return { target: { value: name, files: [{ name, text: async () => JSON.stringify(value) }] } }
}

test('saved configuration is available on reopen and survives a second edit without a page refresh', async () => {
  const { page, stored, messages } = createPage()
  await page.loadData()
  await page.openSettings(page.items.value[0])
  page.settings.sqlPrompt = 'saved prompt'
  await page.handleSettingsSubmit()
  assert.equal(messages.at(-1).text, '配置已保存')

  await page.openSettings(page.items.value[0])
  assert.equal(page.settings.sqlPrompt, 'saved prompt')
  page.settings.recallColMax = 23
  await page.handleSettingsSubmit()
  const saved = stored.get(1).config_json.request
  assert.equal(saved.advanced_config.nl2sql_config.prompt, 'saved prompt')
  assert.equal(saved.advanced_config.meta_embedding_config.top_k, 23)
  assert.deepEqual(saved.messages, [{ role: 'user', content: 'keep this message' }])
  assert.equal(saved.stream, true)
  assert.equal(saved.advanced_config.multi_rewrite_config.prompt, 'keep this hidden setting')
})

test('cloning after saving uses the latest source configuration', async () => {
  const { page, stored } = createPage()
  await page.loadData()
  await page.openSettings(page.items.value[0])
  page.settings.sqlPrompt = 'clone the saved prompt'
  await page.handleSettingsSubmit()
  page.openCloneDialog(page.items.value[0])
  await page.submitClone()
  assert.equal(stored.get(2).config_json.request.advanced_config.nl2sql_config.prompt, 'clone the saved prompt')
})

test('opening settings retrieves changes made after an earlier opening', async () => {
  const { page, stored } = createPage()
  await page.openSettings(project())
  page.settingsVisible.value = false
  stored.set(1, project(1, 10, 'updated elsewhere'))
  await page.openSettings(project())
  assert.equal(page.settings.sqlPrompt, 'updated elsewhere')
})

for (const staleResult of ['success', 'error']) {
  test(`a late folder ${staleResult} cannot replace the currently selected folder`, async () => {
    const first = deferred()
    const second = project(2, 11)
    const { page, messages } = createPage({
      listAutobiProjects: ({ folder_id }) => folder_id === 10 ? first.promise : Promise.resolve([second])
    }, [project(), second])
    const oldLoad = page.loadData()
    page.selectedFolderId.value = 11
    await page.loadData()
    if (staleResult === 'error') first.reject(new Error('old folder unavailable'))
    else first.resolve([project()])
    await oldLoad
    assert.equal(page.selectedFolderId.value, 11)
    assert.deepEqual(page.items.value.map(row => row.id), [2])
    assert.equal(messages.length, 0)
  })
}

test('a late list response cannot repopulate the page after all folders are cleared', async () => {
  const first = deferred()
  const { page } = createPage({ listAutobiProjects: () => first.promise })
  const oldLoad = page.loadData()
  page.selectedFolderId.value = null
  await page.loadData()
  first.resolve([project()])
  await oldLoad
  assert.deepEqual(page.items.value, [])
})

test('rapid settings clicks only open the last selected project', async () => {
  const first = deferred()
  const { page } = createPage({ getAutobiProject: id => id === 1 ? first.promise : Promise.resolve(project(2, 10, 'second prompt')) })
  const oldOpen = page.openSettings(project())
  await page.openSettings(project(2))
  first.resolve(project())
  await oldOpen
  assert.equal(page.currentSettingsItem.value.id, 2)
  assert.equal(page.settings.sqlPrompt, 'second prompt')
})

test('saving a moved project displays it in its target folder', async () => {
  const { page } = createPage()
  await page.loadData()
  await page.openSettings(page.items.value[0])
  page.settingsFolderId.value = 11
  await page.handleSettingsSubmit()
  assert.equal(page.selectedFolderId.value, 11)
  assert.deepEqual(page.items.value.map(row => row.id), [1])
  assert.equal(page.items.value[0].folder_id, 11)
})

test('creating a project in another folder displays the newly created project', async () => {
  const { page } = createPage()
  page.formRef.value = { validate: async () => true }
  page.form.folder_id = 11
  page.form.name = 'New project'
  await page.handleSubmit()
  assert.equal(page.selectedFolderId.value, 11)
  assert.equal(page.items.value[0].name, 'New project')
})

test('a failed save retains the draft and leaves the current folder unchanged', async () => {
  const { page, messages } = createPage({ updateAutobiProject: async () => { throw new Error('save unavailable') } })
  await page.openSettings(project())
  page.settings.sqlPrompt = 'unsaved draft'
  page.settingsFolderId.value = 11
  await page.handleSettingsSubmit()
  assert.equal(page.settingsVisible.value, true)
  assert.equal(page.settings.sqlPrompt, 'unsaved draft')
  assert.equal(page.settingsSaving.value, false)
  assert.equal(page.selectedFolderId.value, 10)
  assert.equal(messages.at(-1).type, 'error')
})

test('lab import previews the file and proposed name without creating a project', async () => {
  const f = createPage()
  await f.page.loadData()
  const event = fileEvent(labPayload())
  await f.page.onLabImportFile(event)
  assert.equal(event.target.value, '')
  assert.equal(f.page.labImportVisible.value, true)
  assert.equal(f.page.labImportFileName.value, 'laboratory.json')
  assert.equal(f.page.labImportForm.name, 'Project 1-导入')
  assert.equal(f.page.labImportForm.folder_id, 10)
  assert.equal(f.imports.length, 0)
  assert.equal(f.stored.size, 1)
})

test('lab import uses one request and opens the new project with empty resource selections', async () => {
  const f = createPage()
  await f.page.onLabImportFile(fileEvent(labPayload()))
  f.page.labImportForm.folder_id = 11
  f.page.labImportForm.name = ' Imported lab '
  f.page.searchKeyword.value = 'old filter'
  await f.page.submitLabImport()
  assert.deepEqual(f.imports, [{ payload: labPayload(), folder_id: 11, name: 'Imported lab' }])
  assert.equal(f.updates.length, 0)
  assert.equal(f.page.selectedFolderId.value, 11)
  assert.equal(f.page.searchKeyword.value, '')
  assert.equal(f.page.labImportVisible.value, false)
  assert.equal(f.page.items.value[0].name, 'Imported lab')
  await f.page.openSettings(f.page.items.value[0])
  assert.equal(f.page.settings.knowledgeBaseId, null)
  for (const prefix of ['rewrite', 'sql', 'nerRetrieval', 'summary', 'chart']) {
    assert.equal(f.page.settings[`${prefix}ProviderId`], null)
    assert.equal(f.page.settings[`${prefix}ModelName`], '')
  }
  assert.equal(f.page.settings.sqlPrompt, 'original prompt')
})

test('invalid lab files and blank names do not create a project', async () => {
  const f = createPage()
  await f.page.onLabImportFile(fileEvent({ format: 'chat-bi-agent-export' }))
  assert.equal(f.page.labImportVisible.value, false)
  assert.equal(f.page.labImportPayload.value, null)
  assert.equal(f.messages.at(-1).type, 'error')
  await f.page.onLabImportFile(fileEvent(labPayload()))
  f.page.labImportForm.name = '  '
  await f.page.submitLabImport()
  assert.equal(f.imports.length, 0)
  assert.equal(f.messages.at(-1).type, 'warning')
})

test('failed lab imports retain drafts for retry and ignore duplicate clicks', async () => {
  const pending = deferred()
  let count = 0
  const f = createPage({ importAutobiProject: async () => { count++; return pending.promise } })
  await f.page.onLabImportFile(fileEvent(labPayload()))
  const request = f.page.submitLabImport()
  await f.page.submitLabImport()
  assert.equal(count, 1)
  pending.reject(new Error('save unavailable'))
  await request
  assert.equal(f.page.labImportVisible.value, true)
  assert.equal(f.page.labImportLoading.value, false)
  assert.equal(f.page.labImportFileName.value, 'laboratory.json')
  assert.equal(f.page.labImportForm.name, 'Project 1')
  assert.deepEqual(f.page.labImportPayload.value, labPayload())
})

test('lab export fetches the latest saved configuration and downloads a JSON file', async () => {
  const f = createPage()
  const stale = project()
  f.stored.set(1, project(1, 10, 'latest saved SQL prompt'))
  await f.page.handleLabExport(stale)
  assert.deepEqual(f.exports, [1])
  assert.equal(f.downloads.length, 1)
  assert.equal(f.downloads[0].filename, 'Project 1-实验室.json')
  assert.equal(f.downloads[0].value.config_json.request.advanced_config.nl2sql_config.prompt, 'latest saved SQL prompt')
  assert.equal(f.page.labExportingIds.size, 0)
})

test('failed lab exports release loading state and create no download', async () => {
  const f = createPage({ exportAutobiProject: async () => { throw new Error('export unavailable') } })
  await f.page.handleLabExport(project())
  assert.equal(f.downloads.length, 0)
  assert.equal(f.page.labExportingIds.size, 0)
  assert.equal(f.messages.at(-1).type, 'error')
})

test('lab JSON parser accepts BOM and preserves all custom configuration fields', () => {
  const value = labPayload()
  value.config_json.custom_setting = { keep: [false, 12, null] }
  assert.deepEqual(transfer.parseLabImportPayload('\uFEFF' + JSON.stringify(value)), value)
})

for (const change of [{ formatVersion: 2 }, { project: [] }, { config_json: null },
  { config_json: { request: [] } }, { config_json: { request: { advanced_config: [] } } },
  { config_json: { request: { messages: [null] } } }, { config_json: { request: { stream: 'false' } } },
  { config_json: { request: {}, model_bindings: { nl2sql: 'invalid' } } }]) {
  test(`lab JSON parser rejects invalid shape: ${JSON.stringify(change)}`, () => {
    assert.throws(() => transfer.parseLabImportPayload(JSON.stringify({ ...labPayload(), ...change })))
  })
}

test('lab import name suggestions fit the name limit through repeated imports', () => {
  const value = labPayload()
  value.project.name = '长'.repeat(255)
  const projects = [{ name: value.project.name }]
  for (let index = 0; index < 3; index++) {
    const name = transfer.suggestLabImportName(value, projects)
    assert.ok(name.length <= 255)
    assert.ok(!projects.some(project => project.name === name))
    projects.push({ name })
  }
})
