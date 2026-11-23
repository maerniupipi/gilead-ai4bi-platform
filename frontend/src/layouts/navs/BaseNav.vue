<template>
  <nav class="unified-nav">
    <!-- 导航分组 -->
    <div
      v-for="group in getFilteredGroups()"
      :key="group.label"
      class="nav-group"
    >
      <div v-if="group.label" class="nav-group-label">{{ group.label }}</div>
      <div class="nav-group-items">
        <router-link
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ 'is-active': isActive(item) }"
        >
          <div class="nav-item-indicator"></div>
          <div class="nav-item-icon">
            <el-icon><component :is="item.icon" /></el-icon>
          </div>
          <span class="nav-item-text">{{ item.label }}</span>
          <div class="nav-item-badge" v-if="item.badge">{{ item.badge }}</div>
        </router-link>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useRoute } from 'vue-router'

const props = defineProps({
  navGroups: {
    type: Array,
    required: true
  }
})

const route = useRoute()

// 所有平台配置入口对已登录用户可见。
function getFilteredGroups() {
  return props.navGroups
}

function isActive(item) {
  const path = route.path
  // 精确匹配
  if (path === item.path) return true
  // prefix: 通用前缀匹配（如 /agent-platform/traces 匹配 /agent-platform/traces/xxx）
  if (item.prefix && path.startsWith(item.prefix)) return true
  // excludePrefix: 匹配前缀但排除特定子路径
  if (item.excludePrefix) {
    const excluded = (item.excludePrefixExclude || []).some(ex => path === ex)
    return path.startsWith(item.excludePrefix) && !excluded
  }
  // 子路径匹配
  if (item.children) {
    return item.children.some(child =>
      path === child.path || path.startsWith(child.path + '/')
    )
  }
  return false
}
</script>

<style scoped>
.unified-nav {
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 分组 */
.nav-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-group-label {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-gray-400);
  padding: 0 var(--space-3);
  margin-bottom: 6px;
}

.nav-group-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* 导航项 */
.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 10px var(--space-3);
  border-radius: var(--radius-md);
  color: var(--color-gray-500);
  text-decoration: none;
  font-size: var(--text-base);
  font-weight: 500;
  transition: all var(--transition-normal);
  overflow: hidden;
}

.nav-item:hover {
  background: var(--color-gray-100);
  color: var(--color-gray-900);
}

.nav-item.is-active {
  background: var(--brand-chatbi-soft);
  color: var(--el-color-primary);
}

/* 左侧激活指示条 */
.nav-item-indicator {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%) scaleY(0);
  width: 3px;
  height: 20px;
  background: linear-gradient(180deg, var(--el-color-primary), var(--el-color-primary-light-5));
  border-radius: 0 3px 3px 0;
  transition: transform var(--transition-normal);
}

.nav-item.is-active .nav-item-indicator {
  transform: translateY(-50%) scaleY(1);
}

/* 图标 */
.nav-item-icon {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border-radius: var(--radius-sm);
  transition: all var(--transition-normal);
  flex-shrink: 0;
}

.nav-item-icon .el-icon {
  font-size: 18px;
}

.nav-item:hover .nav-item-icon {
  background: rgba(var(--el-color-primary-rgb), 0.08);
}

.nav-item.is-active .nav-item-icon {
  background: rgba(var(--el-color-primary-rgb), 0.15);
}

/* 文字 */
.nav-item-text {
  flex: 1;
  line-height: 1.3;
}

/* 徽章 */
.nav-item-badge {
  padding: 2px 8px;
  font-size: var(--text-xs);
  font-weight: 600;
  background: var(--el-color-primary);
  color: var(--color-white);
  border-radius: 10px;
}
</style>
