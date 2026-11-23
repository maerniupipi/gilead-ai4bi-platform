/**
 * 实验中心实验室真实流水线（浏览器端串行）：与《autobi实验室接口调用流程.md》步骤一致，
 * 每步独立方法；配置来自 merge 后的 labConfig（默认 autobiLabDefaultConfig + 项目 config_json）。
 */

import { sendChatMessage, streamChatMessage } from '../api/chat'
import agentAppApi from '../api/agentApp'
import {
  esValueRetriever,
  esKnowledgeRetriever,
  sqlTemplateRetriever,
  tableMetaRetriever,
  tableValueRetriever,
  globalValueMetaRetriever,
  multiGlobalValueMetaRetriever,
  nerRetriever
} from '../api/autobiAtomic'
import { AUTOB_LAB_PIPELINE_STEPS } from '../constants/autobiLabPipeline.js'
import knowledgeBaseApi from '../api/knowledgeBase'
import {
  buildKnowledgeWordsForPrompt,
  buildKnowledgeKnowledgeMapObject,
  buildLongEsQueryWithAnnotations,
  buildTableFieldPromptData,
  buildIclExamplePromptData,
  collectFieldTablesFromMetaSteps,
  collectFieldCodesForMultiColumn,
  parseNerEntitiesFromLlm,
  replaceTemplateVars,
  extractSqlFromModelText,
  normalizeRewrittenQuery,
  buildBiSummaryUserMessage,
  formatSqlExecuteResultForSummary,
  stripLabTemplateNoise,
  applyFeaturesToLabConfigPrompts,
  replaceFeaturesInTemplate,
  buildStepFeatureValues
} from './autobiLabAggregators.js'
import { parseChartSpecFromLlm } from './autobiLabChartSpec.js'

function adv(labConfig) {
  return labConfig?.request?.advanced_config || {}
}

function bindings(labConfig) {
  return labConfig?.model_bindings || {}
}

function runtimePrompt(ctx, template) {
  return replaceFeaturesInTemplate(template, ctx.features || {})
}

async function callLlm(labConfig, bindingKey, message, extra = {}) {
  const b = bindings(labConfig)[bindingKey]
  if (!b?.provider_id || !b?.model_name) {
    throw new Error(`缺少 model_bindings.${bindingKey}`)
  }
  return sendChatMessage({
    provider_id: b.provider_id,
    model: b.model_name,
    message,
    temperature: extra.temperature ?? 0.2,
    max_tokens: extra.max_tokens ?? 4096,
    top_p: extra.top_p ?? 0.9
  })
}

/**
 * 流式调用 LLM
 * @param {object} labConfig - 实验室配置
 * @param {string} bindingKey - 模型绑定键
 * @param {string} message - 消息内容
 * @param {function(string): void} onChunk - 流式回调
 * @param {object} extra - 额外参数
 * @param {AbortSignal} [signal] - 取消信号
 */
async function callLlmStream(labConfig, bindingKey, message, onChunk, extra = {}, signal) {
  const b = bindings(labConfig)[bindingKey]
  if (!b?.provider_id || !b?.model_name) {
    throw new Error(`缺少 model_bindings.${bindingKey}`)
  }
  await streamChatMessage(
    {
      provider_id: b.provider_id,
      model: b.model_name,
      message,
      temperature: extra.temperature ?? 0.2,
      max_tokens: extra.max_tokens ?? 4096,
      top_p: extra.top_p ?? 0.9
    },
    onChunk,
    signal
  )
}

function assertKb(ctx) {
  const id = ctx.knowledgeBaseId
  if (id == null || id === '') throw new Error('未配置知识库 ID，无法执行真实流水线')
  return Number(id)
}

// ---------- 每步独立方法（stepId 与 autobiLabPipeline.js 一致）----------

async function step01_esValueOriginal(ctx) {
  const kb = assertKb(ctx)
  const cfg = adv(ctx.labConfig).value_embedding_config || { top_k: 10, threshold: 0.6 }
  const req = {
    query: ctx.userMessage,
    top_k: cfg.top_k,
    score_threshold: cfg.threshold
  }
  const res = await esValueRetriever(kb, req)
  return { request: req, response: res }
}

async function step02_skipAlias() {
  return { request: {}, response: {} }
}

async function step03_esKnowledge(ctx) {
  const cfg = adv(ctx.labConfig).knowledge_es_config || { top_k: 3, threshold: 0.3 }
  if (cfg.enable === false) {
    return { request: {}, response: { skipped: true, reason: '关键词召回未开启', results: [] } }
  }
  const kb = assertKb(ctx)
  const req = {
    query: ctx.userMessage,
    top_k: cfg.top_k,
    score_threshold: cfg.threshold
  }
  const res = await esKnowledgeRetriever(kb, req)
  return { request: req, response: res }
}

async function step04_knowledgeRewrite(ctx, acc) {
  const cfg = adv(ctx.labConfig).knowledge_rewrite_config
  const results = acc.byStep[3]?.response?.results || []
  acc.knowledgeMap = buildKnowledgeKnowledgeMapObject(results)
  if (cfg?.enable === false) {
    acc.rewrittenQuery = ctx.userMessage
    return {
      request: {},
      response: { skipped: true, reason: '知识改写未开启', rewritten_query: ctx.userMessage }
    }
  }
  if (!cfg?.prompt) throw new Error('缺少 knowledge_rewrite_config.prompt')
  const knowledgeWords = buildKnowledgeWordsForPrompt(results)
  const prompt = replaceTemplateVars(runtimePrompt(ctx, cfg.prompt), {
    rewrite_query: ctx.userMessage,
    knowledge_words: knowledgeWords || '（无知识词召回）'
  })
  const res = await callLlm(ctx.labConfig, 'knowledge_rewrite', prompt, {
    temperature: cfg.temperature,
    max_tokens: cfg.max_tokens,
    top_p: cfg.top_p
  })
  const text = res?.content ?? res ?? ''
  acc.rewrittenQuery = normalizeRewrittenQuery(text, ctx.userMessage)
  return {
    request: { prompt_preview: prompt.slice(0, 2000), full_prompt: prompt },
    response: { ...res, rewritten_query: acc.rewrittenQuery }
  }
}

async function step05_skipIclExact() {
  return { request: {}, response: {} }
}

async function step06_tableMeta(ctx, acc) {
  const kb = assertKb(ctx)
  const q = acc.rewrittenQuery || ctx.userMessage
  const cfg = adv(ctx.labConfig).meta_embedding_config || { top_k: 5, threshold: 0.3 }
  const req = { query: q, top_k: cfg.top_k, score_threshold: cfg.threshold }
  const res = await tableMetaRetriever(kb, req)
  return { request: req, response: res }
}

async function step07_globalValueMeta(ctx, acc) {
  const kb = assertKb(ctx)
  const q = acc.rewrittenQuery || ctx.userMessage
  const cfg = adv(ctx.labConfig).value_embedding_config || { top_k: 10, threshold: 0.6 }
  const req = { query: q, top_k: cfg.top_k, score_threshold: cfg.threshold }
  const res = await globalValueMetaRetriever(kb, req)
  return { request: req, response: res }
}

async function step08_sqlTemplate(ctx, acc) {
  const kb = assertKb(ctx)
  const q = acc.rewrittenQuery || ctx.userMessage
  const cfg = adv(ctx.labConfig).icl_embedding_config || { top_k: 3, threshold: 0 }
  const req = { query: q, top_k: cfg.top_k, score_threshold: cfg.threshold }
  const res = await sqlTemplateRetriever(kb, req)
  return { request: req, response: res }
}

/** 文档第 9 步：同一原子能力检索两次，合并 results */
async function step09_esValueDual(ctx, acc) {
  const kb = assertKb(ctx)
  const cfg = adv(ctx.labConfig).value_embedding_config || { top_k: 10, threshold: 0.6 }
  const rw = acc.rewrittenQuery || ctx.userMessage
  const qLong = buildLongEsQueryWithAnnotations(ctx.userMessage, acc.knowledgeMap || {})
  const reqA = { query: qLong, top_k: cfg.top_k, score_threshold: cfg.threshold }
  const reqB = { query: rw, top_k: cfg.top_k, score_threshold: cfg.threshold }
  const [resA, resB] = await Promise.all([
    esValueRetriever(kb, reqA),
    esValueRetriever(kb, reqB)
  ])
  const merged = {
    results: [...(resA.results || []), ...(resB.results || [])],
    total: (resA.total || 0) + (resB.total || 0),
    dual: { query_a: qLong, query_b: rw }
  }
  return {
    request: { calls: [reqA, reqB], merge_strategy: 'concat_results' },
    response: merged
  }
}

async function step10_skipAlias() {
  return { request: {}, response: {} }
}

async function step11_tableValue(ctx, acc) {
  const mc = adv(ctx.labConfig).value_multi_column_embedding_config || {}
  if (Boolean(mc.enable)) {
    return {
      request: {},
      response: { skipped: true, reason: '已开启多列同值，跳过表值召回（第 11 步）' }
    }
  }
  const kb = assertKb(ctx)
  const q = acc.rewrittenQuery || ctx.userMessage
  const cfg = adv(ctx.labConfig).value_embedding_config || { top_k: 10, threshold: 0.6 }
  const tables = collectFieldTablesFromMetaSteps(acc.byStep)
  if (!tables.length) {
    const req = { query: q, top_k: cfg.top_k, score_threshold: cfg.threshold }
    const res = await tableValueRetriever(kb, req)
    return { request: req, response: res }
  }
  const calls = await Promise.all(
    tables.map(table_name =>
      tableValueRetriever(kb, {
        query: q,
        table_name,
        top_k: cfg.top_k,
        score_threshold: cfg.threshold
      })
    )
  )
  const merged = []
  const seen = new Set()
  for (const res of calls) {
    for (const r of res.results || []) {
      const fc = r.metadata?.field_code || ''
      const key = `${fc}\0${(r.content || '').trim()}\0${Number(r.score).toFixed(6)}`
      if (seen.has(key)) continue
      seen.add(key)
      merged.push(r)
    }
  }
  return {
    request: {
      calls: tables.map((table_name, i) => ({
        query: q,
        table_name,
        top_k: cfg.top_k,
        score_threshold: cfg.threshold
      })),
      merge_strategy: 'per_table_parallel'
    },
    response: { results: merged, total: merged.length, parallel_tables: tables }
  }
}

async function step12_multiColumnSameValue(ctx, acc) {
  const cfg = adv(ctx.labConfig).value_multi_column_embedding_config || {
    enable: false,
    top_k: 10,
    threshold: 0.6
  }
  if (!Boolean(cfg.enable)) {
    return { request: {}, response: { skipped: true, reason: '多列同值未开启' } }
  }
  const kb = assertKb(ctx)
  const q = acc.rewrittenQuery || ctx.userMessage
  const tokens = collectFieldCodesForMultiColumn(acc.byStep)
  if (!tokens.length) {
    return {
      request: { query: q, table_name: [] },
      response: { skipped: true, reason: '第 6/7 步未提炼到 field_code，无法多路召回' }
    }
  }
  const req = {
    query: q,
    table_name: tokens,
    top_k: cfg.top_k ?? 10,
    score_threshold: cfg.threshold,
    keyword_score_threshold: cfg.keyword_score_threshold ?? null
  }
  const res = await multiGlobalValueMetaRetriever(kb, req)
  return { request: req, response: res }
}

async function step13_nerRetrieval(ctx, acc) {
  const cfg = adv(ctx.labConfig).ner_retrieval_config || { enable: false }
  if (!Boolean(cfg.enable)) {
    return { request: {}, response: { skipped: true, reason: 'NER 召回未开启' } }
  }
  if (!cfg.prompt) throw new Error('缺少 ner_retrieval_config.prompt')
  const rw = acc.rewrittenQuery || ctx.userMessage
  let entityTypes = (cfg.entity_types || cfg.filed || '').trim()
  if (!entityTypes) {
    entityTypes =
      '业务相关实体（如产品名、地区、时间口径、品牌名等），凡在文中出现且可能影响 SQL 条件的词。'
  }
  const prompt = replaceTemplateVars(runtimePrompt(ctx, cfg.prompt), { query: rw, filed: entityTypes })
  const llmRes = await callLlm(ctx.labConfig, 'ner_retrieval', prompt, {
    temperature: cfg.temperature,
    max_tokens: cfg.max_tokens,
    top_p: cfg.top_p
  })
  const llmText = llmRes?.content != null ? String(llmRes.content) : String(llmRes ?? '')
  const entities = parseNerEntitiesFromLlm(llmText)
  const aliasTop = Number(cfg.ner_alias_top_k) > 0 ? Number(cfg.ner_alias_top_k) : 30
  let narrative = 'NER 模型未抽取到实体，已跳过别名库检索。'
  let nerAtomic = { results: [], total: 0, narrative }
  if (entities.length) {
    const kb = assertKb(ctx)
    nerAtomic = await nerRetriever(kb, { query: rw, entity: entities, top_k: aliasTop })
    narrative = nerAtomic.narrative || ''
  }
  return {
    request: {
      llm_prompt_preview: prompt.slice(0, 2000),
      full_prompt: prompt,
      ner_atomic_request: entities.length ? { query: rw, entity: entities, top_k: aliasTop } : null
    },
    response: {
      llm_raw: llmText,
      entities,
      ner_atomic: nerAtomic,
      narrative
    }
  }
}

async function step14_nl2sql(ctx, acc) {
  const cfg = adv(ctx.labConfig).nl2sql_config
  if (!cfg?.prompt) throw new Error('缺少 nl2sql_config.prompt')
  const tableField = buildTableFieldPromptData(acc.byStep)
  const iclExample = buildIclExamplePromptData(acc.byStep)
  const q = acc.rewrittenQuery || ctx.userMessage
  const kwNl = buildKnowledgeWordsForPrompt(acc.byStep[3]?.response?.results || [])
  const s13 = acc.byStep[13]?.response || {}
  let nerNl = ''
  if (s13 && !s13.skipped) nerNl = (s13.narrative || '').trim()
  if (!nerNl) nerNl = '（无 NER 映射信息）'
  const databaseType = ctx.databaseType || ctx.features?.database_type || ctx.features?.databaseType || 'SQL'
  const prompt = replaceTemplateVars(runtimePrompt(ctx, cfg.prompt), {
    database_type: databaseType,
    table_field_prompt_data: tableField,
    table_join_relation_prompt_data: '',
    default_field_prompt_data: '',
    icl_example_prompt_data: iclExample,
    knowledge_prompt_data: kwNl || '（无知识词扩展说明）',
    ner_info: nerNl,
    query: q
  })
  const res = await callLlm(ctx.labConfig, 'nl2sql', prompt, {
    temperature: cfg.temperature,
    max_tokens: cfg.max_tokens,
    top_p: cfg.top_p
  })
  const text = res?.content ?? res ?? ''
  acc.generatedSql = extractSqlFromModelText(text)
  return {
    request: { prompt_preview: prompt.slice(0, 3000), full_prompt: prompt, database_type: databaseType },
    response: { ...res, sql: acc.generatedSql, database_type: databaseType }
  }
}

async function step15_skipSqlExtend() {
  return { request: {}, response: {} }
}

function extractAgentRunSql(trace) {
  const output = trace?.output
  if (output != null && String(output).trim()) return String(output).trim()
  const steps = Array.isArray(trace?.steps) ? trace.steps : []
  for (let i = steps.length - 1; i >= 0; i--) {
    const res = steps[i]?.output || steps[i]?.response
    if (res == null) continue
    if (typeof res === 'string' && res.trim()) return res.trim()
    if (typeof res === 'object') {
      for (const key of ['sql', 'content', 'output', 'result']) {
        if (res[key] != null && String(res[key]).trim()) return String(res[key]).trim()
      }
    }
  }
  const exports = trace?.exports
  if (exports && typeof exports === 'object') {
    for (const [key, val] of Object.entries(exports)) {
      if (['sql', 'content', 'output', 'result'].includes(String(key).split('.').pop()) && val != null && String(val).trim()) {
        return String(val).trim()
      }
    }
  }
  return ''
}

async function runAgentWorkflowForSql(appId, versionId, inputs) {
  const started = await agentAppApi.runWorkflow(appId, versionId, { inputs })
  const runId = started?.run_id || started?.trace_id
  if (!runId) throw new Error('SQL 权限改写智能体未返回 run_id')
  const deadline = Date.now() + 120000
  while (Date.now() < deadline) {
    const trace = await agentAppApi.getRunTrace(appId, runId)
    if (trace?.status === 'done') return extractAgentRunSql(trace)
    if (trace?.status === 'error') throw new Error(trace.error || 'SQL 权限改写智能体执行失败')
    await new Promise(resolve => setTimeout(resolve, 800))
  }
  throw new Error('SQL 权限改写智能体执行超时')
}

async function step15_sqlPermissionRewrite(ctx, acc) {
  const cfg = adv(ctx.labConfig).sql_permission_rewrite_config || {}
  const originalSql = (acc.generatedSql || '').trim()
  const baseResponse = {
    original_sql: originalSql,
    rewritten_sql: originalSql,
    sql: originalSql
  }
  if (!Boolean(cfg.enable)) {
    return {
      request: { sql: originalSql },
      response: { ...baseResponse, skipped: true, reason: 'SQL 权限改写未开启' }
    }
  }
  if (!originalSql || /^none$/i.test(originalSql)) {
    return {
      request: { sql: originalSql },
      response: { ...baseResponse, skipped: true, reason: 'nl2sql 未生成可改写 SQL（空或 None）' }
    }
  }
  if (!cfg.target_app_id || !cfg.target_version_id) {
    throw new Error('SQL 权限改写已开启，但未选择智能体 ID 或版本')
  }
  const rewrittenSql = await runAgentWorkflowForSql(cfg.target_app_id, cfg.target_version_id, {
    input: originalSql,
    features: ctx.features || {}
  })
  if (!rewrittenSql) throw new Error('SQL 权限改写智能体未返回 SQL')
  acc.generatedSql = extractSqlFromModelText(rewrittenSql) || rewrittenSql
  return {
    request: {
      target_app_id: cfg.target_app_id,
      target_version_id: cfg.target_version_id,
      input: originalSql,
      features: ctx.features || {}
    },
    response: {
      ...baseResponse,
      rewritten_sql: acc.generatedSql,
      sql: acc.generatedSql
    }
  }
}

async function step16_sqlDataRetriever(ctx, acc) {
  const kb = assertKb(ctx)
  const sql = (acc.generatedSql || '').trim()
  if (!sql || /^none$/i.test(sql)) {
    const response = {
      skipped: true,
      reason: 'nl2sql 未生成可执行 SQL（空或 None）',
      columns: [],
      rows: [],
      row_count: 0
    }
    return { request: { sql: sql || '' }, response }
  }
  const response = await knowledgeBaseApi.executeKnowledgeBaseSql(kb, sql)
  return { request: { sql }, response }
}

async function step17_biSummary(ctx, acc, onStreamSummary) {
  const cfg = adv(ctx.labConfig).bi_summary_config
  if (cfg?.enable === false) {
    acc.summaryText = ''
    return { request: {}, response: { skipped: true, reason: '总结摘要未开启' } }
  }
  if (!cfg?.prompt) throw new Error('缺少 bi_summary_config.prompt')
  const sql = acc.generatedSql || '无'
  const sqlDataText = formatSqlExecuteResultForSummary(acc.byStep[16]?.response)
  const message = buildBiSummaryUserMessage(runtimePrompt(ctx, cfg.prompt), {
    originalQuery: ctx.userMessage,
    executeSql: sql,
    sqlDataText
  })

  // 如果提供了流式回调，使用流式调用
  if (onStreamSummary && typeof onStreamSummary === 'function') {
    let fullContent = ''
    await callLlmStream(
      ctx.labConfig,
      'bi_summary',
      message,
      chunk => {
        fullContent += chunk
        onStreamSummary(fullContent)
      },
      {
        temperature: cfg.temperature,
        max_tokens: cfg.max_tokens,
        top_p: cfg.top_p
      },
      ctx.signal
    )
    acc.summaryText = fullContent
    return {
      request: { message_preview: message.slice(0, 2500), full_message: message },
      response: { content: fullContent }
    }
  }

  // 非流式调用
  const res = await callLlm(ctx.labConfig, 'bi_summary', message, {
    temperature: cfg.temperature,
    max_tokens: cfg.max_tokens,
    top_p: cfg.top_p
  })
  acc.summaryText = res?.content ?? res ?? ''
  return {
    request: { message_preview: message.slice(0, 2500), full_message: message },
    response: res
  }
}

async function step18_chartSpec(ctx, acc) {
  const cfg = adv(ctx.labConfig).chart_drawing_config || {}
  if (cfg.enable === false) {
    acc.chartSpec = null
    return {
      request: { skipped: true, reason: 'chart_drawing_config.enable=false' },
      response: { chart_spec: null }
    }
  }
  if (!cfg.prompt) {
    acc.chartSpec = null
    return {
      request: { skipped: true, reason: '缺少 chart_drawing_config.prompt' },
      response: { chart_spec: null }
    }
  }

  const sqlRes = acc.byStep[16]?.response
  if (!sqlRes || sqlRes.skipped || !sqlRes.rows?.length) {
    acc.chartSpec = null
    return {
      request: { skipped: true, reason: '无 SQL 结果或已跳过执行' },
      response: { chart_spec: null }
    }
  }

  const maxRows = Number(cfg.max_preview_rows) > 0 ? Number(cfg.max_preview_rows) : 80
  const cols = sqlRes.columns || []
  const fieldMapping = cols.map(c => `${c}:${c}`).join('; ')
  const totalRows = sqlRes.row_count ?? sqlRes.rows.length
  const preview = {
    columns: cols,
    rows: (sqlRes.rows || []).slice(0, maxRows),
    row_count: totalRows,
    preview_note:
      sqlRes.rows.length > maxRows ? `（以下为前 ${maxRows} 行样本，总行数 ${totalRows}）` : ''
  }
  const sqlResultJson = JSON.stringify(preview, null, 2)
  let prompt = replaceTemplateVars(runtimePrompt(ctx, cfg.prompt), {
    original_query: ctx.userMessage,
    rewrite_query: acc.rewrittenQuery || ctx.userMessage,
    execute_sql: acc.generatedSql || '无',
    field_mapping: fieldMapping,
    sql_result_json: sqlResultJson
  })
  prompt = stripLabTemplateNoise(prompt)

  let res = null
  let chartSpec = null
  let llmError = null
  try {
    res = await callLlm(ctx.labConfig, 'chart_drawing', prompt, {
      temperature: cfg.temperature,
      max_tokens: cfg.max_tokens,
      top_p: cfg.top_p
    })
    const text = res?.content != null ? String(res.content) : String(res ?? '')
    chartSpec = parseChartSpecFromLlm(text)
    acc.chartSpec = chartSpec
    return {
      request: { prompt_preview: prompt.slice(0, 2500), full_prompt: prompt },
      response: { ...res, chart_spec: chartSpec, raw_text_preview: text.slice(0, 4000) }
    }
  } catch (e) {
    llmError = e?.message || String(e)
    acc.chartSpec = null
    return {
      request: { prompt_preview: prompt.slice(0, 2500), full_prompt: prompt },
      response: { chart_spec: null, error: llmError }
    }
  }
}

const RUNNERS = {
  1: step01_esValueOriginal,
  2: step02_skipAlias,
  3: step03_esKnowledge,
  4: step04_knowledgeRewrite,
  5: step05_skipIclExact,
  6: step06_tableMeta,
  7: step07_globalValueMeta,
  8: step08_sqlTemplate,
  9: step09_esValueDual,
  10: step10_skipAlias,
  11: step11_tableValue,
  12: step12_multiColumnSameValue,
  13: step13_nerRetrieval,
  14: step14_nl2sql,
  15: step15_sqlPermissionRewrite,
  16: step16_sqlDataRetriever,
  17: step17_biSummary,
  18: step18_chartSpec
}

/**
 * @param {{ userMessage: string, knowledgeBaseId: number|string|null, labConfig: object, signal?: AbortSignal, projectId: string, features?: Record<string, string> }} ctx
 * @param onStep 同 Mock
 * @param {function(string): void} [onStreamSummary] - 流式输出数据总结的回调（可选）
 */
export async function runAutobiLabPipelineReal(ctx, onStep, onStreamSummary) {
  const runtimeFeatures =
    ctx.features && typeof ctx.features === 'object' ? { ...ctx.features } : {}
  const runCtx = {
    ...ctx,
    features: runtimeFeatures,
    labConfig: applyFeaturesToLabConfigPrompts(
      JSON.parse(JSON.stringify(ctx.labConfig)),
      runtimeFeatures
    )
  }

  const acc = {
    byStep: {},
    rewrittenQuery: '',
    generatedSql: '',
    summaryText: '',
    knowledgeMap: {},
    chartSpec: null
  }

  for (const meta of AUTOB_LAB_PIPELINE_STEPS) {
    if (runCtx.signal?.aborted) throw new Error('aborted')

    const t0 = performance.now()
    onStep({ meta, status: 'running' })

    const runner = RUNNERS[meta.stepId]
    if (!runner) {
      const err = `未注册步骤 ${meta.stepId}`
      onStep({
        meta,
        status: 'error',
        error: err,
        durationMs: Math.round(performance.now() - t0)
      })
      throw new Error(err)
    }

    let request
    let response
    let error
    try {
      // step17 支持 onStreamSummary 参数
      const out =
        meta.stepId === 17
          ? await runner(runCtx, acc, onStreamSummary)
          : await runner(runCtx, acc)
      request = out.request
      response = out.response
      acc.byStep[meta.stepId] = { request, response }
      Object.assign(runtimeFeatures, buildStepFeatureValues(meta, response))
    } catch (e) {
      error = e?.message || String(e)
    }

    const durationMs = Math.round(performance.now() - t0)

    onStep({
      meta,
      status: error ? 'error' : 'done',
      request,
      response,
      error,
      durationMs
    })

    if (error) throw new Error(error)
  }

  const summaryText =
    acc.summaryText ||
    (acc.byStep[17]?.response?.content != null ? String(acc.byStep[17].response.content) : '')

  // 获取 SQL 查询结果（step 16）
  const sqlDataResponse = acc.byStep[16]?.response || null

  return {
    summaryText: adv(runCtx.labConfig).bi_summary_config?.enable === false
      ? ''
      : summaryText || '（未返回总结内容）',
    rewrittenQuery: acc.rewrittenQuery,
    sql: acc.generatedSql,
    sqlData: sqlDataResponse,
    chartSpec: acc.chartSpec ?? null
  }
}

export function canRunAutobiLabPipelineReal(ctx) {
  return (
    ctx?.knowledgeBaseId != null &&
    ctx.knowledgeBaseId !== '' &&
    ctx?.labConfig?.model_bindings &&
    ctx?.labConfig?.request?.advanced_config
  )
}

export { AUTOB_LAB_PIPELINE_STEPS }
