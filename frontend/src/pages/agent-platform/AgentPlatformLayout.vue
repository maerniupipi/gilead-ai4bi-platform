<template>
  <div v-if="isWorkflowFullBleed" class="agent-workflow-shell">
    <router-view />
  </div>
  <div v-else class="agent-platform-root">
    <aside class="agent-platform-aside" aria-label="工作流平台导航">
      <div class="agent-platform-aside-title">工作室</div>
      <nav class="agent-platform-nav">
        <router-link
          v-for="item in nav"
          :key="item.path"
          :to="item.path"
          class="agent-platform-nav-item"
          :class="{ 'is-active': isNavActive(item) }"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>
    <main
      class="agent-platform-main"
      :class="{ 'agent-platform-main--fill': isAgentMainFill }"
    >
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Tools, Collection, Cpu, SetUp } from '@element-plus/icons-vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isWorkflowFullBleed = computed(
  () => route.name === 'AgentWorkflowDesign' || route.name === 'AgentWorkflowDebug'
)

/** 主区铺满、padding 清零：工作流列表左右栏滚动；AI 共创全屏聊天；XLSX 问答工作台三栏 */
const isAgentMainFill = computed(
  () =>
    route.name === 'AgentPlatformAgents' ||
    route.name === 'AgentAICreatorChat' ||
    route.name === 'XlsxQaWorkbench'
)

const nav = [
  { path: '/agent-platform/agents', label: '工作流', icon: Cpu },
  { path: '/agent-platform/tools', label: '工具', icon: Tools },
  { path: '/agent-platform/knowledge', label: '知识', icon: Collection },
  { path: '/agent-platform/plugins', label: '插件', icon: SetUp }
]

function isNavActive(item) {
  if (item.path === '/agent-platform/agents') {
    return (
      route.path === '/agent-platform/agents' ||
      /^\/agent-platform\/agents\/.+/.test(route.path)
    )
  }
  return route.path === item.path || route.path.startsWith(`${item.path}/`)
}
</script>
