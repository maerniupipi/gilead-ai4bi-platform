import request from '../utils/request'

/**
 * 实验中心原子能力 API（路径仍为 /autobi-atomic）
 * knowledge_base_id 作为 URL 参数传递
 */

// ES表值召回
export function esValueRetriever(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/es-value-retriever`,
    method: 'post',
    data
  })
}

// ES知识词召回
export function esKnowledgeRetriever(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/es-knowledge-retriever`,
    method: 'post',
    data
  })
}

// SQL样例召回
export function sqlTemplateRetriever(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/sql-template-retriever`,
    method: 'post',
    data
  })
}

// 生成 SQL
export function generateSql(data) {
  return request({
    url: '/autobi-atomic/generate-sql',
    method: 'post',
    data
  })
}

// 执行 SQL
export function executeSql(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/execute-sql`,
    method: 'post',
    data
  })
}

// 表字段召回
export function tableMetaRetriever(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/table-meta-retriever`,
    method: 'post',
    data
  })
}

// 表值召回
export function tableValueRetriever(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/table-value-retriever`,
    method: 'post',
    data
  })
}

// 表值召回(对应字段)
export function globalValueMetaRetriever(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/global-value-meta-retriever`,
    method: 'post',
    data
  })
}

// 多列同值（对多个 表&字段 分别做表值召回对应字段后去重）
export function multiGlobalValueMetaRetriever(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/multi-global-value-meta-retriever`,
    method: 'post',
    data
  })
}

// NER：知识库别名映射
export function nerRetriever(knowledgeBaseId, data) {
  return request({
    url: `/autobi-atomic/${knowledgeBaseId}/ner-retriever`,
    method: 'post',
    data
  })
}
