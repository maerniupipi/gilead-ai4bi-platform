import request from '../utils/request'

export function getEsConfigs(params) {
  return request({ url: '/es-configs', method: 'get', params })
}

export function getDefaultEsConfig() {
  return request({ url: '/es-configs/default', method: 'get' })
}

export function createEsConfig(data) {
  return request({ url: '/es-configs', method: 'post', data })
}

export function updateEsConfig(id, data) {
  return request({ url: `/es-configs/${id}`, method: 'put', data })
}

export function deleteEsConfig(id) {
  return request({ url: `/es-configs/${id}`, method: 'delete' })
}

export function testEsConfig(data) {
  return request({ url: '/es-configs/test', method: 'post', data })
}