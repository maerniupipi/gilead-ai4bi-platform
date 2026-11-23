/**
 * 实验中心存库结构（对齐 OpenTrek / completions 入参）：
 * {
 *   knowledge_base_id,
 *   model_bindings: { knowledge_rewrite, nl2sql, bi_summary, chart_drawing },
 *   request: { messages, stream, advanced_config }
 * }
 */

/** 未在表单中编辑的「多轮补全」块：与参考接口一致，可从已保存配置中合并保留 */
export const MULTI_REWRITE_DEFAULT = {
  enable: true,
  prompt: `现在你有一个上下文依赖问题补全任务，任务要求：根据历史问题中的相关信息补全当前问题中省略的信息（例如时间、实体、询问内容等），使其成为一个独立的问题，不再依赖历史问题的相关信息；注意请确保补全后的问题清晰独立地表达原意，不要引入额外问题；注意如果当前问题不依赖历史问题直接返回none即可。
历史问题依次是：{{history_queries | replace("'", '"')}}
当前问题是：“{{original_query}}”
根据历史问题中的相关信息补全当前问题省略的信息，如果不需要补全直接输出none：`,
  temperature: 0.1,
  top_k: 1,
  top_p: 0.5,
  max_tokens: 6000
}

function clone(obj) {
  return obj == null ? obj : JSON.parse(JSON.stringify(obj))
}

/**
 * 用表单 settings 覆盖 advanced_config；保留 prev 中未对接表单的键（如 multi_rewrite_config 全文）
 */
export function buildAdvancedConfig(settings, prevAdvanced) {
  const prev = prevAdvanced && typeof prevAdvanced === 'object' ? clone(prevAdvanced) : {}

  return {
    ...prev,
    multi_rewrite_config: prev.multi_rewrite_config || clone(MULTI_REWRITE_DEFAULT),
    knowledge_es_config: {
      ...(prev.knowledge_es_config || {}),
      enable: settings.keywordRecallEnabled,
      top_k: settings.rewriteKeywordMaxRecall,
      threshold: prev.knowledge_es_config?.threshold ?? 0.3
    },
    knowledge_rewrite_config: {
      ...(prev.knowledge_rewrite_config || {}),
      enable: settings.rewriteEnabled,
      prompt: settings.rewritePrompt,
      temperature: settings.rewriteTemperature,
      top_k: settings.rewriteTopK,
      top_p: settings.rewriteTopP,
      max_tokens: settings.rewriteMaxOut,
      max_context_tokens: settings.rewriteMaxCtx
    },
    meta_embedding_config: {
      ...(prev.meta_embedding_config || {}),
      top_k: settings.recallColMax,
      threshold: settings.recallColThreshold
    },
    value_embedding_config: {
      ...(prev.value_embedding_config || {}),
      top_k: settings.recallValMax,
      threshold: settings.recallValThreshold
    },
    value_multi_column_embedding_config: {
      ...(prev.value_multi_column_embedding_config || {}),
      enable: settings.recallValMultiColEnabled,
      top_k: settings.recallValMultiColMax,
      threshold: settings.recallValMultiColThreshold
    },
    icl_embedding_config: {
      ...(prev.icl_embedding_config || {}),
      top_k: settings.recallSqlMax,
      threshold: settings.recallSqlThreshold
    },
    ner_retrieval_config: {
      ...(prev.ner_retrieval_config || {}),
      enable: settings.nerRetrievalEnabled,
      prompt: settings.nerPrompt,
      temperature: settings.nerTemperature,
      top_k: settings.nerTopK,
      top_p: settings.nerTopP,
      max_tokens: settings.nerMaxOut,
      max_context_tokens: settings.nerMaxCtx
    },
    nl2sql_config: {
      ...(prev.nl2sql_config || {}),
      prompt: settings.sqlPrompt,
      temperature: settings.sqlTemperature,
      top_k: settings.sqlTopK,
      top_p: settings.sqlTopP,
      max_tokens: settings.sqlMaxOut,
      max_context_tokens: settings.sqlMaxCtx
    },
    sql_permission_rewrite_config: {
      ...(prev.sql_permission_rewrite_config || {}),
      enable: settings.sqlPermissionRewriteEnabled,
      target_app_id: settings.sqlPermissionRewriteAgentId,
      target_version_id: settings.sqlPermissionRewriteVersionId
    },
    bi_summary_config: {
      ...(prev.bi_summary_config || {}),
      enable: settings.summaryEnabled,
      prompt: settings.summaryPrompt,
      temperature: settings.summaryTemperature,
      top_k: settings.summaryTopK,
      top_p: settings.summaryTopP,
      max_tokens: settings.summaryMaxOut,
      max_context_tokens: settings.summaryMaxCtx
    },
    chart_drawing_config: {
      ...(prev.chart_drawing_config || {}),
      enable: settings.chartEnabled,
      prompt: settings.chartPrompt,
      temperature: settings.chartTemperature,
      top_k: settings.chartTopK,
      top_p: settings.chartTopP,
      max_tokens: settings.chartMaxOut,
      max_context_tokens: settings.chartMaxCtx
    }
  }
}

export function buildModelBindings(settings) {
  return {
    knowledge_rewrite: {
      provider_id: settings.rewriteProviderId,
      model_name: settings.rewriteModelName
    },
    nl2sql: {
      provider_id: settings.sqlProviderId,
      model_name: settings.sqlModelName
    },
    ner_retrieval: {
      provider_id: settings.nerRetrievalProviderId,
      model_name: settings.nerRetrievalModelName
    },
    bi_summary: {
      provider_id: settings.summaryProviderId,
      model_name: settings.summaryModelName
    },
    chart_drawing: {
      provider_id: settings.chartProviderId,
      model_name: settings.chartModelName
    }
  }
}

/**
 * @param {object} settings — 表单 reactive
 * @param {object|null} requestSnapshot — { messages, stream }
 * @param {object|null} prevAdvanced — 上次保存的 advanced_config（用于保留 multi_rewrite 等）
 */
export function buildStoredConfig(settings, requestSnapshot, prevAdvanced) {
  const messages =
    requestSnapshot?.messages?.length > 0
      ? requestSnapshot.messages
      : [{ role: 'user', content: '' }]
  const stream = requestSnapshot?.stream === true

  return {
    knowledge_base_id: settings.knowledgeBaseId ?? null,
    /** 各能力块用户协议勾选状态，提交时写入；再次打开设置时恢复为已同意 */
    disclaimer_acceptance: {
      rewrite: !!settings.rewriteDisclaimer,
      ner: !!settings.nerRetrievalDisclaimer,
      sql: !!settings.sqlDisclaimer,
      summary: !!settings.summaryDisclaimer,
      chart: !!settings.chartDisclaimer
    },
    model_bindings: buildModelBindings(settings),
    request: {
      messages,
      stream,
      advanced_config: buildAdvancedConfig(settings, prevAdvanced)
    }
  }
}

export function applyModelBindingsToSettings(bindings, settings) {
  if (!bindings || typeof bindings !== 'object') return
  const b = bindings
  if (b.knowledge_rewrite) {
    settings.rewriteProviderId = b.knowledge_rewrite.provider_id ?? null
    settings.rewriteModelName = b.knowledge_rewrite.model_name || ''
  }
  if (b.nl2sql) {
    settings.sqlProviderId = b.nl2sql.provider_id ?? null
    settings.sqlModelName = b.nl2sql.model_name || ''
  }
  if (b.ner_retrieval) {
    settings.nerRetrievalProviderId = b.ner_retrieval.provider_id ?? null
    settings.nerRetrievalModelName = b.ner_retrieval.model_name || ''
  }
  if (b.bi_summary) {
    settings.summaryProviderId = b.bi_summary.provider_id ?? null
    settings.summaryModelName = b.bi_summary.model_name || ''
  }
  if (b.chart_drawing) {
    settings.chartProviderId = b.chart_drawing.provider_id ?? null
    settings.chartModelName = b.chart_drawing.model_name || ''
  }
}

/**
 * 将已保存的 config_json 写回表单（仅映射已有字段）
 */
export function applyConfigJsonToSettings(cfg, settings) {
  if (!cfg || typeof cfg !== 'object') return
  settings.knowledgeBaseId = cfg.knowledge_base_id ?? null
  applyModelBindingsToSettings(cfg.model_bindings, settings)

  const da = cfg.disclaimer_acceptance
  if (da && typeof da === 'object') {
    if (typeof da.rewrite === 'boolean') settings.rewriteDisclaimer = da.rewrite
    if (typeof da.ner === 'boolean') settings.nerRetrievalDisclaimer = da.ner
    if (typeof da.sql === 'boolean') settings.sqlDisclaimer = da.sql
    if (typeof da.summary === 'boolean') settings.summaryDisclaimer = da.summary
    if (typeof da.chart === 'boolean') settings.chartDisclaimer = da.chart
  }

  const adv = cfg.request?.advanced_config
  if (!adv || typeof adv !== 'object') return

  const ke = adv.knowledge_es_config
  if (typeof ke?.enable === 'boolean') settings.keywordRecallEnabled = ke.enable
  if (ke && typeof ke.top_k === 'number') settings.rewriteKeywordMaxRecall = ke.top_k

  const kr = adv.knowledge_rewrite_config
  if (kr) {
    if (typeof kr.enable === 'boolean') settings.rewriteEnabled = kr.enable
    if (kr.prompt != null) settings.rewritePrompt = kr.prompt
    if (typeof kr.temperature === 'number') settings.rewriteTemperature = kr.temperature
    if (typeof kr.top_k === 'number') settings.rewriteTopK = kr.top_k
    if (typeof kr.top_p === 'number') settings.rewriteTopP = kr.top_p
    if (typeof kr.max_tokens === 'number') settings.rewriteMaxOut = kr.max_tokens
    if (typeof kr.max_context_tokens === 'number') settings.rewriteMaxCtx = kr.max_context_tokens
  }

  const meta = adv.meta_embedding_config
  if (meta) {
    if (typeof meta.top_k === 'number') settings.recallColMax = meta.top_k
    if (typeof meta.threshold === 'number') settings.recallColThreshold = meta.threshold
  }
  const val = adv.value_embedding_config
  if (val) {
    if (typeof val.top_k === 'number') settings.recallValMax = val.top_k
    if (typeof val.threshold === 'number') settings.recallValThreshold = val.threshold
  }
  const vmc = adv.value_multi_column_embedding_config
  if (vmc) {
    if (typeof vmc.enable === 'boolean') settings.recallValMultiColEnabled = vmc.enable
    if (typeof vmc.top_k === 'number') settings.recallValMultiColMax = vmc.top_k
    if (typeof vmc.threshold === 'number') settings.recallValMultiColThreshold = vmc.threshold
  }
  const ner = adv.ner_retrieval_config
  if (ner) {
    if (typeof ner.enable === 'boolean') settings.nerRetrievalEnabled = ner.enable
    if (ner.prompt != null) settings.nerPrompt = ner.prompt
    if (typeof ner.temperature === 'number') settings.nerTemperature = ner.temperature
    if (typeof ner.top_k === 'number') settings.nerTopK = ner.top_k
    if (typeof ner.top_p === 'number') settings.nerTopP = ner.top_p
    if (typeof ner.max_tokens === 'number') settings.nerMaxOut = ner.max_tokens
    if (typeof ner.max_context_tokens === 'number') settings.nerMaxCtx = ner.max_context_tokens
  }
  const icl = adv.icl_embedding_config
  if (icl) {
    if (typeof icl.top_k === 'number') settings.recallSqlMax = icl.top_k
    if (typeof icl.threshold === 'number') settings.recallSqlThreshold = icl.threshold
  }

  const sql = adv.nl2sql_config
  if (sql) {
    if (sql.prompt != null) settings.sqlPrompt = sql.prompt
    if (typeof sql.temperature === 'number') settings.sqlTemperature = sql.temperature
    if (typeof sql.top_k === 'number') settings.sqlTopK = sql.top_k
    if (typeof sql.top_p === 'number') settings.sqlTopP = sql.top_p
    if (typeof sql.max_tokens === 'number') settings.sqlMaxOut = sql.max_tokens
    if (typeof sql.max_context_tokens === 'number') settings.sqlMaxCtx = sql.max_context_tokens
  }

  const sqlPerm = adv.sql_permission_rewrite_config
  if (sqlPerm) {
    if (typeof sqlPerm.enable === 'boolean') settings.sqlPermissionRewriteEnabled = sqlPerm.enable
    settings.sqlPermissionRewriteAgentId = sqlPerm.target_app_id ?? null
    settings.sqlPermissionRewriteVersionId = sqlPerm.target_version_id ?? null
  }

  const sum = adv.bi_summary_config
  if (sum) {
    if (typeof sum.enable === 'boolean') settings.summaryEnabled = sum.enable
    if (sum.prompt != null) settings.summaryPrompt = sum.prompt
    if (typeof sum.temperature === 'number') settings.summaryTemperature = sum.temperature
    if (typeof sum.top_k === 'number') settings.summaryTopK = sum.top_k
    if (typeof sum.top_p === 'number') settings.summaryTopP = sum.top_p
    if (typeof sum.max_tokens === 'number') settings.summaryMaxOut = sum.max_tokens
    if (typeof sum.max_context_tokens === 'number') settings.summaryMaxCtx = sum.max_context_tokens
  }

  const chart = adv.chart_drawing_config
  if (chart) {
    if (typeof chart.enable === 'boolean') settings.chartEnabled = chart.enable
    if (chart.prompt != null) settings.chartPrompt = chart.prompt
    if (typeof chart.temperature === 'number') settings.chartTemperature = chart.temperature
    if (typeof chart.top_k === 'number') settings.chartTopK = chart.top_k
    if (typeof chart.top_p === 'number') settings.chartTopP = chart.top_p
    if (typeof chart.max_tokens === 'number') settings.chartMaxOut = chart.max_tokens
    if (typeof chart.max_context_tokens === 'number') settings.chartMaxCtx = chart.max_context_tokens
  }
}
