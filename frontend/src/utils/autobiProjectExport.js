/** 实验室配置文件校验；资源绑定的清空由服务端统一执行。 */
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value)

export function parseLabImportPayload(text) {
  const payload = JSON.parse(text.replace(/^\uFEFF/, ''))
  if (!isObject(payload) || payload.format !== 'chat-bi-lab-export') {
    throw new Error('请使用本系统导出的实验室 JSON 配置文件')
  }
  if (payload.formatVersion !== 1) throw new Error('不支持的实验室导出文件版本')
  if (!isObject(payload.project) || typeof payload.project.name !== 'string' || !payload.project.name.trim() ||
      payload.project.name.trim().length > 255 ||
      (payload.project.description != null && typeof payload.project.description !== 'string')) {
    throw new Error('无效的实验室名称或描述')
  }
  const config = payload.config_json
  if (!isObject(config) || !isObject(config.request)) {
    throw new Error('无效的实验室配置：缺少 request 对象')
  }
  const request = config.request
  if (request.advanced_config !== undefined && !isObject(request.advanced_config)) {
    throw new Error('无效的实验室配置：advanced_config 必须是对象')
  }
  if (request.messages !== undefined && (!Array.isArray(request.messages) || request.messages.some(message => !isObject(message)))) {
    throw new Error('无效的实验室配置：messages 必须是对象数组')
  }
  if (request.stream !== undefined && typeof request.stream !== 'boolean') {
    throw new Error('无效的实验室配置：stream 必须是布尔值')
  }
  if (config.model_bindings !== undefined && (!isObject(config.model_bindings) || Object.values(config.model_bindings).some(binding => !isObject(binding)))) {
    throw new Error('无效的实验室配置：model_bindings 必须是模型绑定对象')
  }
  return payload
}

export function suggestLabImportName(payload, projects = []) {
  const base = payload.project.name.trim().slice(0, 255)
  const names = new Set(projects.map(project => project.name))
  if (!names.has(base)) return base
  for (let index = 1; ; index++) {
    const suffix = index === 1 ? '-导入' : `-导入${index}`
    const name = base.slice(0, 255 - suffix.length) + suffix
    if (!names.has(name)) return name
  }
}
