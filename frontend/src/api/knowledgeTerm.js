import request from '@/utils/request'

export default {
  // 获取知识接入的词条列表（分页）
  getKnowledgeTerms(knowledgeAccessId, params) {
    return request({
      url: `/knowledge_term/knowledge_access/${knowledgeAccessId}`,
      method: 'get',
      params
    })
  },

  // 获取知识接入的全部词条（无分页，用于知识库选择词条）
  getAllKnowledgeTerms(knowledgeAccessId) {
    return request({
      url: `/knowledge_term/knowledge_access/${knowledgeAccessId}/all`,
      method: 'get'
    })
  },

  // 创建词条
  createKnowledgeTerm(knowledgeAccessId, data) {
    return request({
      url: `/knowledge_term?knowledge_access_id=${knowledgeAccessId}`,
      method: 'post',
      data
    })
  },
  
  // 更新词条
  updateKnowledgeTerm(knowledgeTermId, data) {
    return request({
      url: `/knowledge_term/${knowledgeTermId}`,
      method: 'put',
      data
    })
  },
  
  // 删除词条
  deleteKnowledgeTerm(knowledgeTermId) {
    return request({
      url: `/knowledge_term/${knowledgeTermId}`,
      method: 'delete'
    })
  },

  // 导出全部词条
  exportKnowledgeTerms(knowledgeAccessId) {
    return request({
      url: `/knowledge_term/knowledge_access/${knowledgeAccessId}/export`,
      method: 'get'
    })
  },

  // 导入词条
  importKnowledgeTerms(knowledgeAccessId, data) {
    return request({
      url: `/knowledge_term/knowledge_access/${knowledgeAccessId}/import`,
      method: 'post',
      data
    })
  }
}
