<template>
  <BaseNav :navGroups="navGroups" />
</template>

<script setup>
import {
  Connection,
  Document,
  Box,
  Tools,
  List,
  Odometer,
  ChatDotRound,
  Connection as ApiIcon,
  QuestionFilled
} from '@element-plus/icons-vue'
import BaseNav from './BaseNav.vue'

const navGroups = [
  {
    label: '数据',
    items: [
      { path: '/data-source', label: '数据中心', icon: Connection },
      { path: '/knowledge-access', label: '知识引擎', icon: Document },
      { path: '/knowledge-base', label: '知识中心', icon: Box }
    ]
  },
  {
    label: '实验室',
    items: [
      { path: '/autobi', label: '实验中心', icon: Tools, excludePrefix: '/autobi', excludePrefixExclude: ['/autobi/lab-trace', '/autobi-atomic-capabilities'] },
      { path: '/autobi/lab-trace', label: '追踪日志', icon: List },
      { path: '/autobi-atomic-capabilities', label: '原子能力', icon: Odometer }
    ]
  },
  {
    label: '运维',
    items: [
      { path: '/chat', label: '聊天中心', icon: ChatDotRound },
      { path: '/api-interface', label: '接口文档', icon: ApiIcon },
      { path: '/help-center', label: '帮助中心', icon: QuestionFilled }
    ]
  }
]
</script>
