import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { transformWithEsbuild } from 'vite'
import { applyConfigJsonToSettings, buildStoredConfig } from '../src/utils/autobiPayload.js'
import * as aggregators from '../src/utils/autobiLabAggregators.js'
import * as charts from '../src/utils/autobiLabChartSpec.js'
import { AUTOB_LAB_PIPELINE_STEPS } from '../src/constants/autobiLabPipeline.js'

const pipelineSource = await readFile(new URL('../src/utils/autobiLabPipelineReal.js', import.meta.url), 'utf8')
const { code: pipelineCode } = await transformWithEsbuild(pipelineSource, 'autobiLabPipelineReal.js', { format: 'cjs' })

function browserPipeline() {
  const calls = []
  const modules = {
    '../api/chat': {
      sendChatMessage: async request => { calls.push(request.model); return { content: 'rewritten question' } },
      streamChatMessage: async (request, onChunk) => { calls.push(request.model); onChunk('streamed summary') }
    },
    '../api/autobiAtomic': {
      esKnowledgeRetriever: async () => { calls.push('knowledge'); return { results: [] } }
    },
    '../api/agentApp': {},
    '../api/knowledgeBase': {},
    '../constants/autobiLabPipeline.js': {
      AUTOB_LAB_PIPELINE_STEPS: AUTOB_LAB_PIPELINE_STEPS.filter(step => [3, 4, 17].includes(step.stepId))
    },
    './autobiLabAggregators.js': aggregators,
    './autobiLabChartSpec.js': charts
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', pipelineCode)(id => {
    assert.ok(Object.hasOwn(modules, id), `Unexpected import: ${id}`)
    return modules[id]
  }, module, module.exports)
  return { run: module.exports.runAutobiLabPipelineReal, calls }
}

test('optional switches and every model context limit survive saving and reopening', () => {
  const edited = {
    keywordRecallEnabled: false,
    rewriteEnabled: false,
    summaryEnabled: false,
    chartEnabled: false,
    nerRetrievalEnabled: false,
    rewriteMaxCtx: 8192,
    sqlMaxCtx: 16384,
    nerMaxCtx: 2048,
    summaryMaxCtx: 12288,
    chartMaxCtx: 6144
  }
  const saved = JSON.parse(JSON.stringify(buildStoredConfig(edited, null, null)))
  const reopened = {}
  applyConfigJsonToSettings(saved, reopened)
  for (const [field, expected] of Object.entries(edited)) {
    assert.equal(reopened[field], expected, `${field} must round-trip`)
  }
})

test('saving the general settings preserves the tool output and applies the edited SQL prompt', () => {
  for (const output of ['recall', 'sql']) {
    const advanced = { output_stage: output, data_scope_policy: 'ddi', nl2sql_config: { prompt: 'original' } }
    const initial = { knowledge_base_id: 11, model_bindings: { nl2sql: { provider_id: 7, model_name: 'chosen' } },
      request: { advanced_config: advanced } }
    const form = {}
    applyConfigJsonToSettings(initial, form)
    form.sqlPrompt = 'new {{query}}'
    const saved = buildStoredConfig(form, initial.request, advanced)
    assert.equal(saved.request.advanced_config.output_stage, output)
    assert.equal(saved.request.advanced_config.data_scope_policy, 'ddi')
    assert.equal(saved.request.advanced_config.nl2sql_config.prompt, 'new {{query}}')
    assert.deepEqual(saved.model_bindings.nl2sql, initial.model_bindings.nl2sql)
  }
})

test('old configurations without enable or context fields retain form defaults', () => {
  const settings = {
    keywordRecallEnabled: true,
    summaryEnabled: true,
    rewriteMaxCtx: 4096,
    sqlMaxCtx: 4096,
    summaryMaxCtx: 4096,
    chartMaxCtx: 4096
  }
  const original = { ...settings }
  applyConfigJsonToSettings({ request: { advanced_config: {
    knowledge_es_config: { top_k: 3 },
    knowledge_rewrite_config: { prompt: 'rewrite' },
    nl2sql_config: { prompt: 'sql' },
    bi_summary_config: { prompt: 'summary' },
    chart_drawing_config: { prompt: 'chart' }
  } } }, settings)
  for (const [field, value] of Object.entries(original)) assert.equal(settings[field], value)
})

test('browser pipeline skips disabled stages without a retriever, model binding or summary output', async () => {
  const { run, calls } = browserPipeline()
  const events = []
  const streamed = []
  const result = await run({
    userMessage: 'original question',
    knowledgeBaseId: 1,
    labConfig: { request: { advanced_config: {
      knowledge_es_config: { enable: false },
      knowledge_rewrite_config: { enable: false },
      bi_summary_config: { enable: false }
    } } }
  }, event => events.push(event), text => streamed.push(text))
  assert.deepEqual(calls, [])
  assert.deepEqual(streamed, [])
  assert.equal(result.rewrittenQuery, 'original question')
  assert.equal(result.summaryText, '')
  const completed = events.filter(event => event.status === 'done')
  assert.equal(completed.length, 3)
  assert.ok(completed.every(event => event.response.skipped))
})

for (const enable of [undefined, true]) {
  test(`browser pipeline preserves enabled and legacy optional stages (enable=${enable})`, async () => {
    const { run, calls } = browserPipeline()
    const result = await run({
      userMessage: 'original question',
      knowledgeBaseId: 1,
      labConfig: {
        model_bindings: {
          knowledge_rewrite: { provider_id: 1, model_name: 'rewrite-model' },
          bi_summary: { provider_id: 1, model_name: 'summary-model' }
        },
        request: { advanced_config: {
          knowledge_es_config: { enable, top_k: 3 },
          knowledge_rewrite_config: { enable, prompt: 'Rewrite {{rewrite_query}}' },
          bi_summary_config: { enable, prompt: 'Summarize {{original_query}}' }
        } }
      }
    }, () => {}, () => {})
    assert.deepEqual(calls, ['knowledge', 'rewrite-model', 'summary-model'])
    assert.equal(result.rewrittenQuery, 'rewritten question')
    assert.equal(result.summaryText, 'streamed summary')
  })
}
