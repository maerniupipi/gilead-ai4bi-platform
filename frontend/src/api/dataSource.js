import request from '@/utils/request'

// 数据源API模块
const dataSourceApi = {
  queryCatalog(id, database) {
    return request({ url: `/data_source/${id}/query/catalog`, method: 'get', params: { database }, timeout: 20000 })
  },
  query(id, data) {
    return request({ url: `/data_source/${id}/query`, method: 'post', data, timeout: 90000 })
  },
  // 获取数据源列表
  getDataSourceList() {
    return request({
      url: '/data_source',
      method: 'get'
    })
  },
  
  // 获取单个数据源
  getDataSource(id) {
    return request({
      url: `/data_source/${id}`,
      method: 'get'
    })
  },
  
  // 创建数据源
  createDataSource(data) {
    return request({
      url: '/data_source',
      method: 'post',
      data
    })
  },
  
  // 更新数据源
  updateDataSource(id, data) {
    return request({
      url: `/data_source/${id}`,
      method: 'put',
      data
    })
  },
  
  // 删除数据源
  deleteDataSource(id) {
    return request({
      url: `/data_source/${id}`,
      method: 'delete'
    })
  },

  // 获取解密后的密码（仅超管）
  revealPassword(id) {
    return request({
      url: `/data_source/${id}/reveal-password`,
      method: 'get'
    })
  },

  // 检查数据源是否被知识接入引用
  checkKaRefs(id) {
    return request({
      url: `/data_source/${id}/check_ka_refs`,
      method: 'get'
    })
  },

  // 测试数据源连接
  testConnection(data) {
    return request({
      url: '/data_source/test',
      method: 'post',
      data
    })
  }
}

export default dataSourceApi
