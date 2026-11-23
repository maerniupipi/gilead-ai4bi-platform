import assert from 'node:assert/strict'
import { beforeEach, test } from 'node:test'
import { setAuthSession, getUserIdFromToken } from '../src/utils/auth.js'

const data = new Map()
globalThis.localStorage = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) }
globalThis.fetch = async () => ({ ok: true })
beforeEach(() => data.clear())

test('normal backend login supplies the same user ID to management API requests', () => {
  setAuthSession({ token: 'backend_token_42', username: 'operator', role: 'super_admin', userId: 42 })
  assert.equal(getUserIdFromToken(), 42)
})

test('an existing normal login can recover its own ID without requiring another login', () => {
  setAuthSession({ token: 'backend_token_42', username: 'operator', role: 'member' })
  assert.equal(getUserIdFromToken(), 42)
})

test('an unknown opaque token never falls back to a default administrator', () => {
  setAuthSession({ token: 'opaque-token-without-id', username: 'operator', role: 'member' })
  assert.equal(getUserIdFromToken(), null)
})

test('an absent, expired or invalid session cannot produce an identity header', () => {
  assert.equal(getUserIdFromToken(), null)
  setAuthSession({ token: 'backend_token_1', username: 'operator', role: 'super_admin', userId: -1 })
  assert.equal(getUserIdFromToken(), null)
  setAuthSession({ token: 'backend_token_1', username: 'operator', role: 'super_admin', userId: 1 })
  const expired = JSON.parse(data.get('chatbiUser')); expired.expireTime = 1
  data.set('chatbiUser', JSON.stringify(expired))
  assert.equal(getUserIdFromToken(), null)
})
