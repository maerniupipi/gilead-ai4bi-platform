import request from '@/utils/request'

export default {
  // 获取知识接入的表结构列表
  getTableStructures(knowledgeAccessId) {
    return request({
      url: `/table_structure/knowledge_access/${knowledgeAccessId}`,
      method: 'get'
    })
  },
  
  // 获取表结构的字段列表
  getTableFields(tableStructureId, enabledOnly = false) {
    return request({
      url: `/table_structure/${tableStructureId}/fields`,
      method: 'get',
      params: enabledOnly ? { enabled_only: true } : {}
    })
  },
  
  // 创建表结构
  createTableStructure(knowledgeAccessId, data) {
    return request({
      url: `/table_structure?knowledge_access_id=${knowledgeAccessId}`,
      method: 'post',
      data
    })
  },
  
  // 更新表结构
  updateTableStructure(tableStructureId, data) {
    return request({
      url: `/table_structure/${tableStructureId}`,
      method: 'put',
      data
    })
  },
  
  // 创建表字段
  createTableField(tableStructureId, data) {
    return request({
      url: `/table_structure/${tableStructureId}/fields`,
      method: 'post',
      data
    })
  },
  
  // 更新表字段
  updateTableField(tableFieldId, data) {
    return request({
      url: `/table_structure/fields/${tableFieldId}`,
      method: 'put',
      data
    })
  },
  
  // 获取外部数据库的表列表
  getDatabaseTables(knowledgeAccessId) {
    return request({
      url: `/table_structure/import/${knowledgeAccessId}/tables`,
      method: 'get',
      timeout: 60000  // 60s timeout for external DB connection
    })
  },

  // 导入表结构
  importTables(knowledgeAccessId, tableNames) {
    return request({
      url: `/table_structure/import/${knowledgeAccessId}`,
      method: 'post',
      data: { table_names: tableNames },
      timeout: 120000  // 120s timeout for importing multiple tables
    })
  },
  
  // 删除表结构
  deleteTableStructure(tableStructureId) {
    return request({
      url: `/table_structure/${tableStructureId}`,
      method: 'delete'
    })
  }
}
