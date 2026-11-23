<template>
  <BaseEdge :path="pathData.path" :marker-end="markerEnd" :interaction-width="24" :style="edgeLineStyle" />
  <EdgeLabelRenderer>
    <div
      v-if="!workflowReadonly"
      class="wf-edge-plus nodrag nopan"
      :style="labelStyle"
      @dblclick.stop="toggleDelete"
    >
      <el-dropdown
        trigger="click"
        popper-class="agent-workflow-node-dropdown"
        @command="onPickKind"
        @click.stop
      >
        <button type="button" class="wf-edge-plus__btn" aria-label="在连线中插入节点" @mousedown.stop @click.stop>
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
            <el-dropdown-item divided command="__delete__" class="wf-edge-plus__delete-item">
              删除这条连线
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <button
        v-if="showDelete"
        type="button"
        class="wf-edge-plus__del"
        aria-label="删除连线"
        title="删除连线"
        @mousedown.stop
        @click.stop="onDelete"
      >
        <el-icon><Close /></el-icon>
      </button>
    </div>
  </EdgeLabelRenderer>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@vue-flow/core'
import { Plus, Close } from '@element-plus/icons-vue'
import {
  Cpu,
  Document,
  Avatar,
  MagicStick,
  Link,
  Flag,
  Share,
  SetUp
} from '@element-plus/icons-vue'

const props = defineProps({
  id: { type: String, required: true },
  sourceX: { type: Number, required: true },
  sourceY: { type: Number, required: true },
  targetX: { type: Number, required: true },
  targetY: { type: Number, required: true },
  sourcePosition: { type: [String, Number], required: true },
  targetPosition: { type: [String, Number], required: true },
  markerEnd: { type: String, default: undefined },
  style: { type: Object, default: null },
  source: { type: String, required: true },
  target: { type: String, required: true }
})

const wfGraph = inject('wfGraph', null)
const showDelete = ref(false)

const workflowReadonly = computed(() => {
  const r = wfGraph?.readonly
  if (r == null) return false
  return typeof r.value !== 'undefined' ? !!r.value : !!r
})

const palette = computed(() => {
  const p = wfGraph?.palette
  if (p == null) return []
  const items = typeof p.value !== 'undefined' ? p.value : p
  return items.filter(item => item.kind !== 'output')
})

const pathData = computed(() => {
  const [path, labelX, labelY] = getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    targetX: props.targetX,
    targetY: props.targetY,
    sourcePosition: props.sourcePosition,
    targetPosition: props.targetPosition,
    curvature: 0.35
  })
  return { path, labelX, labelY }
})

const labelStyle = computed(() => ({
  position: 'absolute',
  transform: `translate(-50%, -50%) translate(${pathData.value.labelX}px, ${pathData.value.labelY}px)`,
  pointerEvents: 'all'
}))

const edgeLineStyle = computed(() => props.style || undefined)

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

function onPickKind(kind) {
  if (kind === '__delete__') {
    onDelete()
    return
  }
  wfGraph?.insertNodeOnEdge?.(props.id, kind)
}

function onDelete() {
  if (props.id) {
    wfGraph?.deleteEdge?.(props.id)
  } else {
    wfGraph?.deleteEdgeByLink?.(props.source, props.target)
  }
  showDelete.value = false
}

function toggleDelete() {
  showDelete.value = !showDelete.value
}
</script>

<style scoped>
.wf-edge-plus {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.wf-edge-plus__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid #e4e7ec;
  border-radius: 999px;
  background: #fff;
  color: var(--el-color-primary);
  cursor: pointer;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.12);
  transition:
    transform 0.12s ease,
    box-shadow 0.12s ease;
}

.wf-edge-plus__btn:hover {
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.14);
  transform: scale(1.05);
}

.wf-edge-plus__del {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid #fecaca;
  border-radius: 999px;
  background: #fff1f2;
  color: #b42318;
  cursor: pointer;
  box-shadow: 0 1px 4px rgba(180, 35, 24, 0.15);
}

.wf-edge-plus__del:hover {
  background: #ffe4e6;
}
</style>
