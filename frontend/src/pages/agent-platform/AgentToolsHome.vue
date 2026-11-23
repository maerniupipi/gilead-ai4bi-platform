<template>
  <div class="agent-platform-page u-animate-in tools-home">
    <PageHeader
      :breadcrumbs="[{ label: '工作流平台' }, { label: '工具' }]"
    />

    <div class="tools-grid">
      <article
        v-for="tool in visibleTools"
        :key="tool.id"
        class="tool-card"
        :class="{ 'is-disabled': !tool.enabled }"
        @click="onOpen(tool)"
      >
        <div class="tool-card-icon" :style="{ background: tool.accent }">
          <el-icon :size="22"><component :is="tool.icon" /></el-icon>
        </div>
        <div class="tool-card-body">
          <div class="tool-card-title">
            <span>{{ tool.name }}</span>
            <el-tag v-if="tool.badge" size="small" :type="tool.badgeType || 'primary'" round>
              {{ tool.badge }}
            </el-tag>
          </div>
          <div class="tool-card-desc">{{ tool.description }}</div>
          <div v-if="tool.tags?.length" class="tool-card-tags">
            <span v-for="t in tool.tags" :key="t" class="tool-tag">{{ t }}</span>
          </div>
        </div>
        <div class="tool-card-foot">
          <span v-if="!tool.enabled" class="tool-card-disabled-text">即将上线</span>
          <span v-else class="tool-card-cta">打开 →</span>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Grid, DataAnalysis, Connection, Cpu } from '@element-plus/icons-vue'

const router = useRouter()

/**
 * 工具注册表。后续增工具只改这一处：
 *   { id, name, description, icon, accent, to, enabled, badge?, badgeType?, tags? }
 * 需要权限 / 灰度时，可在 visibleTools 里做过滤。
 */
const toolsRegistry = [
  {
    id: 'xlsx-qa',
    name: 'XLSX 表格智能问答',
    description: '上传 Excel 文件，用自然语言提问；AI 会先拆解问题、生成 SQL、逐步下钻，再给出结论。',
    icon: Grid,
    accent: 'linear-gradient(135deg, #34d399 0%, #059669 100%)',
    to: { path: '/agent-platform/tools/xlsx-qa' },
    enabled: true,
    badge: 'Beta',
    tags: ['Excel', 'Text-to-SQL', '下钻分析']
  },
  {
    id: 'bi-insight',
    name: 'BI 洞察助手',
    description: '连接数据源后持续监测指标，出现异常时主动给出诊断与归因。',
    icon: DataAnalysis,
    accent: 'linear-gradient(135deg, #818cf8 0%, #4f46e5 100%)',
    enabled: false
  },
  {
    id: 'api-connector',
    name: 'HTTP / MCP 连接器',
    description: '把第三方 API / MCP 服务封装成可被工作流调用的工具。',
    icon: Connection,
    accent: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
    enabled: false
  },
  {
    id: 'model-runner',
    name: '模型批处理',
    description: '用模型中心配置的大模型跑批量任务，支持并发 / 重试 / 导出结果。',
    icon: Cpu,
    accent: 'linear-gradient(135deg, #38bdf8 0%, #0284c7 100%)',
    enabled: false
  }
]

const visibleTools = computed(() => toolsRegistry)

function onOpen(tool) {
  if (!tool.enabled) {
    ElMessage.info(`「${tool.name}」即将上线，敬请期待`)
    return
  }
  if (tool.to) router.push(tool.to)
}
</script>

<style scoped>
.tools-home {
  padding-bottom: 40px;
}
.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-top: 8px;
}
.tool-card {
  position: relative;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 14px;
  padding: 18px 18px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  cursor: pointer;
  transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
  min-height: 184px;
}
.tool-card:hover {
  border-color: #c6d1e0;
  box-shadow: 0 10px 24px -16px rgba(15, 23, 42, 0.35);
  transform: translateY(-2px);
}
.tool-card.is-disabled {
  cursor: not-allowed;
  opacity: 0.72;
}
.tool-card.is-disabled:hover {
  transform: none;
  box-shadow: none;
}
.tool-card-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 6px 16px -6px rgba(15, 23, 42, 0.3);
}
.tool-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tool-card-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tool-card-desc {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.5;
}
.tool-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}
.tool-tag {
  font-size: 11px;
  color: #4b5563;
  background: #f3f4f6;
  padding: 2px 8px;
  border-radius: 999px;
}
.tool-card-foot {
  display: flex;
  justify-content: flex-end;
  font-size: 12px;
}
.tool-card-cta {
  color: #2563eb;
  font-weight: 500;
}
.tool-card-disabled-text {
  color: #94a3b8;
}
</style>
