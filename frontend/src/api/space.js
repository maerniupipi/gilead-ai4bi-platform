import request from '../utils/request'

export function getSpaces() {
  return request({ url: '/spaces', method: 'get' })
}

export function getAllSpaces() {
  return request({ url: '/spaces/all', method: 'get' })
}

export function createSpace(data) {
  return request({ url: '/spaces', method: 'post', data })
}

export function getSpace(spaceId) {
  return request({ url: `/spaces/${spaceId}`, method: 'get' })
}

export function updateSpace(spaceId, data) {
  return request({ url: `/spaces/${spaceId}`, method: 'put', data })
}

export function deleteSpace(spaceId, data) {
  return request({ url: `/spaces/${spaceId}`, method: 'delete', data })
}

export function cancelDeleteSpace(spaceId) {
  return request({ url: `/spaces/${spaceId}/cancel-delete`, method: 'post' })
}

export function switchSpace(spaceId) {
  return request({ url: `/spaces/switch/${spaceId}`, method: 'post' })
}

export function getCurrentSpace() {
  return request({ url: '/spaces/current', method: 'get' })
}

export function getSpaceMembers(spaceId) {
  return request({ url: `/spaces/${spaceId}/members`, method: 'get' })
}

export function addSpaceMember(spaceId, data) {
  return request({ url: `/spaces/${spaceId}/members`, method: 'post', data })
}

export function removeSpaceMember(spaceId, userId) {
  return request({ url: `/spaces/${spaceId}/members/${userId}`, method: 'delete' })
}
