import request from '@/utils/request'

/** 实验室对话状态（MySQL）；流水线 trace 仍走 autobiLabTrace（Redis） */
export function getAutobiLabChatState(projectId) {
  return request({
    url: `/autobi/projects/${projectId}/lab/chat-state`,
    method: 'get',
    timeout: 30000
  })
}

export function putAutobiLabChatState(projectId, body) {
  return request({
    url: `/autobi/projects/${projectId}/lab/chat-state`,
    method: 'put',
    data: body,
    timeout: 60000
  })
}
