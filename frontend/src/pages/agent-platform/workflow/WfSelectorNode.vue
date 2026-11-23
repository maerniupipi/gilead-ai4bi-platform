<template>
  <div
    class="wf-sel"
    :class="{
      'wf-sel--selected': selected,
      [`wf-sel--${data.kind}`]: true
    }"
  >
    <Handle
      class="wf-sel__handle wf-sel__handle--target"
      type="target"
      :position="Position.Left"
    />
    <div class="wf-sel__inner">
      <div class="wf-sel__rail" aria-hidden="true" />
      <div class="wf-sel__body">
        <div v-if="data.caption" class="wf-sel__caption">{{ data.caption }}</div>
        <div class="wf-sel__meta">
          <span class="wf-sel__badge">SELECTOR</span>
          <span class="wf-sel__badge-deco" aria-hidden="true" />
        </div>
        <div class="wf-sel__row">
          <div class="wf-sel__icon-wrap" aria-hidden="true">
            <div class="wf-sel__icon">
              <el-icon><Share /></el-icon>
            </div>
          </div>
          <div class="wf-sel__text">
            <span class="wf-sel__title">{{ data.label }}</span>
            <span class="wf-sel__hint">条件分支 · 按变量匹配走不同下游</span>
            <span v-if="data.description" class="wf-sel__desc">{{ data.description }}</span>
          </div>
          <div v-if="showOps" class="wf-sel__ops" @click.stop @mousedown.stop>
            <el-dropdown trigger="click" @command="onMenuCommand">
              <button type="button" class="wf-sel__gear" aria-label="节点操作">
                <el-icon><Setting /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="copy" :disabled="!canCopy">复制</el-dropdown-item>
                  <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <div class="wf-sel__branches" aria-label="分支出口">
          <div
            v-for="(br, idx) in branchRows"
            :key="br.id"
            class="wf-sel__branch"
            :class="{ 'wf-sel__branch--else': br.tag === 'ELSE' }"
          >
            <div class="wf-sel__branch-main">
              <span class="wf-sel__branch-tag">{{ br.tag }}</span>
              <span v-if="br.tag !== 'ELSE'" class="wf-sel__branch-preview" :title="br.preview">{{ br.preview }}</span>
              <span v-else class="wf-sel__branch-preview">{{ br.preview }}</span>
            </div>
            <Handle
              :id="br.id"
              class="wf-sel__handle wf-sel__handle--source wf-sel__handle--branch"
              type="source"
              :position="Position.Right"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Handle, Position, useNodeId } from '@vue-flow/core'
import { Share, Setting } from '@element-plus/icons-vue'

const OP_LABEL = {
  contains: '包含',
  not_contains: '不包含',
  starts_with: '开始是',
  ends_with: '结束是',
  eq: '是',
  ne: '不是',
  empty: '为空',
  not_empty: '不为空'
}

const props = defineProps({
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false }
})

const nodeId = useNodeId()
const wfGraph = inject('wfGraph', null)

const workflowReadonly = computed(() => {
  const r = wfGraph?.readonly
  if (r == null) return false
  return typeof r.value !== 'undefined' ? !!r.value : !!r
})

const cases = computed(() => {
  const cfg = props.data.selector_config || {}
  const c = cfg.cases
  return Array.isArray(c) && c.length ? c : [{ id: 'case-0', conditions: [{ ref: '', op: 'starts_with', value: '' }] }]
})

const branchRows = computed(() => {
  const rows = []
  cases.value.forEach((c, idx) => {
    const id = (c.id || `case-${idx}`).toString()
    const tag = idx === 0 ? 'IF' : 'ELIF'
    const conds = c.conditions || []
    const p = conds
      .map((x) => {
        const op = OP_LABEL[x.op] || x.op || ''
        const ref = (x.ref || '').trim() || '…'
        const val = (x.value != null ? String(x.value) : '') || '…'
        return `${ref} ${op} ${val}`
      })
      .join(c.relation === 'OR' ? ' 或 ' : ' 且 ')
    rows.push({
      id,
      tag,
      preview: p || '（无条件，不会匹配）'
    })
  })
  rows.push({
    id: 'else',
    tag: 'ELSE',
    preview: '以上均未满足时走此路'
  })
  return rows
})

const showOps = computed(() => !workflowReadonly.value)
const canCopy = computed(() => true)

function onMenuCommand(cmd) {
  if (cmd === 'copy') wfGraph?.duplicateNode?.(nodeId)
  if (cmd === 'delete') wfGraph?.deleteNode?.(nodeId)
}
</script>

<style scoped>
.wf-sel {
  --wf-accent: #2563eb;
  --wf-rail: linear-gradient(180deg, #93c5fd 0%, #3b82f6 42%, #1d4ed8 100%);
  --wf-icon-bg: linear-gradient(145deg, rgba(37, 99, 235, 0.5), rgba(59, 130, 246, 0.14));
  --wf-icon-fg: #1e3a8a;
  --wf-surface: linear-gradient(155deg, rgba(191, 219, 254, 0.55) 0%, #eff6ff 50%, #ffffff 100%);
  --wf-edge: rgba(37, 99, 235, 0.52);
  --wf-muted: #1e40af;

  position: relative;
  min-width: 220px;
  max-width: 300px;
  border-radius: 14px;
  border: 2px solid var(--wf-edge);
  background: var(--wf-surface);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.65) inset,
    0 2px 8px rgba(15, 23, 42, 0.06);
  transition:
    transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.wf-sel:hover {
  transform: translateY(-1px);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.7) inset,
    0 6px 20px rgba(15, 23, 42, 0.09);
}

.wf-sel--selected {
  border-color: rgba(var(--el-color-primary-rgb), 0.55);
  box-shadow:
    0 0 0 1px rgba(var(--el-color-primary-rgb), 0.25),
    0 0 0 3px rgba(var(--el-color-primary-rgb), 0.12),
    0 8px 24px rgba(15, 23, 42, 0.08);
}

.wf-sel__inner {
  display: flex;
  align-items: stretch;
  border-radius: 13px;
  overflow: hidden;
}

.wf-sel__rail {
  width: 7px;
  flex-shrink: 0;
  background: var(--wf-rail);
  box-shadow:
    1px 0 0 rgba(255, 255, 255, 0.45) inset,
    -1px 0 0 rgba(0, 0, 0, 0.06) inset;
}

.wf-sel__body {
  flex: 1 1 auto;
  min-width: 0;
  padding: 10px 10px 8px 10px;
}

.wf-sel__caption {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #94a3b8;
  margin-bottom: 6px;
}

.wf-sel__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.wf-sel__badge {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
  font-family: ui-monospace, 'SFMono-Regular', 'Menlo', monospace;
  color: var(--wf-accent);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.8);
}

.wf-sel__badge-deco {
  flex: 1 1 auto;
  height: 1px;
  min-width: 12px;
  background: linear-gradient(90deg, var(--wf-accent), transparent);
  opacity: 0.35;
  border-radius: 1px;
}

.wf-sel__row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
  margin-bottom: 8px;
}

.wf-sel__icon-wrap {
  flex-shrink: 0;
  padding: 2px;
  border-radius: 12px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0));
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
}

.wf-sel__icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  background: var(--wf-icon-bg);
  color: var(--wf-icon-fg);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.65) inset;
}

.wf-sel__text {
  flex: 1 1 auto;
  min-width: 0;
  padding-top: 1px;
}

.wf-sel__title {
  display: block;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.03em;
  line-height: 1.25;
}

.wf-sel__hint {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.45;
  color: var(--wf-muted);
  opacity: 0.92;
}

.wf-sel__desc {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  line-height: 1.45;
  color: #475467;
  max-height: 32px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wf-sel__ops {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  margin-top: -2px;
}

.wf-sel__gear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.65);
  color: var(--wf-muted);
  cursor: pointer;
  transition:
    background 0.18s ease,
    color 0.18s ease;
}

.wf-sel__gear:hover {
  background: rgba(15, 23, 42, 0.06);
  color: #0f172a;
}

.wf-sel__branches {
  border-top: 1px solid rgba(15, 23, 42, 0.08);
  padding-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wf-sel__branch {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 30px;
  padding: 4px 0 4px 2px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.45);
}

.wf-sel__branch-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.wf-sel__branch-tag {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.06em;
  color: var(--wf-accent);
  font-family: ui-monospace, monospace;
  min-width: 36px;
}

.wf-sel__branch-preview {
  font-size: 11px;
  color: #475467;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wf-sel__handle {
  width: 11px !important;
  height: 11px !important;
  border-width: 2px !important;
  border-color: var(--wf-accent) !important;
  background: #fff !important;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
}

.wf-sel__handle--target {
  left: -6px !important;
}

.wf-sel__handle--branch {
  position: relative !important;
  right: auto !important;
  top: auto !important;
  transform: none !important;
  flex-shrink: 0;
}
</style>
