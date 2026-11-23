import ExcelJS from 'exceljs'

export const SAMPLE_NAME_MAX = 100
export const SAMPLE_SQL_MAX = 2000

export const SAMPLE_HEADER = ['样例名称', 'SQL内容']

const HEADER_FILL = {
  type: 'pattern',
  pattern: 'solid',
  fgColor: { argb: 'FF5C6BC0' }
}

function clipName(s) {
  return String(s ?? '').trim().slice(0, SAMPLE_NAME_MAX)
}

function clipSql(s) {
  return String(s ?? '').trim().slice(0, SAMPLE_SQL_MAX)
}

function styleHeaderRow(sheet) {
  const row = sheet.getRow(1)
  for (let c = 1; c <= SAMPLE_HEADER.length; c++) {
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
    { width: 80 }
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
  return joined.includes('样例名称') || joined.includes('SQL内容')
}

export async function buildSampleTemplateWorkbook() {
  const wb = new ExcelJS.Workbook()
  wb.creator = 'Chat-BI'

  const ws = wb.addWorksheet('样例库', {
    views: [{ state: 'frozen', ySplit: 1 }]
  })
  ws.addRow(SAMPLE_HEADER)
  styleHeaderRow(ws)
  setColumnWidths(ws)
  ws.addRow([clipName('查询销售总额'), clipSql('SELECT SUM(amount) AS total_sales FROM orders WHERE status = \'completed\'')])
  ws.addRow([clipName('按月统计订单数'), clipSql('SELECT DATE_FORMAT(created_at, \'%Y-%m\') AS month, COUNT(*) AS order_count FROM orders GROUP BY month ORDER BY month')])

  return wb
}

export async function buildSampleExportWorkbookFromApiRows(rows) {
  if (!rows || rows.length === 0) {
    return buildSampleTemplateWorkbook()
  }

  const wb = new ExcelJS.Workbook()
  wb.creator = 'Chat-BI'

  const ws = wb.addWorksheet('样例库', {
    views: [{ state: 'frozen', ySplit: 1 }]
  })
  ws.addRow(SAMPLE_HEADER)
  styleHeaderRow(ws)
  setColumnWidths(ws)
  for (const r of rows) {
    ws.addRow([clipName(r.sample_name), clipSql(r.sql_content)])
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

export async function downloadSampleTemplate(filename = '样例库导入模板.xlsx') {
  const wb = await buildSampleTemplateWorkbook()
  const buf = await workbookToXlsxBuffer(wb)
  triggerDownload(buf, filename)
}

export async function downloadSampleExportFromApiRows(rows, baseName = '样例库导出') {
  const wb = await buildSampleExportWorkbookFromApiRows(rows)
  const buf = await workbookToXlsxBuffer(wb)
  const safe = baseName.replace(/[/\\?%*:|"<>]/g, '_')
  const isEmpty = !rows || rows.length === 0
  triggerDownload(buf, isEmpty ? '样例库导入模板.xlsx' : `${safe}.xlsx`)
}

export async function parseSampleWorkbookArrayBuffer(arrayBuffer) {
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
      while (cells.length < SAMPLE_HEADER.length) cells.push('')
      const trimmed = cells.slice(0, SAMPLE_HEADER.length)
      if (trimmed.every(v => !String(v).trim())) return
      if (rowNumber === 1 && rowLooksLikeHeader(trimmed)) return
      if (rowLooksLikeHeader(trimmed)) return

      out.push({
        sample_name: clipName(trimmed[0] ?? ''),
        sql_content: clipSql(trimmed[1] ?? '')
      })
    })
  })

  return out
}
