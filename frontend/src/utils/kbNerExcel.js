import ExcelJS from 'exceljs'

/** 与模板、导出列顺序一致；数据单元格最多 50 字（与后端一致） */
export const NER_CELL_MAX = 50
export const NER_SHEET_NAME_MAX = 64

/** 与模板、导出列顺序一致 */
export const NER_HEADER = [
  '表名',
  '字段名',
  '标准名称（数据库字段值）',
  '别名',
  '备注'
]

const HEADER_FILL = {
  type: 'pattern',
  pattern: 'solid',
  fgColor: { argb: 'FF5C6BC0' }
}

export function clipCell(s) {
  return String(s ?? '')
    .trim()
    .slice(0, NER_CELL_MAX)
}

export function clipSheetName(s) {
  return String(s ?? '')
    .trim()
    .slice(0, NER_SHEET_NAME_MAX)
}

function styleHeaderRow(sheet, colCount = NER_HEADER.length) {
  const row = sheet.getRow(1)
  for (let c = 1; c <= colCount; c++) {
    const cell = row.getCell(c)
    cell.fill = HEADER_FILL
    cell.font = { bold: true, color: { argb: 'FFFFFFFF' }, size: 11 }
    cell.alignment = { vertical: 'middle', horizontal: 'center', wrapText: true }
  }
  row.height = 24
}

function setColumnWidths(sheet) {
  sheet.columns = [
    { width: 18 },
    { width: 16 },
    { width: 32 },
    { width: 14 },
    { width: 42 }
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
  return (
    joined.includes('表名') &&
    joined.includes('字段名') &&
    (joined.includes('标准名称') || joined.includes('数据库字段值'))
  )
}

/** Excel 工作表名合法化，最长 31 */
function safeExcelTabName(name, used) {
  let base = String(name || 'Sheet')
    .replace(/[:\\/?*[\]]/g, '_')
    .replace(/'/g, '')
    .slice(0, 31) || 'Sheet'
  let n = base
  let i = 1
  while (used.has(n)) {
    const suffix = `_${i}`
    n = (base.slice(0, 31 - suffix.length) + suffix).slice(0, 31)
    i++
  }
  used.add(n)
  return n
}

/**
 * 默认模板：Sheet「省份」+ Sheet「订单状态」；示例单元格不超过 NER_CELL_MAX
 */
export async function buildNerTemplateWorkbook() {
  const wb = new ExcelJS.Workbook()
  wb.creator = 'Chat-BI'

  const ws1 = wb.addWorksheet('省份', {
    views: [{ state: 'frozen', ySplit: 1 }]
  })
  ws1.addRow(NER_HEADER)
  styleHeaderRow(ws1)
  setColumnWidths(ws1)
  ws1.addRow([
    clipCell('product'),
    clipCell('provice'),
    clipCell('上海市'),
    clipCell('上海'),
    clipCell(
      'product 表省份字段示例 provice；标准值为库内存储，别名为对话展示简称'
    )
  ])

  const ws2 = wb.addWorksheet('订单状态', {
    views: [{ state: 'frozen', ySplit: 1 }]
  })
  ws2.addRow(NER_HEADER)
  styleHeaderRow(ws2)
  setColumnWidths(ws2)
  ws2.addRow([
    clipCell('orders'),
    clipCell('status_code'),
    clipCell('2'),
    clipCell('已完成'),
    clipCell('状态码2展示为已完成')
  ])
  ws2.addRow([
    clipCell('orders'),
    clipCell('status_code'),
    clipCell('1'),
    clipCell('待支付'),
    clipCell('状态码1展示为待支付')
  ])

  return wb
}

/**
 * 后端导出记录（snake_case）→ 按 sheet_name 分工作簿；无数据则模板
 * @param {Array<{sheet_name:string,table_name:string,field_name:string,standard_name:string,alias:string,remark:string}>} rows
 */
export async function buildNerExportWorkbookFromApiRows(rows) {
  if (!rows || rows.length === 0) {
    return buildNerTemplateWorkbook()
  }

  const wb = new ExcelJS.Workbook()
  wb.creator = 'Chat-BI'
  const usedNames = new Set()
  const bySheet = new Map()
  for (const r of rows) {
    const sn = clipSheetName(r.sheet_name || '默认')
    if (!bySheet.has(sn)) bySheet.set(sn, [])
    bySheet.get(sn).push(r)
  }

  for (const [sheetName, sheetRows] of bySheet) {
    const tab = safeExcelTabName(sheetName, usedNames)
    const ws = wb.addWorksheet(tab, {
      views: [{ state: 'frozen', ySplit: 1 }]
    })
    ws.addRow(NER_HEADER)
    styleHeaderRow(ws)
    setColumnWidths(ws)
    for (const r of sheetRows) {
      ws.addRow([
        clipCell(r.table_name),
        clipCell(r.field_name),
        clipCell(r.standard_name),
        clipCell(r.alias),
        clipCell(r.remark)
      ])
    }
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

export async function downloadNerTemplate(filename = 'NER导入模板.xlsx') {
  const wb = await buildNerTemplateWorkbook()
  const buf = await workbookToXlsxBuffer(wb)
  triggerDownload(buf, filename)
}

export async function downloadNerExportFromApiRows(rows, baseName = 'NER导出') {
  const wb = await buildNerExportWorkbookFromApiRows(rows)
  const buf = await workbookToXlsxBuffer(wb)
  const safe = baseName.replace(/[/\\?%*:|"<>]/g, '_')
  const isEmpty = !rows || rows.length === 0
  triggerDownload(buf, isEmpty ? 'NER导入模板.xlsx' : `${safe}.xlsx`)
}

/**
 * 解析 xlsx：每行带 sheetName（工作表名），数据列裁剪至 NER_CELL_MAX
 */
export async function parseNerWorkbookArrayBuffer(arrayBuffer) {
  const wb = new ExcelJS.Workbook()
  await wb.xlsx.load(arrayBuffer)
  const out = []

  wb.eachSheet((sheet) => {
    const sheetLabel = clipSheetName(sheet.name)
    sheet.eachRow((row, rowNumber) => {
      const cells = []
      row.eachCell({ includeEmpty: true }, (cell, colNumber) => {
        while (cells.length < colNumber - 1) cells.push('')
        cells[colNumber - 1] = cellToString(cell.value)
      })
      while (cells.length < NER_HEADER.length) cells.push('')
      const trimmed = cells.slice(0, NER_HEADER.length)
      if (trimmed.every(v => !String(v).trim())) return
      if (rowNumber === 1 && rowLooksLikeHeader(trimmed)) return
      if (rowLooksLikeHeader(trimmed)) return

      out.push({
        sheetName: sheetLabel,
        tableName: clipCell(trimmed[0] ?? ''),
        fieldName: clipCell(trimmed[1] ?? ''),
        standardName: clipCell(trimmed[2] ?? ''),
        alias: clipCell(trimmed[3] ?? ''),
        remark: clipCell(trimmed[4] ?? '')
      })
    })
  })

  return out
}

/** 转为后端 import 接口行（snake_case） */
export function nerParsedToApiRows(parsed) {
  return parsed.map((p) => ({
    sheet_name: clipSheetName(p.sheetName),
    table_name: clipCell(p.tableName),
    field_name: clipCell(p.fieldName),
    standard_name: clipCell(p.standardName),
    alias: clipCell(p.alias),
    remark: clipCell(p.remark)
  }))
}
