import request from '../utils/request'

export function getVectorStores(params) {
  return request({ url: '/vector-stores', method: 'get', params })
}

export function createVectorStore(data) {
  return request({ url: '/vector-stores', method: 'post', data })
}

export function updateVectorStore(id, data) {
  return request({ url: `/vector-stores/${id}`, method: 'put', data })
}

export function deleteVectorStore(id) {
  return request({ url: `/vector-stores/${id}`, method: 'delete' })
}

export function testVectorStore(data) {
  return request({ url: '/vector-stores/test', method: 'post', data })
}
