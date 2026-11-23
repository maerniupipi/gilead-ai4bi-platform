import request from '../utils/request'

/**
 * 获取所有模型供应商
 */
export function getModelProviders(params) {
  return request({
    url: '/model-providers',
    method: 'get',
    params
  })
}

/**
 * 获取单个模型供应商
 */
export function getModelProvider(id) {
  return request({
    url: `/model-providers/${id}`,
    method: 'get'
  })
}

/**
 * 创建模型供应商
 */
export function createModelProvider(data) {
  return request({
    url: '/model-providers',
    method: 'post',
    data
  })
}

/**
 * 更新模型供应商
 */
export function updateModelProvider(id, data) {
  return request({
    url: `/model-providers/${id}`,
    method: 'put',
    data
  })
}

/**
 * 删除模型供应商
 */
export function deleteModelProvider(id) {
  return request({
    url: `/model-providers/${id}`,
    method: 'delete'
  })
}

/**
 * 测试模型连接
 */
export function testModel(data) {
  return request({
    url: '/model-providers/test',
    method: 'post',
    data
  })
}
