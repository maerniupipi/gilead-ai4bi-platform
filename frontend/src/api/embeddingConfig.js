import request from '../utils/request'

export function getEmbeddingConfigs(params) {
  return request({ url: '/embedding-configs', method: 'get', params })
}

export function getDefaultEmbeddingConfig() {
  return request({ url: '/embedding-configs/default', method: 'get' })
}

export function createEmbeddingConfig(data) {
  return request({ url: '/embedding-configs', method: 'post', data })
}

export function updateEmbeddingConfig(id, data) {
  return request({ url: `/embedding-configs/${id}`, method: 'put', data })
}

export function deleteEmbeddingConfig(id) {
  return request({ url: `/embedding-configs/${id}`, method: 'delete' })
}