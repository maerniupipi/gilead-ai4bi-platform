/**
 * 认证相关的工具函数
 */

const AUTH_TOKEN_KEY = 'chatbiUser'
const SPACE_ID_KEY = 'chatbiSpaceId'
const TOKEN_EXPIRE_HOURS = 24
const JWT_SECRET = 'ai4bi-space-secret-key-2024'  // 简化版，实际应使用环境变量

/**
 * 写入完整登录会话（含后端 token 与本地用户信息）
 * @param {{ token: string, username: string, role: string, displayName?: string, userId?: number, system_role?: string }} session
 */
export function setAuthSession ({ token, username, role, displayName, userId, system_role }) {
  const expireTime = Date.now() + TOKEN_EXPIRE_HOURS * 60 * 60 * 1000
  const authData = {
    token,
    expireTime,
    username,
    role: role || 'member',
    displayName: displayName || username,
    userId: userId,
    system_role: system_role || role || 'member'
  }
  localStorage.setItem(AUTH_TOKEN_KEY, JSON.stringify(authData))
}

/**
 * @deprecated 仅兼容旧逻辑；新登录请使用 setAuthSession
 * @param {string} token
 */
export function setAuthToken (token) {
  setAuthSession({
    token,
    username: 'legacy',
    role: 'user',
    displayName: '用户'
  })
}

/**
 * 获取认证 token（无用户名视为旧会话，需重新登录）
 * @returns {string|null}
 */
export function getAuthToken () {
  try {
    const authDataStr = localStorage.getItem(AUTH_TOKEN_KEY)
    if (!authDataStr) return null

    const authData = JSON.parse(authDataStr)

    if (Date.now() > authData.expireTime) {
      removeAuthToken()
      return null
    }

    if (!authData.username || authData.username === 'legacy') {
      removeAuthToken()
      return null
    }

    return authData.token
  } catch (error) {
    console.error('解析认证数据失败:', error)
    removeAuthToken()
    return null
  }
}

/**
 * @returns {{ username: string, role: string, displayName: string, userId: number, system_role: string } | null}
 */
export function getCurrentUser () {
  try {
    const authDataStr = localStorage.getItem(AUTH_TOKEN_KEY)
    if (!authDataStr) return null
    const authData = JSON.parse(authDataStr)
    if (Date.now() > authData.expireTime) {
      removeAuthToken()
      return null
    }
    if (!authData.username || authData.username === 'legacy') return null
    return {
      username: authData.username,
      role: authData.role || authData.system_role || 'member',
      displayName: authData.displayName || authData.username,
      userId: authData.userId,
      system_role: authData.system_role || authData.role || 'member'
    }
  } catch {
    return null
  }
}

/**
 * 创建工作流等资源时带给后端的负责人展示名（未登录则 undefined）
 * @returns {string|undefined}
 */
export function getOwnerDisplayNameForCreate () {
  const u = getCurrentUser()
  if (!u) return undefined
  const s = String(u.displayName || u.username || '').trim()
  return s || undefined
}

export function removeAuthToken () {
  const hadSession = !!localStorage.getItem(AUTH_TOKEN_KEY)
  localStorage.removeItem(AUTH_TOKEN_KEY)
  if (hadSession && typeof window !== 'undefined' && typeof window.fetch === 'function') {
    void window.fetch('/api/users/logout', { method: 'POST', credentials: 'same-origin', keepalive: true }).catch(() => {})
  }
}

export function isAuthenticated () {
  return getAuthToken() !== null
}

/**
 * 获取当前空间ID
 * @returns {number|null}
 */
export function getCurrentSpaceId() {
  const spaceId = localStorage.getItem(SPACE_ID_KEY)
  if (spaceId) {
    return parseInt(spaceId, 10)
  }
  return null
}

/**
 * 设置当前空间ID
 * @param {number} spaceId
 */
export function setCurrentSpaceId(spaceId) {
  if (spaceId) {
    localStorage.setItem(SPACE_ID_KEY, String(spaceId))
  } else {
    localStorage.removeItem(SPACE_ID_KEY)
  }
}

/**
 * 生成简化版JWT token
 * @param {object} payload - 包含 userId 等信息
 * @returns {string} token
 */
export function generateToken(payload) {
  const header = { alg: 'HS256', typ: 'JWT' }
  const headerB64 = btoa(JSON.stringify(header))
  const payloadWithExp = {
    ...payload,
    exp: Math.floor(Date.now() / 1000) + (TOKEN_EXPIRE_HOURS * 3600)
  }
  const payloadB64 = btoa(JSON.stringify(payloadWithExp))
  const signature = SHA256(`${headerB64}.${payloadB64}.${JWT_SECRET}`)
  return `${headerB64}.${payloadB64}.${signature}`
}

/**
 * SHA256 hash function
 */
function SHA256(str) {
  function rotateRight(n, s) {
    return ((n >>> s) | (n << (32 - s))) >>> 0
  }
  function Ch(x, y, z) {
    return (x & y) ^ (~x & z)
  }
  function Maj(x, y, z) {
    return (x & y) ^ (x & z) ^ (y & z)
  }
  function Sigma0(x) {
    return rotateRight(x, 2) ^ rotateRight(x, 13) ^ rotateRight(x, 22)
  }
  function Sigma1(x) {
    return rotateRight(x, 6) ^ rotateRight(x, 11) ^ rotateRight(x, 25)
  }
  function Gamma0(x) {
    return rotateRight(x, 7) ^ rotateRight(x, 18) ^ (x >>> 3)
  }
  function Gamma1(x) {
    return rotateRight(x, 17) ^ rotateRight(x, 19) ^ (x >>> 10)
  }

  const K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ]

  const H = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  ]

  const msg = unescape(encodeURIComponent(str))
  const msgBytes = new Uint8Array(msg.length)
  for (let i = 0; i < msg.length; i++) {
    msgBytes[i] = msg.charCodeAt(i)
  }

  const bitLenHi = (msgBytes.length * 8) / 0x100000000
  const bitLenLo = msgBytes.length * 8 >>> 0
  const paddingLen = msgBytes.length % 64 < 56 ? 56 : 120
  const totalLen = msgBytes.length + paddingLen + 8
  const padded = new Uint8Array(totalLen)
  padded.set(msgBytes, 0)
  padded[msgBytes.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(totalLen - 4, bitLenLo, false)
  view.setUint32(totalLen - 8, bitLenHi, false)

  for (let chunk = 0; chunk < padded.length; chunk += 64) {
    const W = new Uint32Array(64)
    for (let i = 0; i < 16; i++) {
      W[i] = view.getUint32(chunk + i * 4, false)
    }
    for (let i = 16; i < 64; i++) {
      W[i] = (Gamma1(W[i - 2]) + W[i - 7] + Gamma0(W[i - 15]) + W[i - 16]) >>> 0
    }
    let [a, b, c, d, e, f, g, h] = H
    for (let i = 0; i < 64; i++) {
      const T1 = (h + Sigma1(e) + Ch(e, f, g) + K[i] + W[i]) >>> 0
      const T2 = (Sigma0(a) + Maj(a, b, c)) >>> 0
      h = g
      g = f
      f = e
      e = (d + T1) >>> 0
      d = c
      c = b
      b = a
      a = (T1 + T2) >>> 0
    }
    H[0] = (H[0] + a) >>> 0
    H[1] = (H[1] + b) >>> 0
    H[2] = (H[2] + c) >>> 0
    H[3] = (H[3] + d) >>> 0
    H[4] = (H[4] + e) >>> 0
    H[5] = (H[5] + f) >>> 0
    H[6] = (H[6] + g) >>> 0
    H[7] = (H[7] + h) >>> 0
  }

  function toHexStr(n) {
    let h = ''
    for (let i = 24; i >= 0; i -= 4) {
      h += ((n >>> i) & 0xf).toString(16)
    }
    return h
  }

  return H.map(toHexStr).join('')
}

/**
 * 验证简化版JWT token
 * @param {string} token
 * @returns {object|null} 解码后的payload或null
 */
export function verifyToken(token) {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null

    const [headerB64, payloadB64, signature] = parts
    const expectedSig = SHA256(`${headerB64}.${payloadB64}.${JWT_SECRET}`)

    if (signature !== expectedSig) return null

    const payload = JSON.parse(atob(payloadB64))
    if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
      return null  // token过期
    }
    return payload
  } catch {
    return null
  }
}

/**
 * 从token中获取用户ID
 * @returns {number|null}
 */
export function getUserIdFromToken() {
  const token = getAuthToken()
  if (!token) return null
  // Normal account login stores an opaque backend token and the server-returned
  // userId in the session. Retain the existing JWT fallback for older sessions.
  const storedUserId = getCurrentUser()?.userId
  const userId = Number(storedUserId)
  if (Number.isSafeInteger(userId) && userId > 0) return userId
  if (storedUserId != null) return null
  // 已登录的旧版本会话可能只保存了后端返回的用户 token。
  const legacy = /^backend_token_([1-9]\d*)$/.exec(token)
  if (legacy) {
    const legacyUserId = Number(legacy[1])
    if (Number.isSafeInteger(legacyUserId)) return legacyUserId
  }
  const payload = verifyToken(token)
  return payload?.userId || null
}
