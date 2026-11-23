import request from '@/utils/request'

const knowledgeBaseApi = {
  // 获取知识库列表
  getKnowledgeBaseList(params) {
    return request({
      url: '/knowledge_base',
      method: 'get',
      params
    })
  },
  
  // 获取单个知识库
  getKnowledgeBase(id) {
    return request({
      url: `/knowledge_base/${id}`,
      method: 'get'
    })
  },
  
  // 创建知识库
  createKnowledgeBase(data) {
    return request({
      url: '/knowledge_base',
      method: 'post',
      data
    })
  },
  
  // 更新知识库
  updateKnowledgeBase(id, data) {
    return request({
      url: `/knowledge_base/${id}`,
      method: 'put',
      data
    })
  },
  
  // 删除知识库
  deleteKnowledgeBase(id) {
    return request({
      url: `/knowledge_base/${id}`,
      method: 'delete'
    })
  },

  // 检查知识库是否被实验中心项目引用
  checkAutobiRefs(id) {
    return request({
      url: `/knowledge_base/${id}/check_autobi_refs`,
      method: 'get'
    })
  },
  
  // 批量选择表结构
  batchSelectTableStructures(id, data) {
    return request({
      url: `/knowledge_base/${id}/table_structures/batch_select`,
      method: 'post',
      data
    })
  },
  
  // 删除知识库表结构
  deleteKbTableStructure(id) {
    return request({
      url: `/knowledge_base/table_structures/${id}`,
      method: 'delete'
    })
  },
  
  // 获取单个知识库表结构及其字段
  getKbTableStructure(id) {
    return request({
      url: `/knowledge_base/table_structures/${id}`,
      method: 'get'
    })
  },
  
  // 更新知识库表结构
  updateKbTableStructure(id, data) {
    return request({
      url: `/knowledge_base/table_structures/${id}`,
      method: 'put',
      data
    })
  },
  
  // 更新知识库表字段
  updateKbTableField(id, data) {
    return request({
      url: `/knowledge_base/table_fields/${id}`,
      method: 'put',
      data
    })
  },
  
  // 删除知识库表字段
  deleteKbTableField(id) {
    return request({
      url: `/knowledge_base/table_fields/${id}`,
      method: 'delete'
    })
  },
  
  // 批量选择知识词条
  batchSelectKnowledgeTerms(id, data) {
    return request({
      url: `/knowledge_base/${id}/knowledge_terms/batch_select`,
      method: 'post',
      data
    })
  },
  
  // 删除知识库知识词条
  deleteKbKnowledgeTerm(id) {
    return request({
      url: `/knowledge_base/knowledge_terms/${id}`,
      method: 'delete'
    })
  },
  
  // 批量选择样例库
  batchSelectSampleLibraries(id, data) {
    return request({
      url: `/knowledge_base/${id}/sample_libraries/batch_select`,
      method: 'post',
      data
    })
  },
  
  // 删除知识库样例库
  deleteKbSampleLibrary(id) {
    return request({
      url: `/knowledge_base/sample_libraries/${id}`,
      method: 'delete'
    })
  },
  
  // 向量化操作
  vectorizeKnowledgeBase(id, steps = null, mode = 'incremental') {
    const data = steps ? { steps, mode } : { mode }
    return request({
      url: `/knowledge_base/${id}/vectorize`,
      method: 'post',
      data
    })
  },

  cancelVectorization(id) {
    return request({
      url: `/knowledge_base/${id}/vectorize/cancel`,
      method: 'post'
    })
  },
  
  // 克隆知识库
  cloneKnowledgeBase(id) {
    return request({
      url: `/knowledge_base/${id}/clone`,
      method: 'post'
    })
  },

  /**
   * 按知识库关联数据源执行只读 SQL（后端禁止 DML）
   * @param {number} id 知识库 ID
   * @param {string} sql
   * @returns {Promise<{ columns: string[], rows: object[], row_count: number }>}
   */
  executeKnowledgeBaseSql(id, sql) {
    return request({
      url: `/knowledge_base/${id}/execute_sql`,
      method: 'post',
      data: { sql }
    })
  },

  /** NER：按 Sheet 分组，单库最多 1000 条 */
  listNerSheets(id) {
    return request({
      url: `/knowledge_base/${id}/ner/sheets`,
      method: 'get'
    })
  },

  listNerRows(id, params) {
    return request({
      url: `/knowledge_base/${id}/ner/rows`,
      method: 'get',
      params
    })
  },

  createNerRow(id, data) {
    return request({
      url: `/knowledge_base/${id}/ner/rows`,
      method: 'post',
      data
    })
  },

  updateNerRow(id, rowId, data) {
    return request({
      url: `/knowledge_base/${id}/ner/rows/${rowId}`,
      method: 'put',
      data
    })
  },

  deleteNerRow(id, rowId) {
    return request({
      url: `/knowledge_base/${id}/ner/rows/${rowId}`,
      method: 'delete'
    })
  },

  deleteNerSheet(id, sheetName) {
    return request({
      url: `/knowledge_base/${id}/ner/sheet`,
      method: 'delete',
      params: { sheet_name: sheetName }
    })
  },

  exportNerRows(id) {
    return request({
      url: `/knowledge_base/${id}/ner/export_rows`,
      method: 'get'
    })
  },

  importNerRows(id, data) {
    return request({
      url: `/knowledge_base/${id}/ner/import`,
      method: 'post',
      data
    })
  }
}

export default knowledgeBaseApi
