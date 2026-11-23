/**
 * 轻量 Markdown → HTML（表格问答工作台 / 洞察报告共用）
 * 支持：标题、粗斜体、行内代码、代码块、无序/有序列表、GFM 表格、引用块（>）
 */

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function applyBoldEm(s) {
  return s
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

function formatBlockquoteInner(raw) {
  const escaped = escapeHtml(raw.trim())
  return `<blockquote class="md-blockquote">${applyBoldEm(escaped).replace(/\n/g, '<br/>')}</blockquote>`
}

export function renderSimpleMarkdown(md) {
  if (!md) return ''

  const codeBlocks = []
  let t = md.replace(/```([\s\S]*?)```/g, (_, c) => {
    const i = codeBlocks.length
    codeBlocks.push(`<pre><code>${escapeHtml(c)}</code></pre>`)
    return `\n\n__MD_CODE_${i}__\n\n`
  })

  const inlineCodes = []
  t = t.replace(/`([^`\n]+)`/g, (_, c) => {
    const i = inlineCodes.length
    inlineCodes.push(`<code>${escapeHtml(c)}</code>`)
    return `__MD_INLINE_${i}__`
  })

  const bqBlocks = []
  t = t.replace(/(?:^|\n)((?:\s*>\s?.+\n?)+)/g, (block) => {
    const body = block.replace(/^\n/, '').trimEnd()
    const lines = body.split('\n').filter((l) => /^\s*>/.test(l))
    if (!lines.length) return block
    const inner = lines.map((l) => l.replace(/^\s*>\s?/, '')).join('\n')
    const i = bqBlocks.length
    bqBlocks.push(formatBlockquoteInner(inner))
    return `\n\n__MD_BQ_${i}__\n\n`
  })

  t = escapeHtml(t)

  t = t.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>')
  t = t.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>')
  t = t.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>')
  t = t.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>')
  t = t.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>')
  t = t.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>')

  t = applyBoldEm(t)

  t = t.replace(/(?:^|\n)((?:\s*[-*]\s+.+\n?)+)/g, (block) => {
    const items = block
      .trim()
      .split('\n')
      .map((l) => l.replace(/^\s*[-*]\s+/, '').trim())
      .filter(Boolean)
      .map((x) => `<li>${x}</li>`)
      .join('')
    return `\n<ul>${items}</ul>`
  })

  t = t.replace(/(?:^|\n)((?:\s*\d+\.\s+.+\n?)+)/g, (block) => {
    const items = block
      .trim()
      .split('\n')
      .map((l) => l.replace(/^\s*\d+\.\s+/, '').trim())
      .filter(Boolean)
      .map((x) => `<li>${x}</li>`)
      .join('')
    return `\n<ol>${items}</ol>`
  })

  t = t.replace(/(?:^|\n)((?:\|.+\|[ \t]*\n)+)/g, (block) => {
    const lines = block.trim().split('\n').filter((l) => /^\|/.test(l.trim()))
    if (lines.length < 2) return block
    const splitRow = (row) =>
      row
        .replace(/^\||\|$/g, '')
        .split('|')
        .map((c) => c.trim())
    const header = splitRow(lines[0])
    const bodyStart = /^[\s|:-]+$/.test(lines[1].replace(/[|\s]/g, '')) ? 2 : 1
    const body = lines.slice(bodyStart).map(splitRow)
    const thead =
      '<thead><tr>' + header.map((c) => `<th>${c}</th>`).join('') + '</tr></thead>'
    const tbody =
      '<tbody>' +
      body.map((r) => '<tr>' + r.map((c) => `<td>${c}</td>`).join('') + '</tr>').join('') +
      '</tbody>'
    return `\n<div class="md-table-wrap"><table>${thead}${tbody}</table></div>`
  })

  const isBlock = (p) =>
    /^\s*<(h\d|ul|ol|pre|blockquote|div|table)\b/i.test(p) ||
    /^__MD_(CODE|BQ)_\d+__$/.test(p.trim())

  t = t
    .split(/\n{2,}/)
    .map((p) => (isBlock(p) ? p : `<p>${p.replace(/\n/g, '<br/>')}</p>`))
    .join('\n')

  t = t.replace(/__MD_INLINE_(\d+)__/g, (_, i) => inlineCodes[Number(i)] || '')
  t = t.replace(/__MD_BQ_(\d+)__/g, (_, i) => bqBlocks[Number(i)] || '')
  t = t.replace(/__MD_CODE_(\d+)__/g, (_, i) => codeBlocks[Number(i)] || '')

  return t
}
