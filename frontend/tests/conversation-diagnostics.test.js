import test from 'node:test'
import assert from 'node:assert/strict'
import { compactInputs, analysisCalls } from '../src/components/conversationDiagnosticView.js'

test('compact view folds only known aliases and equal features mirrors without mutating evidence', () => {
  const inputs = { input: '查询', question: '查询', message: '另一个消息', user_id: '001',
    department: 'east', metadata: { region: 'east', messages: ['旧消息'] },
    history_messages: [{ role: 'user', content: '上题' }],
    history: '[{"role":"user","content":"上题"}]',
    sales: 0, target: 0, features: { department: 'east', sales: 0, business_month: '2026-01' } }
  const original = JSON.stringify(inputs)
  const view = compactInputs(inputs)
  assert.equal(JSON.stringify(inputs), original)
  assert.equal(view.values.message, '另一个消息')
  assert.equal(view.values.sales, 0)
  assert.equal(view.values.target, 0)
  assert.deepEqual(view.values.metadata, { region: 'east', messages: ['旧消息'] })
  assert.deepEqual(view.values.features, { business_month: '2026-01' })
  assert(view.aliases.some(item => item.field === 'question' && item.same_as === 'input'))
  assert(view.aliases.some(item => item.field === 'history'))
})

test('only identical root agent/workflow captures are merged; real child runs stay separate', () => {
  const call = { app_id: 1, version_id: 2, inputs: { input: '问题' } }
  const source = [{ ...call, kind: 'agent' }, { ...call, kind: 'workflow', trace_id: 'root' },
    { ...call, kind: 'nested_agent', trace_id: 'child1' }, { ...call, kind: 'nested_agent', trace_id: 'child2' },
    { ...call, kind: 'model', id: 'm1' }, { ...call, kind: 'model', id: 'm2' }]
  const visible = analysisCalls(source)
  assert.equal(visible.length, 3)
  assert.equal(visible[0].trace_id, 'root')
  assert(visible[0].combined_root_capture)
  assert.equal(visible[2].trace_id, 'child2')
  assert.equal(source.length, 6)
})
