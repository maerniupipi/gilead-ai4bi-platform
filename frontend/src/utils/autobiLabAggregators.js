/**
 * 实验室流水线：原子能力结果 → Prompt 用自然语言 / 双路 ES query 等
 */

/** ES 知识词 → 自然语言键值对（供知识改写 prompt） */
export function buildKnowledgeWordsForPrompt(results) {
  const lines = []
  for (const r of results || []) {
    const term = (r.content || r.metadata?.data_detail || '').trim()
    if (!term) continue
    const explain = r.metadata?.quote_extend ?? r.metadata?.data_detail ?? ''
    lines.push(`「${term}」→ ${explain || '（无扩展说明）'}`)
  }
  return lines.join('\n')
}

/** 供双路 ES 长 query 的【】映射串 */
export function buildKnowledgeKnowledgeMapObject(results) {
  const o = {}
  for (const r of results || []) {
    const term = (r.content || r.metadata?.data_detail || '').trim()
    if (!term) continue
    const explain = r.metadata?.quote_extend ?? r.metadata?.data_detail ?? ''
    o[term] = explain || term
  }
  return o
}

export function buildLongEsQueryWithAnnotations(originalQuery, knowledgeMap) {
  const entries = Object.entries(knowledgeMap || {})
  if (!entries.length) return originalQuery
  const part = entries.map(([k, v]) => `【${k}】代表【${v}】`).join('、')
  return `${originalQuery} 其中，${part}`
}

/** 底层 field_code 多为「表&&字段」，写入 nl2sql 参考时展示为「表.字段」 */
export function formatRecallTableDotField(fieldTable, fieldCode, contentFallback = '') {
  const fc = String(fieldCode || '').trim()
  if (fc.includes('&&')) {
    const i = fc.indexOf('&&')
    const t = fc.slice(0, i).trim()
    const c = fc.slice(i + 2).trim()
    if (t && c) return `${t}.${c}`
  }
  const ft = String(fieldTable || '').trim()
  if (ft && fc && !fc.includes('&&')) return `${ft}.${fc}`
  return fc || String(contentFallback || '').trim() || ft || '?'
}

function fmtTableMeta(results) {
  return (results || [])
    .map(r => {
      const m = r.metadata || {}
      const ref = formatRecallTableDotField(m.field_table, m.field_code, r.content)
      return `- ${ref}：${m.field_value || r.content}`
    })
    .join('\n')
}

function fmtGenericRetriever(results, label) {
  return (results || [])
    .map(r => {
      const m = r.metadata || {}
      const ref = formatRecallTableDotField(m.field_table, m.field_code, '')
      return `- [${label}] ${r.content} | ${ref}`
    })
    .join('\n')
}

function formatStepResultItem(r, index) {
  if (r == null || typeof r !== 'object') return `${index + 1}. ${String(r)}`
  const m = r.metadata || {}
  const parts = []
  const content = r.content ?? m.field_value ?? m.data_detail
  if (content != null && String(content).trim()) parts.push(`内容：${String(content).trim()}`)
  const ref = formatRecallTableDotField(m.field_table, m.field_code, '')
  if (ref && ref !== '?') parts.push(`字段：${ref}`)
  if (m.query) parts.push(`问题：${m.query}`)
  if (m.answer) parts.push(`SQL：${m.answer}`)
  if (r.score != null) parts.push(`得分：${r.score}`)
  return `${index + 1}. ${parts.join('；') || JSON.stringify(r)}`
}

/** 将任一步骤返回转换为适合直接放进 Prompt 的自然语言文本。 */
export function buildStepResponseNlp(response, title = '') {
  if (response == null) return `${title ? `${title}：` : ''}无返回结果`
  if (typeof response !== 'object') return String(response)
  if (response.skipped) return `${title ? `${title}：` : ''}已跳过，原因：${response.reason || '未说明'}`

  const lines = []
  if (title) lines.push(`【${title}】`)
  if (Array.isArray(response.results)) {
    lines.push(`共召回 ${response.total ?? response.results.length} 条结果：`)
    lines.push(...response.results.map(formatStepResultItem))
  }
  if (Array.isArray(response.entities) && response.entities.length) {
    lines.push(`识别实体：${response.entities.join('、')}`)
  }
  if (response.narrative) lines.push(`说明：${response.narrative}`)
  if (response.rewritten_query) lines.push(`改写问题：${response.rewritten_query}`)
  if (response.sql) lines.push(`SQL：${response.sql}`)
  if (response.content && !Array.isArray(response.results)) lines.push(`内容：${response.content}`)
  if (Array.isArray(response.rows)) {
    lines.push(`查询结果：共 ${response.row_count ?? response.rows.length} 行`)
    lines.push(JSON.stringify({ columns: response.columns || [], rows: response.rows }, null, 2))
  }
  if (response.chart_spec) lines.push(`图表配置：${JSON.stringify(response.chart_spec, null, 2)}`)
  return lines.length > (title ? 1 : 0) ? lines.join('\n') : JSON.stringify(response, null, 2)
}

/**
 * 每步完成后写入运行时 features。
 * 无步骤号键表示最近一次同 api_key 的结果；带步骤号键可稳定区分重复 api_key。
 */
export function buildStepFeatureValues(meta, response) {
  const apiKey = String(meta?.apiKey || `step-${meta?.stepId || 'unknown'}`)
  const stepPrefix = `step_${meta?.stepId}_${apiKey}`
  const result = JSON.stringify(response ?? {}, null, 2)
  const nlp = buildStepResponseNlp(response, meta?.title || apiKey)
  return {
    [`${apiKey}_result`]: result,
    [`${apiKey}_nlp`]: nlp,
    [`${stepPrefix}_result`]: result,
    [`${stepPrefix}_nlp`]: nlp
  }
}

/** 第 6/7 步去重 field_table，供表值按表并行 */
export function collectFieldTablesFromMetaSteps(byStep) {
  const seen = new Set()
  const out = []
  for (const sid of [6, 7]) {
    const res = byStep[sid]?.response
    for (const r of res?.results || []) {
      const ft = (r.metadata?.field_table || '').trim()
      if (ft && !seen.has(ft)) {
        seen.add(ft)
        out.push(ft)
      }
    }
  }
  return out
}

/** 第 6/7 步去重 field_code，供多列同值 */
export function collectFieldCodesForMultiColumn(byStep) {
  const seen = new Set()
  const out = []
  for (const sid of [6, 7]) {
    const res = byStep[sid]?.response
    for (const r of res?.results || []) {
      const fc = (r.metadata?.field_code || '').trim()
      if (fc && !seen.has(fc)) {
        seen.add(fc)
        out.push(fc)
      }
    }
  }
  return out
}

/** nl2sql：{{ table_field_prompt_data }} — ⑥⑦⑨ + ⑪ 或 ⑫（不含 SQL 样例） */
export function buildTableFieldPromptData(byStep) {
  const parts = []
  const s6 = byStep[6]?.response
  const s7 = byStep[7]?.response
  const s9 = byStep[9]?.response
  const s11 = byStep[11]?.response || {}
  const s12 = byStep[12]?.response || {}
  if (s6?.results?.length) parts.push('【表字段召回 table-meta】\n' + fmtTableMeta(s6.results))
  if (s7?.results?.length) parts.push('【表值(对应字段) global-value-meta】\n' + fmtGenericRetriever(s7.results, '值'))
  if (s9?.results?.length) parts.push('【ES 表值（双次检索合并）】\n' + fmtGenericRetriever(s9.results, 'ES'))
  if (!s12.skipped && s12.results?.length) {
    parts.push('【多列同值召回 multi-global-value-meta】\n' + fmtGenericRetriever(s12.results, '值'))
  } else if (!s11.skipped && s11.results?.length) {
    parts.push('【表值召回 table-value】\n' + fmtGenericRetriever(s11.results, '值'))
  }
  return parts.join('\n\n') || '（暂无召回结果）'
}

function fmtSqlTemplate(results) {
  return (results || [])
    .map(r => {
      const m = r.metadata || {}
      const q = m.query || r.content
      const a = m.answer || ''
      return `- 问：${q}\n  SQL：${a}`
    })
    .join('\n')
}

/** nl2sql：{{ icl_example_prompt_data }} — 文档第 8 步（SQL 样例召回） */
export function buildIclExamplePromptData(byStep) {
  const s8 = byStep[8]?.response
  if (!s8?.results?.length) return ''
  return fmtSqlTemplate(s8.results)
}

/**
 * 将请求体 features 中与占位符同名的 {{ key }}（可含过滤器前缀段，仅取首段键名）替换为字符串值。
 * 未出现在 features 中的占位符保持不动，留给后续 replaceTemplateVars。
 */
export function replaceFeaturesInTemplate(template, features) {
  if (!template || !features || typeof features !== 'object') return template
  return String(template).replace(/\{\{\s*([^}]+?)\s*\}\}/g, (match, raw) => {
    const base = String(raw)
      .trim()
      .split('|')[0]
      .trim()
      .split('.')[0]
      .trim()
    if (Object.prototype.hasOwnProperty.call(features, base)) {
      const v = features[base]
      return v == null ? '' : String(v)
    }
    return match
  })
}

/** 对 labConfig.request.advanced_config 下各块含 prompt 的字符串做 features 预替换（深拷贝后返回新配置） */
export function applyFeaturesToLabConfigPrompts(labConfig, features) {
  if (!labConfig || !features || typeof features !== 'object' || !Object.keys(features).length) {
    return labConfig
  }
  const cfg = JSON.parse(JSON.stringify(labConfig))
  const adv = cfg?.request?.advanced_config
  if (!adv || typeof adv !== 'object') return cfg
  for (const block of Object.values(adv)) {
    if (block && typeof block === 'object' && typeof block.prompt === 'string') {
      block.prompt = replaceFeaturesInTemplate(block.prompt, features)
    }
  }
  return cfg
}

/** 简单替换 {{ key }}（空格可选），不做 Jinja */
export function replaceTemplateVars(template, vars) {
  if (!template) return ''
  let s = template
  for (const [k, v] of Object.entries(vars)) {
    const re = new RegExp(`\\{\\{\\s*${k}\\s*\\}\\}`, 'g')
    s = s.replace(re, v == null ? '' : String(v))
  }
  return s
}

/** 去掉配置里遗留的 Jinja 标记（实验室前端不做模板引擎解析） */
export function stripLabTemplateNoise(s) {
  if (!s) return ''
  return String(s)
    .replace(/\{%\s*raw\s*%\}/gi, '')
    .replace(/\{%\s*endraw\s*%\}/gi, '')
    .split('\n')
    .filter(line => !/^\s*\{%/.test(line))
    .join('\n')
}

/** 从模型输出取 SQL（去 markdown 围栏） */
export function extractSqlFromModelText(text) {
  if (!text) return ''
  const t = text.trim()
  const block = t.match(/```(?:sql)?\s*([\s\S]*?)```/i)
  if (block) return block[1].trim()
  return t
}

/** 改写结果归一化：none / 空 → 用原问题 */
export function normalizeRewrittenQuery(raw, originalQuery) {
  const x = (raw || '').trim()
  if (!x || /^none$/i.test(x)) return originalQuery
  return x
}

/** 解析 NER 模型 JSON 输出中的 ner 数组 */
export function parseNerEntitiesFromLlm(text) {
  if (!text || !String(text).trim()) return []
  let t = String(text).trim()
  const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fence) t = fence[1].trim()
  const brace = t.match(/\{[\s\S]*\}/)
  if (!brace) return []
  try {
    const obj = JSON.parse(brace[0])
    const ner = obj.ner
    if (!Array.isArray(ner)) return []
    return ner.map(x => String(x).trim()).filter(Boolean)
  } catch {
    return []
  }
}

/**
 * 数据总结：配置里含 Jinja，浏览器端用「问题 + SQL + 占位执行结果」拼一条可执行消息，
 * 并尽量保留配置中「步骤说明」段落（去掉明显 Jinja 控制块行）。
 */
/** 将 execute_sql 接口返回格式化为数据总结用的参考文本 */
export function formatSqlExecuteResultForSummary(res) {
  if (!res) return '（无执行结果）'
  if (res.skipped) return res.reason || '（跳过 SQL 执行）'
  const { columns = [], rows = [], row_count = 0 } = res
  try {
    return JSON.stringify({ columns, rows, row_count }, null, 2)
  } catch {
    return String(rows)
  }
}

export function buildBiSummaryUserMessage(template, { originalQuery, executeSql, sqlDataText }) {
  const sql = executeSql || '无'
  const data = sqlDataText ?? '（占位）10000元'
  let head = template || ''
  head = head.replace(/\{\{\s*rewrite_query\s*\}\}/g, originalQuery)
  head = head.replace(/\{\{[\s\S]*?\}\}/g, '')
  head = head.split('\n').filter(line => !/^\s*\{%/.test(line)).join('\n')
  const body = `\n\n----------\n问题（用户原始）：\n${originalQuery}\n\n查询的 SQL：\n${sql}\n\nSQL 执行结果：\n${data}\n\n请严格依据上述参考信息作答。`
  return (head.trim() + body).trim()
}
