<template>
  <div id="app">
    <!-- 登录页、XLSX 分享页：全屏，不走任何布局 -->
    <router-view v-if="isLoginRoute || isXlsxShareStandaloneRoute" />
    <!-- 其他所有路由：走统一布局（由路由的根组件提供） -->
    <router-view v-else />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { provideSpaceContext } from './utils/spaceContext'

provideSpaceContext()

const route = useRoute()

const isLoginRoute = computed(() => route.path === '/login')
const isXlsxShareStandaloneRoute = computed(() => route.path.startsWith('/xlsx-qa/share'))
</script>

<style>
/* Global reset — design tokens are in styles/global.css */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans SC', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--color-gray-900, #1a1d23);
  background: var(--color-gray-50, #f8f9fb);
}

#app {
  height: 100%;
}

/* 全局滚动条样式 */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

/* Element Plus 覆盖 */
.el-dropdown-menu {
  border-radius: 12px !important;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12) !important;
  border: 1px solid #e8eaef !important;
  padding: 8px !important;
}

.el-dropdown-menu__item {
  border-radius: 8px !important;
  padding: 10px 16px !important;
  font-size: 14px !important;
}

.el-dropdown-menu__item:hover {
  background: #f1f3f8 !important;
  color: #1a1d23 !important;
}

.el-dropdown-menu__item--divided {
  margin-top: 8px !important;
  border-top: 1px solid #e8eaef !important;
}
</style>
