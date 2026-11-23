/**
 * 合并实验中心实验室配置：项目 config_json 覆盖默认 autobiconfig。
 */

function isPlainObject(x) {
  return x !== null && typeof x === 'object' && !Array.isArray(x)
}

export function deepMergeAutobiLab(base, override) {
  if (!isPlainObject(base)) return override ?? base
  if (!isPlainObject(override)) return base
  const out = { ...base }
  for (const k of Object.keys(override)) {
    const bv = base[k]
    const ov = override[k]
    if (isPlainObject(bv) && isPlainObject(ov)) {
      out[k] = deepMergeAutobiLab(bv, ov)
    } else {
      out[k] = ov
    }
  }
  return out
}

function cloneCfg(obj) {
  return JSON.parse(JSON.stringify(obj))
}

export function mergeAutobiLabConfig(defaultConfig, projectConfigJson) {
  if (!projectConfigJson || typeof projectConfigJson !== 'object') {
    return cloneCfg(defaultConfig)
  }
  return deepMergeAutobiLab(cloneCfg(defaultConfig), projectConfigJson)
}
