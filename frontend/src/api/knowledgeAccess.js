import request from '@/utils/request'

export default {
  // 创建知识接入
  createKnowledgeAccess(data) {
    return request({
      url: '/knowledge_access',
      method: 'post',
      data
    })
  },
  
  // 获取知识接入列表
  getKnowledgeAccessList(params) {
    return request({
      url: '/knowledge_access',
      method: 'get',
      params
    })
  },
  
  // 获取单个知识接入
  getKnowledgeAccess(knowledgeAccessId) {
    return request({
      url: `/knowledge_access/${knowledgeAccessId}`,
      method: 'get'
    })
  },
  
  // 更新知识接入
  updateKnowledgeAccess(knowledgeAccessId, data) {
    return request({
      url: `/knowledge_access/${knowledgeAccessId}`,
      method: 'put',
      data
    })
  },
  
  // 删除知识接入
  deleteKnowledgeAccess(knowledgeAccessId) {
    return request({
      url: `/knowledge_access/${knowledgeAccessId}`,
      method: 'delete'
    })
  },

  // 检查知识接入是否被知识库引用
  checkKbRefs(knowledgeAccessId) {
    return request({
      url: `/knowledge_access/${knowledgeAccessId}/check_kb_refs`,
      method: 'get'
    })
  }
}
