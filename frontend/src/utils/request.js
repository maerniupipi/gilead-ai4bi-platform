import axios from 'axios'
import { getUserIdFromToken, getCurrentSpaceId, getCurrentUser } from './auth'

/**
 * 统一响应码（与后端 core/response.py 保持同步）
 */
export const ResponseCode = {
  SUCCESS: 'SUCCESS',
  NOT_FOUND: 'NOT_FOUND',
  BAD_REQUEST: 'BAD_REQUEST',
  DUPLICATE: 'DUPLICATE',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
  UNAUTHORIZED: 'UNAUTHORIZED',
  FORBIDDEN: 'FORBIDDEN',
  SERVER_ERROR: 'SERVER_ERROR',
}

const DEFAULT_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT_MS || 30000)
const service = axios.create({
  baseURL: `${(import.meta.env.BASE_URL || '/').replace(/\/+$/, '')}/api`,
  timeout: DEFAULT_TIMEOUT,
})

// 请求拦截器（可在此注入 Token 等认证头）
service.interceptors.request.use(
  config => {
    // 自动注入 user_id、username 和 space_id 到请求中
    const userId = getUserIdFromToken()
    const currentUser = getCurrentUser()
    const spaceId = getCurrentSpaceId()

    // 设置用户ID和用户名到header
    if (userId) {
      config.headers['X-User-Id'] = userId
    }
    if (currentUser?.username) {
      config.headers['X-Username'] = currentUser.username
    }

    // 自动注入 space_id 到 params（工具类接口不注入 space_id，保持通用）
    const isToolRoute = config.url?.startsWith('/xlsx-qa/') ||
                        config.url?.startsWith('/autobi/gateway') ||
                        config.url?.startsWith('/autobi/lab/') ||
                        config.url?.startsWith('/chat/')
    if (spaceId && !config.params && !isToolRoute) {
      config.params = { space_id: spaceId }
    } else if (spaceId && !isToolRoute) {
      config.params = { ...config.params, space_id: spaceId }
    }

    return config
  },
  error => Promise.reject(error)
)

/**
 * 响应拦截器
 * 后端统一返回格式：{ code: string, message: string, data: any }
 * - 成功：code === 'SUCCESS'，直接返回 data 字段，让调用方无感知
 * - 业务失败：构造 Error 并挂载 code / message，向上抛出
 * - HTTP 层失败：从 error.response.data 读取标准字段后抛出
 */
service.interceptors.response.use(
  response => {
    // 非 JSON 响应（Blob / ArrayBuffer / 文件下载等）直接返回 raw axios response
    const respType = response.config?.responseType
    if (respType && respType !== 'json') {
      return response
    }
    const { code, message, data } = response.data
    if (code === ResponseCode.SUCCESS) {
      return data
    }
    // 业务错误（如 NOT_FOUND / DUPLICATE 等），后端已返回 2xx 但 code 非 SUCCESS
    const err = new Error(message || '请求失败')
    err.code = code
    return Promise.reject(err)
  },
  error => {
    const isTimeout = error.code === 'ECONNABORTED'
    // HTTP 层错误（4xx / 5xx），后端已格式化为 {code, message, data}
    const resp = error.response?.data
    const message = resp?.message || (isTimeout ? '请求超时，请稍后重试' : error.message) || '网络错误'
    const code = resp?.code || 'ERROR'
    const err = new Error(message)
    err.code = code
    console.error(`[request] ${code}: ${message}`)
    return Promise.reject(err)
  }
)

export default service
