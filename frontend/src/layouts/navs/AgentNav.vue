<template>
  <BaseNav :navGroups="navGroups" />
</template>

<script setup>
import { Cpu, Clock } from '@element-plus/icons-vue'
import BaseNav from './BaseNav.vue'

const navGroups = [
  {
    label: '工作流',
    items: [
      { path: '/agent-platform/agents', label: '工作流', icon: Cpu, prefix: '/agent-platform/agents' }
    ]
  },
  {
    label: '监控',
    items: [
      { path: '/agent-platform/traces', label: '运行日志', icon: Clock, prefix: '/agent-platform/traces' }
    ]
  }
]
</script>
