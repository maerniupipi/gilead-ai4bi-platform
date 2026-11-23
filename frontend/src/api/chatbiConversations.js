import request from '@/utils/request'

export const listChatBIConversations = params => request({ url: '/chatbi/conversations', method: 'get', params })
export const getChatBIConversation = (id, params) => request({ url: `/chatbi/conversations/${id}`, method: 'get', params })
