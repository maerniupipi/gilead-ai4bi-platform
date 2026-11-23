import ExcelJS from 'exceljs'

export const TERM_NAME_MAX = 100
export const TERM_VALUE_MAX = 500

export const TERM_HEADER = ['词条名称', '词条值']

const HEADER_FILL = {
  type: 'pattern',
  pattern: 'solid',
  fgColor: { argb: 'FF5C6BC0' }
}

function clipName(s) {
  return String(s ?? '').trim().slice(0, TERM_NAME_MAX)
}

function clipValue(s) {
  return String(s ?? '').trim().slice(0, TERM_VALUE_MAX)
}

function styleHeaderRow(sheet) {
  const row = sheet.getRow(1)
  for (let c = 1; c <= TERM_HEADER.length; c++) {
    const cell = row.getCell(c)
    cell.fill = HEADER_FILL
    cell.font = { bold: true, color: { argb: 'FFFFFFFF' }, size: 11 }
    cell.alignment = { vertical: 'middle', horizontal: 'center', wrapText: true }
  }
  row.height = 24
}

function setColumnWidths(sheet) {
  sheet.columns = [
    { width: 24 },
    { width: 60 }
  ]
}

function cellToString(val) {
  if (val == null) return ''
  if (typeof val === 'object' && val !== null && 'richText' in val) {
    return val.richText?.map(t => t.text).join('') || ''
  }
  if (typeof val === 'object' && val !== null && 'text' in val) return String(val.text)
  return String(val).trim()
}

function rowLooksLikeHeader(cells) {
  const joined = cells.join('').replace(/\s/g, '')
  return joined.includes('词条名称') || joined.includes('词条值')
}

export async function buildTermTemplateWorkbook() {
  const wb = new ExcelJS.Workbook()
  wb.creator = 'Chat-BI'

  const ws = wb.addWorksheet('知识词条', {
    views: [{ state: 'frozen', ySplit: 1 }]
  })
  ws.addRow(TERM_HEADER)
  styleHeaderRow(ws)
  setColumnWidths(ws)
  ws.addRow([clipName('示例词条'), clipValue('这是词条的值，用于解释业务术语')])
  ws.addRow([clipName('GMV'), clipValue('Gross Merchandise Volume，商品交易总额')])

  return wb
}

export async function buildTermExportWorkbookFromApiRows(rows) {
  if (!rows || rows.length === 0) {
    return buildTermTemplateWorkbook()
  }

  const wb = new ExcelJS.Workbook()
  wb.creator = 'Chat-BI'

  const ws = wb.addWorksheet('知识词条', {
    views: [{ state: 'frozen', ySplit: 1 }]
  })
  ws.addRow(TERM_HEADER)
  styleHeaderRow(ws)
  setColumnWidths(ws)
  for (const r of rows) {
    ws.addRow([clipName(r.term_name), clipValue(r.term_value)])
  }

  return wb
}

export async function workbookToXlsxBuffer(wb) {
  return wb.xlsx.writeBuffer()
}

function triggerDownload(buffer, filename) {
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadTermTemplate(filename = '知识词条导入模板.xlsx') {
  const wb = await buildTermTemplateWorkbook()
  const buf = await workbookToXlsxBuffer(wb)
  triggerDownload(buf, filename)
}

export async function downloadTermExportFromApiRows(rows, baseName = '知识词条导出') {
  const wb = await buildTermExportWorkbookFromApiRows(rows)
  const buf = await workbookToXlsxBuffer(wb)
  const safe = baseName.replace(/[/\\?%*:|"<>]/g, '_')
  const isEmpty = !rows || rows.length === 0
  triggerDownload(buf, isEmpty ? '知识词条导入模板.xlsx' : `${safe}.xlsx`)
}

export async function parseTermWorkbookArrayBuffer(arrayBuffer) {
  const wb = new ExcelJS.Workbook()
  await wb.xlsx.load(arrayBuffer)
  const out = []

  wb.eachSheet((sheet) => {
    sheet.eachRow((row, rowNumber) => {
      const cells = []
      row.eachCell({ includeEmpty: true }, (cell, colNumber) => {
        while (cells.length < colNumber - 1) cells.push('')
        cells[colNumber - 1] = cellToString(cell.value)
      })
      while (cells.length < TERM_HEADER.length) cells.push('')
      const trimmed = cells.slice(0, TERM_HEADER.length)
      if (trimmed.every(v => !String(v).trim())) return
      if (rowNumber === 1 && rowLooksLikeHeader(trimmed)) return
      if (rowLooksLikeHeader(trimmed)) return

      out.push({
        term_name: clipName(trimmed[0] ?? ''),
        term_value: clipValue(trimmed[1] ?? '')
      })
    })
  })

  return out
}
