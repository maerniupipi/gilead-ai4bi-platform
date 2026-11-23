import request from '@/utils/request'

export default {
  // 获取知识接入的样例列表
  getSampleLibraries(knowledgeAccessId, params) {
    return request({
      url: `/sample_library/knowledge_access/${knowledgeAccessId}`,
      method: 'get',
      params
    })
  },
  
  // 创建样例
  createSampleLibrary(knowledgeAccessId, data) {
    return request({
      url: `/sample_library?knowledge_access_id=${knowledgeAccessId}`,
      method: 'post',
      data
    })
  },
  
  // 更新样例
  updateSampleLibrary(sampleLibraryId, data) {
    return request({
      url: `/sample_library/${sampleLibraryId}`,
      method: 'put',
      data
    })
  },
  
  // 删除样例
  deleteSampleLibrary(sampleLibraryId) {
    return request({
      url: `/sample_library/${sampleLibraryId}`,
      method: 'delete'
    })
  },

  // 导出全部样例
  exportSampleLibraries(knowledgeAccessId) {
    return request({
      url: `/sample_library/knowledge_access/${knowledgeAccessId}/export`,
      method: 'get'
    })
  },

  // 导入样例
  importSampleLibraries(knowledgeAccessId, data) {
    return request({
      url: `/sample_library/knowledge_access/${knowledgeAccessId}/import`,
      method: 'post',
      data
    })
  }
}
