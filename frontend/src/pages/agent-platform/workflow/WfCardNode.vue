<template>
  <div
    class="wf-card"
    :class="{
      'wf-card--selected': selected,
      [`wf-card--${data.kind}`]: true
    }"
  >
    <Handle
      v-if="showTarget"
      class="wf-card__handle wf-card__handle--target"
      type="target"
      :position="Position.Left"
    />
    <div class="wf-card__inner">
      <div class="wf-card__rail" aria-hidden="true" />
      <div class="wf-card__body">
        <div v-if="data.caption" class="wf-card__caption">{{ data.caption }}</div>
        <div class="wf-card__meta">
          <span class="wf-card__badge">{{ kindBadge }}</span>
          <span class="wf-card__badge-deco" aria-hidden="true" />
        </div>
        <div class="wf-card__row">
          <div class="wf-card__icon-wrap" aria-hidden="true">
            <div class="wf-card__icon">
              <el-icon><component :is="icon" /></el-icon>
            </div>
          </div>
          <div class="wf-card__text">
            <span class="wf-card__title">{{ data.label }}</span>
            <span class="wf-card__hint">{{ roleHint }}</span>
            <span v-if="data.description" class="wf-card__desc">{{ data.description }}</span>
            <span v-if="configurationIssues.length" class="wf-card__validation" :title="configurationIssues.join('；')">待配置 · {{ configurationIssues.length }} 项</span>
          </div>
          <div v-if="showOps" class="wf-card__ops" @click.stop @mousedown.stop>
            <el-dropdown trigger="click" @command="onMenuCommand">
              <button type="button" class="wf-card__gear" aria-label="节点操作">
                <el-icon><Setting /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="copy" :disabled="!canCopy">复制</el-dropdown-item>
                  <el-dropdown-item command="delete" :disabled="!canDelete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </div>
    </div>
    <Handle
      v-if="showSource"
      class="wf-card__handle wf-card__handle--source"
      type="source"
      :position="Position.Right"
    />
    <div
      v-if="showLeafPlus"
      class="wf-card__leaf-plus nodrag nopan"
      @click.stop
      @mousedown.stop
    >
      <el-dropdown trigger="click" popper-class="agent-workflow-node-dropdown" @command="onAddKind">
        <button type="button" class="wf-card__plus-btn" aria-label="向后添加节点">
          <el-icon><Plus /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu class="agent-workflow-node-menu">
            <el-dropdown-item v-for="item in palette" :key="item.kind" :command="item.kind">
              <span class="agent-workflow-node-menu__row">
                <span class="agent-workflow-node-menu__icon" :class="`is-${item.kind}`">
                  <el-icon><component :is="iconFor(item.kind)" /></el-icon>
                </span>
                {{ item.label }}
              </span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { Handle, Position, useNodeId, useVueFlow } from '@vue-flow/core'
import {
  House,
  Flag,
  Cpu,
  Document,
  Avatar,
  MagicStick,
  Link,
  VideoPlay,
  Plus,
  Setting,
  Share,
  SetUp
} from '@element-plus/icons-vue'
import { nodeConfigurationIssues } from './workflowContracts.js'

const props = defineProps({
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false }
})

const configurationIssues = computed(() => nodeConfigurationIssues({ data: props.data }))
const nodeId = useNodeId()
const { edges } = useVueFlow()
const wfGraph = inject('wfGraph', null)

const workflowReadonly = computed(() => {
  const r = wfGraph?.readonly
  if (r == null) return false
  return typeof r.value !== 'undefined' ? !!r.value : !!r
})

const palette = computed(() => {
  const p = wfGraph?.palette
  if (p == null) return []
  return typeof p.value !== 'undefined' ? p.value : p
})

const showTarget = computed(() => props.data.kind !== 'start')
const showSource = computed(() => props.data.kind !== 'output')

const isLeaf = computed(() => !edges.value.some((e) => e.source === nodeId))

const showLeafPlus = computed(() => showSource.value && isLeaf.value && !workflowReadonly.value)
const showOps = computed(() => props.data.kind !== 'start' && !workflowReadonly.value)

const canCopy = computed(() => props.data.kind !== 'start' && props.data.kind !== 'userInput') // 开始和用户输▶入不可复制

const canDelete = computed(() => props.data.kind !== 'start' && props.data.kind !== 'userInput')

const kindBadge = computed(() => {
  const m = {
    start: 'ENTRY',
    userInput: 'INPUT',
    llm: 'LLM',
    script: 'SCRIPT',
    selector: 'SELECT',
    agent: 'AGENT',
    lab: 'LAB',
    atomic: 'ATOMIC',
    externalApi: 'HTTP',
    output: 'OUTPUT'
  }
  return m[props.data.kind] || 'NODE'
})

const roleHint = computed(() => {
  const m = {
    start: '流程起点 · 从此处开始执行',
    userInput: '收集用户消息与附件 · 对话入口',
    llm: '大语言模型 · 推理、改写与结构化输出',
    script: 'Python 3 · 类型化入参与字典返回',
    selector: '条件分支 · 按变量匹配走不同路径',
    agent: '编排子工作流 · 工具与多步推理',
    lab: '实验中心 · 流水线与追踪',
    atomic: 'ChatBI 原子能力 · 召回、生成 SQL 与执行 SQL',
    externalApi: 'REST / OpenAPI · 第三方服务',
    output: '汇总结果 · 对用户或下游返回'
  }
  return m[props.data.kind] || ''
})

const icon = computed(() => {
  const k = props.data.kind
  if (k === 'start') return VideoPlay
  if (k === 'userInput') return House
  if (k === 'llm') return Cpu
  if (k === 'script') return Document
  if (k === 'agent') return Avatar
  if (k === 'lab') return MagicStick
  if (k === 'atomic') return SetUp
  if (k === 'externalApi') return Link
  if (k === 'selector') return Share
  if (k === 'output') return Flag
  return Cpu
})

function iconFor(kind) {
  const map = {
    llm: Cpu,
    script: Document,
    selector: Share,
    agent: Avatar,
    lab: MagicStick,
    atomic: SetUp,
    externalApi: Link,
    output: Flag
  }
  return map[kind] || Cpu
}

function onMenuCommand(cmd) {
  if (cmd === 'copy') wfGraph?.duplicateNode?.(nodeId)
  if (cmd === 'delete') wfGraph?.deleteNode?.(nodeId)
}

function onAddKind(kind) {
  wfGraph?.addNodeAfter?.(nodeId, kind)
}
</script>

<style scoped>
.wf-card__validation { display: block; margin-top: 5px; font-size: 11px; color: #b45309; }
.wf-card {
  --wf-accent: #64748b;
  --wf-accent-rgb: 100, 116, 139;
  --wf-icon-bg: rgba(var(--wf-accent-rgb), 0.08);
  --wf-icon-fg: #334155;
  --wf-edge: rgba(var(--wf-accent-rgb), 0.26);
  --wf-muted: #64748b;

  position: relative;
  width: 320px;
  min-width: 320px;
  max-width: 360px;
  border-radius: 12px;
  border: 1px solid var(--wf-edge);
  background: #ffffff;
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.04),
    0 10px 28px rgba(15, 23, 42, 0.06);
  transition:
    transform 0.16s ease,
    box-shadow 0.2s ease,
    border-color 0.2s ease;
}

.wf-card:hover {
  transform: translateY(-1px);
  box-shadow:
    0 2px 5px rgba(15, 23, 42, 0.05),
    0 16px 36px rgba(15, 23, 42, 0.09);
}

.wf-card--selected {
  border-color: rgba(var(--wf-accent-rgb), 0.62);
  box-shadow:
    0 0 0 3px rgba(var(--wf-accent-rgb), 0.12),
    0 14px 34px rgba(15, 23, 42, 0.09);
}

.wf-card--start {
  --wf-accent: #0ea5e9;
  --wf-accent-rgb: 14, 165, 233;
  --wf-icon-fg: #0369a1;
  --wf-muted: #0369a1;
}

.wf-card--userInput {
  --wf-accent: #2563eb;
  --wf-accent-rgb: 37, 99, 235;
  --wf-icon-fg: #1e3a8a;
  --wf-muted: #1e40af;
}

.wf-card--llm {
  --wf-accent: #4f46e5;
  --wf-accent-rgb: 79, 70, 229;
  --wf-icon-fg: #312e81;
  --wf-muted: #3730a3;
}

.wf-card--script {
  --wf-accent: #0f766e;
  --wf-accent-rgb: 15, 118, 110;
  --wf-icon-fg: #134e4a;
  --wf-muted: #115e59;
}

.wf-card--agent {
  --wf-accent: #7c3aed;
  --wf-accent-rgb: 124, 58, 237;
  --wf-icon-fg: #4c1d95;
  --wf-muted: #5b21b6;
}

.wf-card--lab {
  --wf-accent: #be185d;
  --wf-accent-rgb: 190, 24, 93;
  --wf-icon-fg: #9d174d;
  --wf-muted: #9d174d;
}

.wf-card--atomic {
  --wf-accent: #7c3aed;
  --wf-accent-rgb: 124, 58, 237;
  --wf-icon-fg: #5b21b6;
  --wf-muted: #6d28d9;
}

.wf-card--externalApi {
  --wf-accent: #c2410c;
  --wf-accent-rgb: 194, 65, 12;
  --wf-icon-fg: #7c2d12;
  --wf-muted: #9a3412;
}

.wf-card--output {
  --wf-accent: #be123c;
  --wf-accent-rgb: 190, 18, 60;
  --wf-icon-fg: #881337;
  --wf-muted: #9f1239;
}

.wf-card__inner {
  display: flex;
  align-items: stretch;
  border-radius: 12px;
  overflow: hidden;
}

.wf-card__rail {
  width: 5px;
  flex-shrink: 0;
  background: var(--wf-accent);
}

.wf-card__body {
  flex: 1 1 auto;
  min-width: 0;
  padding: 16px 18px 16px 16px;
}

.wf-card__caption {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #94a3b8;
  margin-bottom: 6px;
}

.wf-card__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.wf-card__badge {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  font-family: ui-monospace, 'SFMono-Regular', 'Menlo', monospace;
  color: var(--wf-accent);
}

.wf-card__badge-deco {
  flex: 1 1 auto;
  height: 1px;
  min-width: 12px;
  background: rgba(var(--wf-accent-rgb), 0.14);
  border-radius: 1px;
}

.wf-card__row {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.wf-card__icon-wrap {
  flex-shrink: 0;
  padding: 0;
  border-radius: 12px;
}

.wf-card__icon {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  background: var(--wf-icon-bg);
  color: var(--wf-icon-fg);
  border: 1px solid rgba(var(--wf-accent-rgb), 0.18);
}

.wf-card__text {
  flex: 1 1 auto;
  min-width: 0;
}

.wf-card__title {
  display: block;
  font-size: 17px;
  font-weight: 750;
  color: #0f172a;
  letter-spacing: 0;
  line-height: 1.3;
}

.wf-card__hint {
  display: block;
  margin-top: 5px;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.5;
  color: #64748b;
}

.wf-card__desc {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.45;
  color: #475467;
  max-height: 36px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.wf-card__ops {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  align-self: flex-start;
  margin-top: -6px;
  margin-right: -8px;
}

.wf-card__gear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: var(--wf-muted);
  cursor: pointer;
  transition:
    background 0.18s ease,
    color 0.18s ease;
}

.wf-card__gear:hover {
  background: rgba(var(--wf-accent-rgb), 0.08);
  color: var(--wf-accent);
}

.wf-card__handle {
  width: 13px !important;
  height: 13px !important;
  border-width: 2px !important;
  border-color: var(--wf-accent) !important;
  background: #fff !important;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
}

.wf-card__handle--target {
  left: -7px !important;
}

.wf-card__handle--source {
  right: -7px !important;
}

.wf-card__leaf-plus {
  position: absolute;
  right: -46px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  pointer-events: auto;
}

.wf-card__plus-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 999px;
  background: #ffffff;
  color: var(--wf-accent);
  cursor: pointer;
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.08),
    0 8px 18px rgba(15, 23, 42, 0.08);
  transition:
    transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1),
    box-shadow 0.18s ease;
}

.wf-card__plus-btn:hover {
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.12);
  transform: scale(1.08);
}
</style>
