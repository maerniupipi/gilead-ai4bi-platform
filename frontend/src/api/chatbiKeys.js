import request from '@/utils/request'

export const listChatBIKeys = () => request({ url: '/chatbi/keys', method: 'get' })
export const chatBIWorkflowOptions = () => request({ url: '/chatbi/keys/workflow-options', method: 'get' })
export const createChatBIKey = data => request({ url: '/chatbi/keys', method: 'post', data })
export const updateChatBIKey = (id, data) => request({ url: `/chatbi/keys/${id}`, method: 'put', data })
export const setChatBIKeyEnabled = (id, enabled) => request({ url: `/chatbi/keys/${id}/enabled`, method: 'patch', data: { enabled } })
