<template>
  <div class="module-switcher">
    <div class="module-tabs">
      <button
        v-for="item in modules"
        :key="item.key"
        class="module-tab"
        :class="{ 'is-active': currentModule === item.key }"
        @click="handleSwitch(item)"
      >
        <el-icon class="tab-icon"><component :is="item.icon" /></el-icon>
        <span class="tab-label">{{ item.label }}</span>
        <div class="tab-indicator" v-if="currentModule === item.key"></div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { DataAnalysis, Setting, Cpu, Collection } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const modules = [
  { key: 'chatbi', label: 'ChatBI', icon: DataAnalysis, path: '/data-source' },
  { key: 'labs', label: '实验室', icon: Cpu, path: '/autobi' },
  { key: 'management', label: '管理', icon: Setting, path: '/management' }
]

const currentModule = computed(() => {
  const path = route.path
  if (path.startsWith('/management')) return 'management'
  if (path.startsWith('/autobi')) return 'labs'
  return 'chatbi'
})

function handleSwitch(item) {
  if (currentModule.value !== item.key) {
    router.push(item.path)
  }
}
</script>

<style scoped>
.module-switcher {
  display: flex;
  align-items: center;
}

.module-tabs {
  display: flex;
  align-items: center;
  background: var(--color-gray-100);
  border-radius: var(--radius-md);
  padding: 4px;
  gap: 2px;
}

.module-tab {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-gray-500);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-normal);
  white-space: nowrap;
}

.module-tab:hover:not(.is-active) {
  color: var(--color-gray-900);
  background: rgba(255, 255, 255, 0.6);
}

.module-tab.is-active {
  background: var(--color-white);
  color: var(--el-color-primary);
  box-shadow: 0 2px 8px rgba(var(--el-color-primary-rgb), 0.15);
}

.tab-icon {
  font-size: 15px;
  transition: transform var(--transition-normal);
}

.module-tab.is-active .tab-icon {
  transform: scale(1.1);
}

.tab-label {
  line-height: 1;
}

.tab-indicator {
  position: absolute;
  bottom: 2px;
  left: 50%;
  transform: translateX(-50%);
  width: 16px;
  height: 3px;
  background: linear-gradient(90deg, var(--el-color-primary), var(--el-color-primary-light-3));
  border-radius: 2px;
}
</style>
