<template>
  <div class="unified-layout">
    <!-- 顶部栏 -->
    <header class="unified-header" v-if="!isImmersive && !isWorkflowFullBleed">
      <div class="header-left">
        <!-- Logo 区域 -->
        <div class="header-brand">
          <img :src="brandLogo" class="brand-img" alt="AI4BI" />
          <span class="brand-text">AI4BI</span>
        </div>
      </div>

      <!-- 中间：模块切换器 -->
      <div class="header-center">
        <ModuleSwitcher />
      </div>

      <div class="header-right">
        <!-- 空间切换 -->
        <SpaceSwitcher />

        <div class="header-separator"></div>

        <span class="header-welcome">{{ welcomeName }}</span>
        <el-dropdown @command="handleCommand" trigger="click">
          <div class="user-avatar-wrap">
            <el-avatar class="user-avatar" :size="32">{{ avatarText }}</el-avatar>
          </div>
          <template #dropdown>
            <el-dropdown-menu class="user-dropdown">
              <el-dropdown-item command="logout" divided>
                退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 主体区域 -->
    <div class="unified-body">
      <!-- 左侧导航 -->
      <aside class="unified-aside" v-if="!isImmersive && !isAgentMainNoAside && !isWorkflowFullBleed">
        <component :is="currentNav" />
      </aside>

      <!-- 主内容区 -->
      <main
        class="unified-main"
        :class="{
          'is-full': isImmersive || isAgentContentFill || isWorkflowFullBleed,
          'is-fill': isAgentContentFill || isWorkflowFullBleed
        }"
      >
        <router-view v-slot="{ Component, route: viewRoute }">
          <KeepAlive v-if="isWorkflowFullBleed" :key="workflowWorkspaceKey" include="AgentWorkflowDebug">
            <component :is="Component" :key="viewRoute.name" />
          </KeepAlive>
          <component :is="Component" v-else />
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { removeAuthToken, getCurrentUser, getCurrentSpaceId } from '@/utils/auth'
import SpaceSwitcher from '@/components/SpaceSwitcher.vue'
import ModuleSwitcher from './ModuleSwitcher.vue'
import ChatBINav from './navs/ChatBINav.vue'
import ManagementNav from './navs/ManagementNav.vue'
import AgentNav from './navs/AgentNav.vue'
import EvalNav from './navs/EvalNav.vue'
import brandLogo from '@/assets/images/logo.png'

const route = useRoute()
const router = useRouter()

// 根据路由判断当前模块和导航组件
const currentModule = computed(() => {
  const path = route.path
  if (path.startsWith('/management')) return 'management'
  if (path.startsWith('/agent-platform')) return 'agent'
  if (path.startsWith('/eval')) return 'eval'
  return 'chatbi'
})

// Sync body data-module for theme switching
watch(currentModule, (mod) => {
  document.body.setAttribute('data-module', mod)
}, { immediate: true })

onMounted(() => {
  document.body.setAttribute('data-module', currentModule.value)
})

onUnmounted(() => {
  document.body.removeAttribute('data-module')
})

const navMap = {
  chatbi: ChatBINav,
  management: ManagementNav,
  agent: AgentNav,
  eval: EvalNav
}

const currentNav = computed(() => navMap[currentModule.value] || ChatBINav)

// 沉浸模式
const isImmersive = computed(() => Boolean(route.meta.immersive))

// 工作流全屏
const isWorkflowFullBleed = computed(
  () => route.name === 'AgentWorkflowDesign' || route.name === 'AgentWorkflowDebug'
)
// Keep an in-flight test alive only while switching tabs of the same workflow.
// Leaving this workspace (or changing space/version) unmounts it and cancels work.
const workflowWorkspaceKey = computed(
  () => `${getCurrentSpaceId() || ''}:${route.params.appId}:${route.params.versionId}`
)

// 智能体主区铺满但保留系统侧边栏的页面
const isAgentContentFill = computed(
  () =>
    currentModule.value === 'agent' &&
    (route.name === 'AgentPlatformAgents' ||
      route.name === 'AgentAICreatorChat' ||
      route.name === 'XlsxQaWorkbench' ||
      route.name === 'AgentTraceView')
)

// 智能体下需要隐藏系统侧边栏的沉浸式页面
const isAgentMainNoAside = computed(
  () =>
    currentModule.value === 'agent' &&
    (route.name === 'AgentAICreatorChat' ||
      route.name === 'XlsxQaWorkbench')
)

const welcomeName = computed(() => {
  const u = getCurrentUser()
  if (!u) return '访客'
  const n = (u.displayName || u.username || '').trim()
  return n ? `欢迎回来，${n}` : '欢迎'
})

const avatarText = computed(() => {
  const u = getCurrentUser()
  if (!u) return '?'
  const n = (u.displayName || u.username || '').trim()
  if (!n) return '?'
  return Array.from(n)[0] || '?'
})

const handleCommand = (command) => {
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      removeAuthToken()
      router.push('/login')
    }).catch(() => {})
  }
}
</script>

<style scoped>
/* === 布局容器 === */
.unified-layout {
  --header-height: 60px;
  --aside-width: 220px;

  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--color-gray-50);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans SC', sans-serif;
}

/* === 顶部栏 === */
.unified-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: var(--header-height);
  padding: 0 var(--space-6);
  background: var(--color-white);
  border-bottom: 1px solid var(--color-gray-200);
  flex-shrink: 0;
  box-shadow: var(--shadow-xs);
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  min-width: 200px;
}

.header-center {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}

.brand-img {
  height: 36px;
  width: auto;
  vertical-align: middle;
}

.brand-text {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-gray-900);
  letter-spacing: -0.02em;
}

.header-separator {
  width: 1px;
  height: 28px;
  background: var(--color-gray-200);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.header-welcome {
  font-size: var(--text-sm);
  color: var(--color-gray-500);
  font-weight: 500;
}

.user-avatar-wrap {
  cursor: pointer;
  padding: 2px;
  border-radius: 50%;
  transition: var(--transition-fast);
}

.user-avatar-wrap:hover {
  background: var(--color-gray-100);
}

.user-avatar {
  --el-avatar-bg-color: var(--brand-chatbi-soft);
  --el-avatar-text-color: var(--brand-chatbi);
  background: var(--brand-chatbi-soft) !important;
  color: var(--brand-chatbi) !important;
  font-weight: 600;
  font-size: 14px;
  border: 2px solid transparent;
  transition: var(--transition-fast);
}

.user-avatar-wrap:hover .user-avatar {
  border-color: var(--el-color-primary);
}

/* === 主体区域 === */
.unified-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* === 左侧导航 === */
.unified-aside {
  width: var(--aside-width);
  background: var(--color-white);
  border-right: 1px solid var(--color-gray-200);
  overflow-y: auto;
  flex-shrink: 0;
  box-shadow: var(--shadow-xs);
}

/* === 主内容区 === */
.unified-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--space-6) var(--space-8);
  transition: var(--transition-normal);
}

.unified-main.is-full {
  padding: 0;
}

/* 铺满型页面：主区不单独滚动，由子页面内部控制滚动，避免整页双滚动条 */
.unified-main.is-fill {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
}
</style>
