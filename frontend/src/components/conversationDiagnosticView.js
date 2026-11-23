// Presentation only. Captured inputs and request evidence remain untouched.
const equal = (left, right) => JSON.stringify(left) === JSON.stringify(right)

export function compactInputs(inputs = {}) {
  const values = { ...inputs }
  const aliases = []
  const alias = (name, canonical) => {
    if (name in values && canonical in values && equal(values[name], values[canonical])) {
      aliases.push({ field: name, same_as: canonical })
      delete values[name]
    }
  }
  if ('input' in values) {
    for (const name of ['question', 'message', 'user_message']) alias(name, 'input')
  }
  alias('conversation_history', 'history')
  if (Array.isArray(values.history_messages)) {
    for (const name of ['history', 'conversation_history']) {
      try {
        if (name in values && equal(JSON.parse(values[name]), values.history_messages)) {
          aliases.push({ field: name, same_as: 'history_messages（JSON 文本）' })
          delete values[name]
        }
      } catch { /* A business string is not assumed to be JSON. */ }
    }
  }
  if (values.features && typeof values.features === 'object' && !Array.isArray(values.features)) {
    const features = { ...values.features }
    for (const key of Object.keys(features)) {
      if (key !== 'features' && key in inputs && equal(features[key], inputs[key])) {
        aliases.push({ field: `features.${key}`, same_as: key })
        delete features[key]
      }
    }
    if (Object.keys(features).length) values.features = features
    else delete values.features
  }
  const compatibilityContext = {}
  for (const key of ['history_messages', 'history', 'conversation_history']) {
    if (key in values) {
      compatibilityContext[key] = values[key]
      delete values[key]
    }
  }
  return { values, aliases, compatibilityContext }
}

export function analysisCalls(invocations = []) {
  const calls = []
  for (const call of (invocations || []).filter(item => item.kind !== 'model')) {
    const previous = calls.at(-1)
    // These are two capture boundaries of the same root execution. Never merge
    // different child traces or repeated provider requests with equal inputs.
    if (call.kind === 'workflow' && previous?.kind === 'agent' &&
        call.app_id === previous.app_id && call.version_id === previous.version_id &&
        equal(call.inputs, previous.inputs)) {
      calls[calls.length - 1] = { ...call, combined_root_capture: true }
    } else calls.push(call)
  }
  return calls.map(call => ({ ...call, compact: compactInputs(call.inputs) }))
}

export const inputUseLabel = value => ({
  referenced: '画布引用（静态）', declared: '入口声明', possible_context: '可能由上下文或下游使用',
})[value] || '尚未采集'
