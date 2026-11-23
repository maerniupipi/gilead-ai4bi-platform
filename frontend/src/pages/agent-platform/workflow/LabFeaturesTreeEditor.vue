<template>
  <div class="lab-fe lab-fe--root">
    <div v-if="!fieldKeys.length" class="lab-fe__empty">
      <p class="lab-fe__empty-title">尚未配置 features 字段</p>
      <p class="lab-fe__empty-hint">仅支持平铺字段。每个字段可选「常量」或「引用」，常量会自动识别字符串/数字/布尔。</p>
    </div>

    <div v-else class="lab-fe__items">
      <div v-for="(key, idx) in fieldKeys" :key="fieldRowKey(key)" class="lab-fe__item lab-fe__item--card">
        <div class="lab-fe__item-head">
          <span class="lab-fe__item-index">字段 {{ idx + 1 }}</span>
          <el-button text type="danger" size="small" class="lab-fe__rm" @click="removeKey(key)">移除</el-button>
        </div>

        <div class="lab-fe__grid">
          <label class="lab-fe__l">键名</label>
          <el-input
            size="small"
            class="lab-fe__inp"
            :model-value="keyDrafts[key] ?? key"
            placeholder="如 disease、stage"
            @keydown.stop
            @update:model-value="(value) => keyDrafts[key] = value"
            @blur="onRenameKey(key)"
            @keydown.enter.stop.prevent="onRenameKey(key)"
          />

          <label class="lab-fe__l">模式</label>
          <el-radio-group :model-value="fieldMode(key)" size="small" @change="(m) => setFieldMode(key, m)">
            <el-radio-button label="const">常量</el-radio-button>
            <el-radio-button label="ref">引用</el-radio-button>
          </el-radio-group>

          <label class="lab-fe__l">取值</label>
          <div class="lab-fe__val-body">
            <el-input
              v-if="fieldMode(key) === 'const'"
              :model-value="displayConstValue(key)"
              size="small"
              placeholder="输入文本，或 true/false/数字（自动识别）"
              @keydown.stop
              @update:model-value="(v) => setFieldConstValue(key, v)"
            />
            <el-select
              v-else
              :model-value="fieldRefValue(key)"
              size="small"
              filterable
              allow-create
              placeholder="选择上游变量"
              class="lab-fe__sel"
              @keydown.stop
              @change="(v) => setFieldRefValue(key, v)"
            >
              <el-option v-for="opt in upstreamVarOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
            <p class="lab-fe__typed-hint">
              当前类型：<b>{{ fieldRuntimeTypeLabel(key) }}</b>
            </p>
          </div>
        </div>
      </div>
    </div>

    <div class="lab-fe__footer">
      <el-button type="primary" plain size="small" class="lab-fe__btn" @click="addKey">
        <el-icon class="lab-fe__btn-ic"><Plus /></el-icon>
        文本字段
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

defineOptions({ name: 'LabFeaturesTreeEditor' })

const props = defineProps({
  modelValue: { type: Object, required: true },
  upstreamVarOptions: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:modelValue'])

const keyDrafts = ref({})
const fieldIds = new Map()
let nextFieldId = 0

function fieldRowKey(key) {
  if (!fieldIds.has(key)) fieldIds.set(key, ++nextFieldId)
  return fieldIds.get(key)
}

const sanitizedModel = computed(() => {
  const src = props.modelValue && typeof props.modelValue === 'object' && !Array.isArray(props.modelValue) ? props.modelValue : {}
  const ret = {}
  for (const [k, v] of Object.entries(src)) {
    if (!k) continue
    if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') ret[k] = v
  }
  return ret
})

const fieldKeys = computed(() => Object.keys(sanitizedModel.value))

watch(fieldKeys, (keys) => {
  const current = new Set(keys)
  for (const key of Object.keys(keyDrafts.value)) {
    if (!current.has(key)) delete keyDrafts.value[key]
  }
  for (const key of fieldIds.keys()) {
    if (!current.has(key)) fieldIds.delete(key)
  }
})

function emitModelValue(v) {
  emit('update:modelValue', v)
}

function nextModel() {
  return { ...sanitizedModel.value }
}

function fieldValue(key) {
  return sanitizedModel.value[key]
}

function extractRefExpr(val) {
  if (typeof val !== 'string') return ''
  const s = val.trim()
  if (!s.startsWith('{{') || !s.endsWith('}}')) return ''
  return s.slice(2, -2).trim()
}

function fieldMode(key) {
  return extractRefExpr(fieldValue(key)) ? 'ref' : 'const'
}

function fieldRefValue(key) {
  return extractRefExpr(fieldValue(key))
}

function fieldRuntimeTypeLabel(key) {
  const v = fieldValue(key)
  if (fieldMode(key) === 'ref') return '引用变量'
  if (typeof v === 'boolean') return '布尔'
  if (typeof v === 'number') return '数字'
  return '字符串'
}

function displayConstValue(key) {
  const v = fieldValue(key)
  if (v == null) return ''
  return String(v)
}

function setFieldValue(key, value) {
  const copy = nextModel()
  copy[key] = value
  emitModelValue(copy)
}

function parseLiteralInput(raw) {
  const s = String(raw ?? '').trim()
  if (!s) return ''
  if (/^(true|false)$/i.test(s)) return s.toLowerCase() === 'true'
  if (/^-?(?:\d+|\d*\.\d+)$/.test(s)) {
    const n = Number(s)
    if (Number.isFinite(n)) return n
  }
  return String(raw ?? '')
}

function setFieldConstValue(key, raw) {
  setFieldValue(key, parseLiteralInput(raw))
}

function setFieldRefValue(key, refExpr) {
  const expr = String(refExpr || '').trim()
  setFieldValue(key, expr ? `{{${expr}}}` : '')
}

function setFieldMode(key, mode) {
  if (mode === 'ref') {
    const dflt = props.upstreamVarOptions?.[0]?.value || '用户输入.input'
    setFieldValue(key, `{{${dflt}}}`)
    return
  }
  const current = fieldValue(key)
  const refExpr = extractRefExpr(current)
  if (refExpr) {
    setFieldValue(key, '')
  }
}

function onRenameKey(oldKey, rawNew) {
  const newKey = String(rawNew ?? keyDrafts.value[oldKey] ?? oldKey).trim()
  if (!newKey) {
    ElMessage.warning('键名不能为空')
    keyDrafts.value[oldKey] = oldKey
    return
  }
  if (newKey === oldKey) {
    keyDrafts.value[oldKey] = oldKey
    return
  }
  const copy = JSON.parse(JSON.stringify(props.modelValue || {}))
  if (Object.prototype.hasOwnProperty.call(copy, newKey)) {
    ElMessage.warning('键名已存在')
    keyDrafts.value[oldKey] = oldKey
    return
  }
  // Commit once, after typing, retaining the original field's position and value.
  const renamed = Object.fromEntries(Object.entries(copy).map(([key, value]) => [key === oldKey ? newKey : key, value]))
  fieldIds.set(newKey, fieldRowKey(oldKey))
  keyDrafts.value[newKey] = newKey
  emitModelValue(renamed)
}

function uniqueChildKey(parent, base) {
  let nk = base
  let i = 1
  while (Object.prototype.hasOwnProperty.call(parent, nk)) nk = `${base}_${i++}`
  return nk
}

function addKey() {
  const copy = nextModel()
  copy[uniqueChildKey(copy, 'new_field')] = ''
  emitModelValue(copy)
}

function removeKey(key) {
  const copy = nextModel()
  delete copy[key]
  emitModelValue(copy)
}
</script>

<style scoped>
.lab-fe {
  --lab-accent: #be185d;
  --lab-accent-soft: rgba(190, 24, 93, 0.08);
  --lab-line: rgba(15, 23, 42, 0.08);
  font-family: inherit;
}

.lab-fe--root {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.lab-fe__empty {
  padding: 12px;
  border-radius: 10px;
  border: 1px dashed var(--lab-line);
  background: #fff;
  text-align: center;
}

.lab-fe__empty-title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: #475467;
}

.lab-fe__empty-hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  color: #98a2b3;
}

.lab-fe__items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lab-fe__item--card {
  padding: 10px 12px 12px;
  border-radius: 10px;
  border: 1px solid var(--lab-line);
  background: #fff;
  box-shadow: none;
}

.lab-fe__item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.lab-fe__item-index {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--lab-accent);
  text-transform: uppercase;
}

.lab-fe__rm {
  flex-shrink: 0;
}

.lab-fe__grid {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 8px 10px;
  align-items: start;
}

.lab-fe__l {
  font-size: 12px;
  font-weight: 600;
  color: #667085;
  padding-top: 5px;
  line-height: 1.3;
}

.lab-fe__inp,
.lab-fe__sel,
.lab-fe__val-body {
  min-width: 0;
}

.lab-fe__val-body {
  width: 100%;
}

.lab-fe__typed-hint {
  margin: 6px 0 0;
  font-size: 11px;
  color: #98a2b3;
}

.lab-fe__typed-hint b {
  color: #667085;
  font-weight: 600;
}

.lab-fe__footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 2px;
}

.lab-fe__btn {
  border-radius: 8px;
  font-weight: 600;
  border-color: rgba(190, 24, 93, 0.35);
  color: var(--lab-accent);
}

.lab-fe__btn:hover {
  border-color: var(--lab-accent);
  background: var(--lab-accent-soft);
}

.lab-fe__btn-ic {
  margin-right: 4px;
  vertical-align: middle;
}
</style>
