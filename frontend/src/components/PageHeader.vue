<template>
  <header class="page-header">
    <div class="page-header__left">
      <div class="page-header__icon">
        <slot name="icon">
          <PageIcon />
        </slot>
      </div>
      <nav class="page-header__breadcrumb" aria-label="Breadcrumb">
        <template v-for="(item, idx) in breadcrumbs" :key="idx">
          <span v-if="idx > 0" class="page-header__sep">/</span>
          <component
            :is="item.to ? 'router-link' : 'span'"
            :to="item.to"
            class="page-header__crumb"
            :class="{ 'is-link': !!item.to, 'is-current': idx === breadcrumbs.length - 1 }"
          >
            {{ item.label }}
          </component>
        </template>
      </nav>
    </div>
    <div class="page-header__right" v-if="$slots.extra || $slots.actions">
      <div v-if="$slots.extra" class="page-header__extra">
        <slot name="extra" />
      </div>
      <div v-if="$slots.actions" class="page-header__actions">
        <slot name="actions" />
      </div>
    </div>
  </header>
</template>

<script setup>
defineProps({
  breadcrumbs: {
    type: Array,
    required: true,
    // [{ label: '数据集', to: '/knowledge-access' }, { label: '表结构配置' }]
  }
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 20px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--color-gray-200, #e8eaef);
  min-height: 48px;
  gap: 16px;
}

.page-header__left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.page-header__icon {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  color: var(--el-color-primary, #1fb8cc);
}

.page-header__breadcrumb {
  display: flex;
  align-items: center;
  gap: 0;
  min-width: 0;
  flex-wrap: wrap;
}

.page-header__sep {
  display: inline-flex;
  align-items: center;
  margin: 0 8px;
  font-size: 14px;
  color: var(--color-gray-300, #d1d5db);
  user-select: none;
}

.page-header__crumb {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-gray-400, #9ca3af);
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.18s ease;
}

.page-header__crumb.is-link {
  color: var(--color-gray-500, #5c6370);
}

.page-header__crumb.is-link:hover {
  color: var(--el-color-primary, #1fb8cc);
}

.page-header__crumb.is-current {
  color: var(--color-gray-900, #1a1d23);
  font-weight: 600;
}

.page-header__right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  margin-left: auto;
}

.page-header__extra {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
