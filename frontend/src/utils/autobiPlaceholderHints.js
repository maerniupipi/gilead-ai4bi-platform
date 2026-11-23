/**
 * 从任意 JSON 可序列化结构中收集 Jinja/模板占位符 `{{ name }}`
 * 用于提示 features（旧称 metadata）可传入的键名：与提示词中 {{键名}} 同名则预先替换。
 */
const PLACEHOLDER_RE = /\{\{\s*([^}]+?)\s*\}\}/g

export function collectTemplatePlaceholders(value, outSet = new Set()) {
  if (value == null) return outSet
  if (typeof value === 'string') {
    let m
    PLACEHOLDER_RE.lastIndex = 0
    while ((m = PLACEHOLDER_RE.exec(value)) !== null) {
      const raw = m[1].trim()
      if (!raw) continue
      const key = raw.split('|')[0].trim().split('.')[0].trim()
      if (key && /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(key)) {
        outSet.add(key)
      }
    }
    return outSet
  }
  if (Array.isArray(value)) {
    value.forEach(v => collectTemplatePlaceholders(v, outSet))
    return outSet
  }
  if (typeof value === 'object') {
    Object.values(value).forEach(v => collectTemplatePlaceholders(v, outSet))
  }
  return outSet
}

/**
 * @param {object} configJson — 项目 config_json
 * @returns {string[]}
 */
export function listPlaceholderKeysFromConfig(configJson) {
  if (!configJson || typeof configJson !== 'object') return []
  const runtimeKeys = new Set(['qs_recall'])
  return [...collectTemplatePlaceholders(configJson)].filter(key => !runtimeKeys.has(key)).sort()
}
