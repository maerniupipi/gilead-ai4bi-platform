/**
 * AES-256-GCM password encryption/decryption via Web Crypto API.
 *
 * Uses the same shared key as the backend (PASSWORD_ENCRYPTION_KEY).
 * The key must be exposed to the frontend via Vite env var
 * VITE_PASSWORD_ENCRYPTION_KEY (64-char hex = 32 bytes).
 *
 * Wire format: base64( nonce[12] || ciphertext )
 * Backend prefixes with "ENC:" — this utility handles the prefix.
 */

const ENC_PREFIX = 'ENC:'
const NONCE_LENGTH = 12

function getKeyBytes() {
  const hex = (import.meta.env.VITE_PASSWORD_ENCRYPTION_KEY || '').trim()
  if (!hex || hex.length !== 64) {
    throw new Error('VITE_PASSWORD_ENCRYPTION_KEY must be a 64-char hex string')
  }
  const bytes = new Uint8Array(32)
  for (let i = 0; i < 32; i++) {
    bytes[i] = parseInt(hex.substring(i * 2, i * 2 + 2), 16)
  }
  return bytes
}

async function importKey(rawBytes) {
  return crypto.subtle.importKey(
    'raw',
    rawBytes,
    { name: 'AES-GCM' },
    false,
    ['encrypt', 'decrypt']
  )
}

function base64ToUint8Array(base64) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

function uint8ArrayToBase64(bytes) {
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

/**
 * Decrypt an encrypted password from the backend.
 *
 * Supports both "ENC:"-prefixed ciphertext and legacy plaintext
 * (plaintext is returned as-is for backward compatibility).
 *
 * @param {string} encrypted - The encrypted value from the API
 * @returns {Promise<string>} The decrypted plaintext password
 */
export async function decryptPassword(encrypted) {
  if (!encrypted || !encrypted.startsWith(ENC_PREFIX)) {
    // Legacy plaintext or empty
    return encrypted || ''
  }

  const payload = encrypted.substring(ENC_PREFIX.length)
  const raw = base64ToUint8Array(payload)
  const nonce = raw.slice(0, NONCE_LENGTH)
  const ciphertext = raw.slice(NONCE_LENGTH)

  const key = await importKey(getKeyBytes())
  const plainBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: nonce },
    key,
    ciphertext
  )
  return new TextDecoder().decode(plainBuffer)
}

/**
 * Encrypt a plaintext password for sending to the backend.
 *
 * @param {string} plaintext - The plaintext password
 * @returns {Promise<string>} Base64-encoded ciphertext with "ENC:" prefix
 */
export async function encryptPassword(plaintext) {
  if (!plaintext) return ''

  const rawBytes = getKeyBytes()
  const key = await importKey(rawBytes)
  const nonce = crypto.getRandomValues(new Uint8Array(NONCE_LENGTH))
  const encoded = new TextEncoder().encode(plaintext)
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce },
    key,
    encoded
  )

  const combined = new Uint8Array(nonce.length + ciphertext.byteLength)
  combined.set(nonce, 0)
  combined.set(new Uint8Array(ciphertext), nonce.length)

  return ENC_PREFIX + uint8ArrayToBase64(combined)
}
