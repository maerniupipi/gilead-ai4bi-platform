/** Round chart display text only; leave series and source rows untouched. */
export function formatChartValue(value) {
  if (value == null) return ''
  const raw = String(value).trim()
  if (!raw) return ''
  const match = /^([+-]?)(\d+)(?:\.(\d*))?([%％]?)$/.exec(raw.replace(/,/g, ''))
  if (!match) {
    const numeric = Number(raw)
    return Number.isFinite(numeric) ? numeric.toFixed(2) : raw
  }
  const [, sign, integer, fraction = '', suffix] = match
  const digits = (integer.replace(/^0+(?=\d)/, '') + (fraction + '00').slice(0, 2)).split('')
  if ((fraction[2] || '0') >= '5') {
    let index = digits.length - 1
    while (index >= 0 && digits[index] === '9') { digits[index] = '0'; index-- }
    if (index < 0) digits.unshift('1')
    else digits[index] = String(Number(digits[index]) + 1)
  }
  const combined = digits.join('').padStart(3, '0')
  return (sign === '-' && /[1-9]/.test(combined) ? '-' : '') + combined.slice(0, -2) + '.' + combined.slice(-2) + suffix
}
