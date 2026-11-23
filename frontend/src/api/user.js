import request from '../utils/request'

export function getCurrentUser() {
  return request({ url: '/users/current', method: 'get' })
}

export function getUsers(params = {}) {
  return request({ url: '/users', method: 'get', params })
}

export function getUser(userId) {
  return request({ url: `/users/${userId}`, method: 'get' })
}

export function createUser(data) {
  return request({ url: '/users', method: 'post', data })
}

export function updateUser(userId, data) {
  return request({ url: `/users/${userId}`, method: 'put', data })
}

export function deleteUser(userId) {
  return request({ url: `/users/${userId}`, method: 'delete' })
}
