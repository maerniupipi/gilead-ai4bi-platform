import request from '../utils/request'

/**
 * 全量覆盖写入实验室追踪（Redis key 由后端按 trace_id 生成）
 * @param {string} traceId
 * @param {object} body snake_case 字段，与后端 AutobiLabTraceUpsert 一致
 */
export function putAutobiLabTrace(traceId, body) {
  return request({
    url: `/autobi/lab/traces/${encodeURIComponent(traceId)}`,
    method: 'put',
    data: body
  })
}

export function getAutobiLabTrace(traceId) {
  return request({
    url: `/autobi/lab/traces/${encodeURIComponent(traceId)}`,
    method: 'get'
  })
}
