import test from 'node:test'
import assert from 'node:assert/strict'
import { formatChartValue } from '../src/utils/formatChartValue.js'
import { buildBarLineOptions, buildPieOptions } from '../src/utils/autobiLabChartSpec.js'

test('chart text rounds metrics and percentages to two decimals without losing large decimal strings', () => {
  for (const [value, expected] of [
    [null, ''], ['', ''], [0, '0.00'], [1, '1.00'], [-1.235, '-1.24'],
    ['1.005', '1.01'], ['1,234.56789', '1234.57'], ['9007199254740993.995', '9007199254740994.00'],
    ['-0.0002', '0.00'], ['12.3456%', '12.35%'], ['1e-3', '0.00'], ['文本', '文本'],
  ]) assert.equal(formatChartValue(value), expected, String(value))
})

test('bar and line axes/tooltips/labels share two-decimal display and keep source values', () => {
  const data = { columns: ['医院', 'IMS'], rows: [{ 医院: '医院123', IMS: '123.45678' }, { 医院: '医院2', IMS: null }] }
  const before = structuredClone(data)
  for (const type of ['bar', 'line']) {
    const option = buildBarLineOptions({ xaxis: ['医院'], yaxis: ['IMS'] }, data, type)
    assert.equal(option.tooltip.valueFormatter('123.45678'), '123.46')
    assert.equal(option.yAxis.axisLabel.formatter(5), '5.00')
    assert.equal(option.series[0].label.formatter({ value: -1.235 }), '-1.24')
    assert.equal(option.xAxis.data[0], '医院123')
    assert.equal(option.series[0].data[0], 123.45678)
  }
  assert.deepEqual(data, before)
})

test('pie metric tooltip and percentage label display two decimals without changing slices', () => {
  const data = { columns: ['BU', 'value'], rows: [{ BU: 'C4', value: '1.23456' }, { BU: 'ES', value: '2.34567' }] }
  const before = structuredClone(data)
  const option = buildPieOptions({ xaxis: ['BU'], yaxis: ['value'] }, data)
  assert.equal(option.tooltip.valueFormatter(1.23456), '1.23')
  assert.equal(option.series[0].label.formatter({ name: 'C4', percent: 12.34567 }), 'C4: 12.35%')
  assert.equal(option.series[0].data[0].value, 1.23456)
  assert.deepEqual(data, before)
})
