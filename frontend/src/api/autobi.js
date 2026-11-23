import request from '@/utils/request'

export function listAutobiFolders() {
  return request({ url: '/autobi/folders', method: 'get' })
}

export function createAutobiFolder(data) {
  return request({ url: '/autobi/folders', method: 'post', data })
}

export function updateAutobiFolder(id, data) {
  return request({ url: `/autobi/folders/${id}`, method: 'put', data })
}

export function deleteAutobiFolder(id) {
  return request({ url: `/autobi/folders/${id}`, method: 'delete' })
}

export function moveAutobiFolder(id, data) {
  return request({ url: `/autobi/folders/${id}/move`, method: 'post', data })
}

export function listAutobiProjects(params) {
  return request({ url: '/autobi/projects', method: 'get', params })
}

export function getAutobiProject(id) {
  return request({ url: `/autobi/projects/${id}`, method: 'get' })
}

export function exportAutobiProject(id) {
  return request({ url: `/autobi/projects/${id}/export`, method: 'get' })
}

export function importAutobiProject(data) {
  return request({ url: '/autobi/projects/import', method: 'post', data })
}

export function createAutobiProject(data) {
  return request({ url: '/autobi/projects', method: 'post', data })
}

export function updateAutobiProject(id, data) {
  return request({ url: `/autobi/projects/${id}`, method: 'put', data })
}

export function deleteAutobiProject(id) {
  return request({ url: `/autobi/projects/${id}`, method: 'delete' })
}

export function issueAutobiLabShare(id, rotate = false) {
  return request({ url: `/autobi/projects/${id}/share`, method: 'post', params: { rotate } })
}

export function revokeAutobiLabShare(id) {
  return request({ url: `/autobi/projects/${id}/share`, method: 'delete' })
}
