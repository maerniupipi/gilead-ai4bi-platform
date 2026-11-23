import request from '../utils/request'

/**
 * 会话登录（无邀请码）
 * @returns {Promise<{ token: string }>}
 */
export function sessionLogin() {
  return request({
    url: '/auth/login',
    method: 'post',
    data: {}
  })
}
