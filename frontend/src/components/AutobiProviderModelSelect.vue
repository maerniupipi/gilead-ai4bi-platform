<template>
  <div class="provider-model-row">
    <el-select
      :model-value="providerId"
      class="split-left"
      filterable
      clearable
      placeholder="请选择供应商"
      @update:model-value="onProviderChange"
    >
      <el-option
        v-for="p in providers"
        :key="p.id"
        :label="p.name"
        :value="p.id"
      />
    </el-select>
    <el-select
      :model-value="modelName"
      class="split-right"
      filterable
      clearable
      placeholder="请选择模型"
      :disabled="!providerId"
      @update:model-value="$emit('update:modelName', $event)"
    >
      <el-option
        v-for="m in modelOptions"
        :key="m"
        :label="m"
        :value="m"
      />
    </el-select>
  </div>
</template>

<script setup>
import { computed } from 'vue'

/** 与 ModelProviderList 保持一致 */
function parseModels(modelsStr) {
  if (!modelsStr) return []
  try {
    const parsed = JSON.parse(modelsStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return String(modelsStr)
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
  }
}

const props = defineProps({
  providerId: {
    type: [Number, String],
    default: null
  },
  modelName: {
    type: String,
    default: ''
  },
  providers: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:providerId', 'update:modelName'])

const modelOptions = computed(() => {
  const p = props.providers.find(x => x.id === props.providerId)
  return p ? parseModels(p.models) : []
})

function onProviderChange(v) {
  emit('update:providerId', v)
  emit('update:modelName', '')
}
</script>

<style scoped>
.provider-model-row {
  display: flex;
  gap: 0;
  width: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  overflow: hidden;
  background: var(--el-fill-color-blank);
}

.split-left {
  flex: 1;
  min-width: 0;
}

.split-right {
  flex: 1;
  min-width: 0;
  border-left: 1px solid var(--el-border-color);
}

.provider-model-row :deep(.split-left .el-select__wrapper),
.provider-model-row :deep(.split-right .el-select__wrapper) {
  box-shadow: none !important;
  border: none !important;
  border-radius: 0;
}

.provider-model-row :deep(.split-left .el-select__wrapper) {
  border-radius: var(--el-border-radius-base) 0 0 var(--el-border-radius-base);
}

.provider-model-row :deep(.split-right .el-select__wrapper) {
  border-radius: 0 var(--el-border-radius-base) var(--el-border-radius-base) 0;
}
</style>
