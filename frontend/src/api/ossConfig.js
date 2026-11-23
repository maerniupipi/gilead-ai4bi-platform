import request from '../utils/request'

export function getOssConfigs(params) {
  return request({ url: '/oss-configs', method: 'get', params })
}

export function createOssConfig(data) {
  return request({ url: '/oss-configs', method: 'post', data })
}

export function updateOssConfig(id, data) {
  return request({ url: `/oss-configs/${id}`, method: 'put', data })
}

export function deleteOssConfig(id) {
  return request({ url: `/oss-configs/${id}`, method: 'delete' })
}

export function testOssConfig(data) {
  return request({ url: '/oss-configs/test', method: 'post', data })
}
