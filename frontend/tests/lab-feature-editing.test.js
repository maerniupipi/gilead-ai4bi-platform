import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { compileScript, parse } from 'vue/compiler-sfc'
import { transformWithEsbuild } from 'vite'
import * as vue from 'vue'

const source = await readFile(new URL('../src/pages/agent-platform/workflow/LabFeaturesTreeEditor.vue', import.meta.url), 'utf8')
const { descriptor } = parse(source)
const { code } = await transformWithEsbuild(compileScript(descriptor, { id: 'feature-editing' }).content, 'LabFeatures.js', { format: 'cjs' })

function editor(initial) {
  const props = vue.reactive({ modelValue: structuredClone(initial), upstreamVarOptions: [{ value: '上游.year' }] })
  const messages = []
  const modules = { vue, 'element-plus': { ElMessage: { warning: message => messages.push(message) } }, '@element-plus/icons-vue': {} }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(id => modules[id], module, module.exports)
  const scope = vue.effectScope()
  const page = scope.run(() => module.exports.default.setup(props, { expose() {}, emit(event, value) {
    assert.equal(event, 'update:modelValue')
    props.modelValue = value
  } }))
  return { props, messages, page, scope }
}

test('typed key drafts survive unrelated model updates and commit in place with the original reference', async () => {
  const f = editor({ new_field: '{{上游.year}}', next: 0, flag: false })
  const rowKey = f.page.fieldRowKey('new_field')
  f.page.keyDrafts.value.new_field = 'max_'
  f.page.setFieldConstValue('next', '2026')
  await vue.nextTick()
  assert.equal(f.page.keyDrafts.value.new_field, 'max_')
  f.page.keyDrafts.value.new_field = 'max_year'
  f.page.onRenameKey('new_field')
  await vue.nextTick()
  assert.deepEqual(f.props.modelValue, { max_year: '{{上游.year}}', next: 2026, flag: false })
  assert.deepEqual(f.page.fieldKeys.value, ['max_year', 'next', 'flag'])
  assert.equal(f.page.fieldMode('max_year'), 'ref')
  assert.equal(f.page.fieldRowKey('max_year'), rowKey)
  f.scope.stop()
})

test('empty and duplicate names reset only the invalid draft, preserving other pending input', () => {
  const f = editor({ first: 'one', second: 'two' })
  f.page.keyDrafts.value.second = 'second_draft'
  for (const invalid of [' ', 'second']) {
    f.page.keyDrafts.value.first = invalid
    f.page.onRenameKey('first')
    assert.deepEqual(f.props.modelValue, { first: 'one', second: 'two' })
    assert.equal(f.page.keyDrafts.value.first, 'first')
    assert.equal(f.page.keyDrafts.value.second, 'second_draft')
  }
  assert.equal(f.messages.length, 2)
  f.scope.stop()
})

test('edited names and reference/constant values survive serialization and reopening', () => {
  const f = editor({ new_field: '{{上游.year}}' })
  f.page.keyDrafts.value.new_field = 'max_year'
  f.page.onRenameKey('new_field')
  f.page.setFieldRefValue('max_year', '上游.month')
  f.page.addKey()
  f.page.setFieldConstValue('new_field', 'false')
  const reopened = editor(JSON.parse(JSON.stringify(f.props.modelValue)))
  assert.equal(reopened.page.fieldRefValue('max_year'), '上游.month')
  assert.equal(reopened.page.fieldValue('new_field'), false)
  reopened.page.removeKey('new_field')
  assert.deepEqual(reopened.props.modelValue, { max_year: '{{上游.month}}' })
  f.scope.stop(); reopened.scope.stop()
})
