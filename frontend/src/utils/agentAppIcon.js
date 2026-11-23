/** 与后端一致：仅保留 BMP 字符（兼容 MySQL utf8，非 utf8mb4），最多 4 字符 */
export const DEFAULT_AGENT_APP_ICON = '*'

/**
 * 说明：
 * - 使用 BMP 范围内符号，避免 4 字节 emoji 写入 utf8 列失败
 * - 尽量使用 VS16（FE0F）变体，在多数系统中可呈现彩色风格
 */
export const AGENT_APP_ICON_CHOICES = ['☀️', '⭐️', '⚡️', '✨', '✅', '❇️', '❤️', '☕️', '✈️', '⚙️', '☘️', '♻️']

export function clampAgentAppIcon(raw) {
  if (raw == null || raw === '') return DEFAULT_AGENT_APP_ICON
  let out = ''
  for (const ch of String(raw).trim()) {
    const cp = ch.codePointAt(0)
    if (cp > 0xffff) continue
    out += ch
    if (out.length >= 4) break
  }
  return out || DEFAULT_AGENT_APP_ICON
}
