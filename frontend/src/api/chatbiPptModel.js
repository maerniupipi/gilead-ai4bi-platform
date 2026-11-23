import request from '@/utils/request'

export const getPptModel = () => request({ url: '/chatbi/ppt-model', method: 'get' })
export const getPptModelOptions = () => request({ url: '/chatbi/ppt-model/options', method: 'get' })
export const savePptModel = data => request({ url: '/chatbi/ppt-model', method: 'put', data })
