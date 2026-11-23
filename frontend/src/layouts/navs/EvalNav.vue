<template>
  <BaseNav :navGroups="navGroups" />
</template>

<script setup>
import { Collection, List, Document } from '@element-plus/icons-vue'
import BaseNav from './BaseNav.vue'

const navGroups = [
  {
    label: '评测',
    items: [
      { path: '/eval/suites', label: '评测集', icon: Collection },
      { path: '/eval/tasks', label: '任务历史', icon: List },
      { path: '/eval/templates', label: '评测模板', icon: Document }
    ]
  }
]
</script>
