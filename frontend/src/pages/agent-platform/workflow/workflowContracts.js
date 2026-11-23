import { ATOMIC_CAPABILITIES } from './atomicCapabilities.js'

export const LAB_OUTPUT_FIELDS = Object.freeze(['trace_id', 'summary', 'sql', 'error'])

/** Shared editor/debug contracts. Keep identifiers aligned with executor results. */
export const LLM_OUTPUT_FIELDS = [{ variable: 'text', type: 'STRING', description: '模型生成的文本' }]

const PYTHON_KEYWORDS = new Set('False None True and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield'.split(' '))
export function isValidScriptInputName(name) {
  // Python uses Unicode XID identifiers; Chinese parameters are valid. The
  // restricted runtime additionally disallows names beginning with underscore.
  return typeof name === 'string' && /^\p{XID_Start}\p{XID_Continue}*$/u.test(name) && !PYTHON_KEYWORDS.has(name)
}

export function formatWorkflowValue(value) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function workflowOutputText(output) {
  if (output && typeof output === 'object' && !Array.isArray(output)) {
    if (output.content != null) return formatWorkflowValue(output.content)
    if (output.text != null) return formatWorkflowValue(output.text)
  }
  return formatWorkflowValue(output)
}

export function typedConstant(value, type = 'string') {
  const t = String(type).toLowerCase()
  if (t === 'string') return formatWorkflowValue(value)
  if (value == null) return value
  let parsed = value
  if (typeof value === 'string') {
    try { parsed = JSON.parse(value) } catch { throw new Error('请填写有效的 JSON 值') }
  }
  if (t === 'number' && (typeof parsed !== 'number' || !Number.isFinite(parsed))) throw new Error('请填写数字')
  if (['boolean', 'bool'].includes(t) && typeof parsed !== 'boolean') throw new Error('布尔值请填写 true 或 false')
  if (t === 'object' && (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))) throw new Error('对象请填写 JSON 对象，如 {"key":"value"}')
  if (t.startsWith('array_') || t.startsWith('list<') || t === 'array') {
    if (!Array.isArray(parsed)) throw new Error('列表请填写 JSON 数组，如 [1,2]')
    const subtype = t.startsWith('array_') ? t.slice(6) : t.startsWith('list<') ? (t.slice(5, -1) === 'bool' ? 'boolean' : t.slice(5, -1)) : ''
    if (subtype) for (const item of parsed) {
      if (subtype === 'string' && typeof item !== 'string') throw new Error('列表元素必须为文本')
      const actual = typedConstant(item, subtype)
      if (typeof actual !== typeof item) throw new Error(`列表元素必须符合 ${subtype} 类型`)
    }
  }
  return parsed
}

export function constantPlaceholder(type) {
  const t = String(type || 'string').toLowerCase()
  if (t === 'number') return '数字，如 0 或 3.14'
  if (['boolean', 'bool'].includes(t)) return 'true 或 false'
  if (t === 'object') return 'JSON 对象，如 {"key":"value"}'
  if (t.startsWith('array_') || t.startsWith('list<') || t === 'array') return 'JSON 数组，如 [1,2]'
  return '文本常量（允许空文本）'
}

export function nodeOutputOptions(node, atomicOutputs = []) {
  const d = node?.data || {}
  const prefix = String(d.label || d.var_name || node.id || '').trim()
  let keys = []
  switch (d.kind) {
    case 'userInput': keys = (d.fields || []).map(f => f.variable); break
    case 'llm': keys = ['text']; break
    case 'script': keys = (d.script_config?.output_vars || []).map(f => f.name); break
    case 'lab': keys = d.lab_config?.output_vars?.length ? d.lab_config.output_vars.map(item => typeof item === 'object' ? item?.key : item) : LAB_OUTPUT_FIELDS; break
    case 'atomic': keys = atomicOutputs.map(f => f.key); break
    case 'agent': keys = d.agent_config?.output_mapping?.length ? d.agent_config.output_mapping.map(f => f.target_var) : ['output', 'content']; break
    case 'externalApi': keys = ['status_code', 'response_body', ...(d.api_config?.output_vars || []).map(f => f.name)]; break
    case 'selector': keys = ['branch_handle', 'matched']; break
    case 'output': keys = ['content', 'metadata']; break
  }
  return [...new Set(keys.filter(Boolean))].map(key => ({ value: `${prefix}.${key}`, label: `${prefix}.${key}` }))
}

/** Rewrite references only: never rewrite user text, scripts, or constant payloads. */
export function renameNodeReferences(nodes, oldLabel, newLabel) {
  const namespaces = [...new Set([oldLabel, ...nodes.flatMap(node => [node.data?.label, node.data?.var_name]).filter(Boolean)])].sort((a, b) => b.length - a.length)
  const rewriteRef = value => {
    if (typeof value !== 'string') return value
    const owner = namespaces.find(name => value.startsWith(`${name}.`))
    return owner === oldLabel ? newLabel + value.slice(oldLabel.length) : value
  }
  const rewriteTemplate = value => typeof value === 'string' ? value.replace(/\{\{\s*([^{}]+?)\s*\}\}/g, (match, ref) => ref.startsWith(`${oldLabel}.`) ? `{{${rewriteRef(ref)}}}` : match) : value
  const referenceKeys = new Set(['ref', 'source_ref', 'source_var', 'content_ref'])
  const templateKeys = new Set(['system_prompt', 'user_prompt', 'content_template', 'body_template', 'base_url', 'path', 'output_template'])
  function visit(value, key = '', parent = '') {
    if (Array.isArray(value)) return value.map(item => key === 'context_vars' && typeof item === 'string' ? rewriteRef(item) : visit(item, '', key))
    if (!value || typeof value !== 'object') {
      if (referenceKeys.has(key)) return rewriteRef(value)
      if (templateKeys.has(key) || (key === 'value' && ['headers', 'query'].includes(parent))) return rewriteTemplate(value)
      return value
    }
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, visit(v, k, parent)]))
  }
  return nodes.map(node => ({ ...node, data: visit(node.data) }))
}

export function nodeConfigurationIssues(node) {
  const d = node?.data || {}
  const issues = []
  const names = (rows, key, title) => {
    const values = (rows || []).map(row => String(row[key] || '').trim())
    if (values.some(name => !name)) issues.push(`${title}名称不能为空`)
    if (new Set(values).size !== values.length) issues.push(`${title}名称不能重复`)
    if (values.some(name => name.includes('.'))) issues.push(`${title}名称不能包含点号（点号用于引用路径）`)
  }
  const refs = (rows, key) => (rows || []).forEach(row => {
    if (row.source_mode === 'ref' && !String(row[key] || '').trim()) issues.push(`请为「${row.name || row.variable || row.target_field || row.key || '参数'}」选择引用变量`)
  })
  if (d.kind === 'userInput') {
    names(d.fields, 'variable', '输入字段')
    for (const field of d.fields || []) {
      if (field.source_mode !== 'ref' && field.default != null && field.default !== '') {
        try { typedConstant(field.default, field.type) } catch (e) { issues.push(`「${field.variable}」默认值：${e.message}`) }
      }
    }
  }
  if (d.kind === 'llm') {
    if (!d.llm_config?.provider_id || !d.llm_config?.model_name) issues.push('请选择模型供应商和模型')
    names(d.llm_config?.input_params, 'variable', '输入参数')
    refs(d.llm_config?.input_params, 'ref')
  }
  if (d.kind === 'script') {
    const cfg = d.script_config || {}
    if (!String(cfg.code || '').trim()) issues.push('请编写 Python 脚本')
    names(cfg.input_vars, 'name', '输入变量')
    names(cfg.output_vars, 'name', '输出变量')
    for (const row of cfg.input_vars || []) {
      if (!isValidScriptInputName(row.name)) issues.push(`输入变量「${row.name || ''}」须为有效 Python 参数名，不能以下划线或数字开头，也不能使用 Python 关键字；支持中文名称`)
      if (row.source_mode === 'const') {
        try { typedConstant(row.const_value, row.type) } catch (e) { issues.push(`「${row.name}」：${e.message}`) }
      }
    }
  }
  if (d.kind === 'agent') {
    if (!d.agent_config?.target_app_id) issues.push('请选择要调用的工作流')
    names(d.agent_config?.input_mapping, 'target_field', '入参')
    names(d.agent_config?.output_mapping, 'target_var', '返回参数')
  }
  if (d.kind === 'lab' && !d.lab_config?.project_id) issues.push('请选择实验室项目')
  if (d.kind === 'atomic') {
    const cfg = d.atomic_config || {}
    const spec = ATOMIC_CAPABILITIES.find(item => item.value === cfg.capability)
    if (!spec) issues.push('请选择有效的原子能力')
    else {
      const rows = new Map((cfg.input_vars || []).map(row => [row.key, row]))
      for (const field of spec.inputs) {
        const row = rows.get(field.key)
        if (row?.source_mode === 'ref') {
          if (!String(row.source_ref || row.ref || '').trim()) issues.push(`请为「${field.label}」选择引用变量`)
          continue
        }
        const raw = row?.const_value
        if (raw == null || (typeof raw === 'string' && !raw.trim())) {
          if (field.required) issues.push(`请填写「${field.label}」（必填）`)
          continue
        }
        // Template values are typed after resolution; KB IDs only support explicit refs.
        if (field.key !== 'knowledge_base_id' && typeof raw === 'string' && raw.includes('{{')) continue
        try {
          const isNull = raw === 'null' || raw === null
          if (isNull && field.nullable) continue
          const value = typedConstant(raw, field.type)
          if (field.integer && !Number.isInteger(value)) throw new Error('请填写整数')
          if (field.min != null && value < field.min) throw new Error(`不能小于 ${field.min}`)
          if (field.max != null && value > field.max) throw new Error(`不能大于 ${field.max}`)
          if (field.minItems && (!Array.isArray(value) || value.length < field.minItems || value.some(item => typeof item === 'string' && !item.trim()))) throw new Error('请填写至少一个非空列表项')
        } catch (e) { issues.push(`「${field.label}」：${e.message}`) }
      }
    }
  }
  if (d.kind === 'externalApi') {
    const cfg = d.api_config || {}
    if (!cfg.base_url) issues.push('请填写 Base URL')
    else if (!cfg.base_url.includes('{{') && !/^https?:\/\//i.test(cfg.base_url)) issues.push('Base URL 须以 http:// 或 https:// 开头')
    names(cfg.output_vars, 'name', '返回参数')
    if ((cfg.output_vars || []).some(row => !row.json_path)) issues.push('请填写返回参数的 JSON Path')
  }
  if (d.kind === 'output') {
    const cfg = d.output_config || {}
    refs(cfg.content_fields, 'source_ref')
    refs(cfg.metadata_fields, 'source_ref')
    names(cfg.metadata_fields, 'name', '元数据')
    for (const row of cfg.metadata_fields || []) {
      if (row.source_mode === 'const') {
        try { typedConstant(row.const_value, row.type) } catch (e) { issues.push(`「${row.name}」：${e.message}`) }
      }
    }
  }
  if (d.kind === 'selector') {
    for (const row of d.selector_config?.cases || []) {
      if (!(row.conditions || []).length || row.conditions.some(c => !c.ref)) issues.push('请为每个条件选择引用变量')
    }
  }
  return [...new Set(issues)]
}

export function buildDebugInputs({ nodes, text, json, jsonMode }) {
  const input = nodes.find(n => n.data?.kind === 'userInput')
  const fields = input?.data?.fields?.length ? input.data.fields : [{ variable: 'input', required: true, type: 'string' }]
  let values
  if (jsonMode) {
    try { values = JSON.parse(json) } catch { throw new Error('JSON 格式无效，请填写对象，如 {"input":"你好"}') }
    if (!values || typeof values !== 'object' || Array.isArray(values)) throw new Error('JSON 须为对象，如 {"input":"你好"}')
  } else {
    const field = fields.find(f => !f.hidden) || fields[0]
    values = {}
    if (text !== '') values[field.variable] = typedConstant(text, field.type)
  }
  for (const field of fields) {
    const name = field.variable
    let value = Object.hasOwn(values, name) ? values[name] : field.default
    if (!Object.hasOwn(values, name) && field.source_mode === 'ref' && Array.isArray(field.source_ref)) value = values[field.source_ref[1]]
    if (field.required && (value == null || value === '')) throw new Error(`请填写「${field.display || name}」${jsonMode ? '' : '；多个必填字段请切换 JSON 输入'}`)
    if (Object.hasOwn(values, name)) values[name] = typedConstant(values[name], field.type)
  }
  return values
}
