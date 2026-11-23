<template>
  <BaseNav :navGroups="navGroups" />
</template>

<script setup>
import {
  Connection,
  Cpu,
  Monitor,
  Box,
  Document,
  Folder,
  Setting,
  List,
  Lock,
  Goods,
  Refresh
} from '@element-plus/icons-vue'
import BaseNav from './BaseNav.vue'

const navGroups = [
  {
    label: '模型配置',
    items: [
      { path: '/management/model-provider', label: '语言模型', icon: Connection },
      { path: '/management/vector-model', label: '向量模型', icon: Cpu },
      { path: '/management/multimodal', label: '多模态模型', icon: Monitor, adminOnly: true }
    ]
  },
  {
    label: '存储与服务',
    items: [
      { path: '/management/vector-store', label: '向量库', icon: Box },
      { path: '/management/oss-config', label: '对象存储', icon: Goods },
      { path: '/management/es-config', label: 'ES 配置', icon: Document }
    ]
  },
  {
    label: '系统管理',
    items: [
      { path: '/management/space', label: '空间管理', icon: Folder, adminOnly: true },
      { path: '/management/admin', label: '用户管理', icon: Setting },
      { path: '/management/data-sync', label: '数据同步', icon: Refresh, adminOnly: true },
      { path: '/management/audit-log', label: '审计日志', icon: List, adminOnly: true },
      { path: '/management/system-logs', label: '系统日志', icon: Document }
    ]
  }
]
</script>
