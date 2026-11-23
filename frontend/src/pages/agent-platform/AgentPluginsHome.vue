<template>
  <div class="agent-platform-page u-animate-in plugins-skills-page">
    <PageHeader
      :breadcrumbs="[{ label: '工作流平台' }, { label: '插件' }]"
    />

    <div class="agent-surface-panel agent-surface-panel--block plugins-skills-panel">
      <div class="skills-market-head">
        <div class="skills-market-head__text">
          <h2 class="skills-market-title">Skills市场</h2>
          <p class="skills-market-note">可在工作流LLM中使用（灰度测试中）</p>
        </div>
        <span class="skills-market-badge" aria-label="功能待开放">待开放</span>
      </div>

      <div class="skills-card-grid" aria-label="通用 Skills 预览">
        <article
          v-for="item in skillItems"
          :key="item.id"
          class="skill-card"
          tabindex="0"
        >
          <span class="skill-card__cat">{{ item.category }}</span>
          <div class="skill-card__header">
            <div class="skill-card__icon" aria-hidden="true">{{ item.icon }}</div>
            <div class="skill-card__titles">
              <h3 class="skill-card__name">{{ item.title }}</h3>
              <p class="skill-card__ns">{{ item.namespace }}</p>
            </div>
          </div>
          <p class="skill-card__desc">{{ item.description }}</p>
          <div class="skill-card__footer">
            <span class="skill-card__stat">
              <span class="skill-card__stat-icon" aria-hidden="true">◇</span>
              {{ item.stat }}
            </span>
            <span class="skill-card__tags">{{ item.tags }}</span>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<script setup>
/** 占位展示：与 Dify 插件市场类似的卡片信息架构，后续对接真实市场数据 */
const skillItems = [
  {
    id: 'web-fetch',
    category: '工具',
    icon: '🌐',
    title: '网页抓取与正文提取',
    namespace: 'studio / web_fetch',
    description: '为工作流拉取指定 URL 的正文与元信息，适合资料汇总与事实核对。',
    stat: '428',
    tags: '# 工具  ·  # 检索'
  },
  {
    id: 'ppt-outline',
    category: '生成',
    icon: '📊',
    title: '演示大纲生成',
    namespace: 'studio / deck_outline',
    description: '根据主题与受众生成演示结构、章节要点与讲稿提示，便于快速成稿。',
    stat: '512',
    tags: '# 生成  ·  # 办公'
  },
  {
    id: 'amazon-scrape',
    category: '数据',
    icon: '🛒',
    title: '电商列表解析',
    namespace: 'connectors / listing_parse',
    description: '解析公开商品列表页的结构化字段，用于比价与竞品监控类场景。',
    stat: '301',
    tags: '# 数据  ·  # 解析'
  },
  {
    id: 'serp',
    category: '检索',
    icon: '🔎',
    title: '实时搜索摘要',
    namespace: 'search / live_serp',
    description: '发起检索并返回摘要片段与引用链接，供 LLM 在回答中引用最新信息。',
    stat: '667',
    tags: '# 检索  ·  # 实时'
  },
  {
    id: 'image-gen',
    category: '模型',
    icon: '🖼️',
    title: '文生图 / 图生图',
    namespace: 'models / image_gen',
    description: '根据自然语言或参考图生成配图，支持多种比例与风格关键词。',
    stat: '891',
    tags: '# 模型  ·  # 多模态'
  },
  {
    id: 'code-runner',
    category: '工具',
    icon: '⚡',
    title: '安全代码沙箱',
    namespace: 'runtime / safe_python',
    description: '在受限环境中执行短脚本，用于数据处理、格式转换与小规模计算。',
    stat: '354',
    tags: '# 工具  ·  # 代码'
  },
  {
    id: 'querit',
    category: '检索',
    icon: '📎',
    title: '知识片段召回',
    namespace: 'rag / chunk_retrieve',
    description: '按向量与关键词混合召回知识库切片，并返回可溯源的段落与得分。',
    stat: '540',
    tags: '# 检索  ·  # RAG'
  },
  {
    id: 'mcp-relay',
    category: '集成',
    icon: '🔗',
    title: 'MCP 工具桥接',
    namespace: 'mcp / auth_relay',
    description: '将远程 MCP 工具以统一协议暴露给工作流，支持按用户 OAuth 与限流。',
    stat: '276',
    tags: '# 集成  ·  # MCP'
  }
]
</script>

<style scoped>
.plugins-skills-page {
  max-width: 1280px;
}

.plugins-skills-panel {
  padding: 22px 22px 26px;
}

.skills-market-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--ap-border, #e5e7eb);
}

.skills-market-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ap-text, #0f172a);
}

.skills-market-note {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--ap-muted, #64748b);
}

.skills-market-badge {
  flex-shrink: 0;
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #94a3b8;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  padding: 5px 12px;
  border-radius: 8px;
  user-select: none;
}

.skills-card-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 1100px) {
  .skills-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .skills-card-grid {
    grid-template-columns: 1fr;
  }
}

.skill-card {
  position: relative;
  background: var(--ap-surface, #fff);
  border: 1px solid var(--ap-border, #e8edf0);
  border-radius: 12px;
  padding: 16px 16px 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.skill-card:hover {
  border-color: rgba(var(--el-color-primary-rgb, 61, 141, 130), 0.22);
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.07);
}

.skill-card__cat {
  position: absolute;
  top: 14px;
  right: 14px;
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.02em;
}

.skill-card__header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding-right: 48px;
}

.skill-card__icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-size: 22px;
  line-height: 1;
  background: linear-gradient(
    145deg,
    rgba(var(--el-color-primary-rgb, 61, 141, 130), 0.14),
    rgba(var(--el-color-primary-rgb, 61, 141, 130), 0.05)
  );
  border: 1px solid rgba(15, 23, 42, 0.06);
  flex-shrink: 0;
}

.skill-card__titles {
  min-width: 0;
}

.skill-card__name {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--ap-text, #0f172a);
  letter-spacing: -0.02em;
  line-height: 1.35;
}

.skill-card__ns {
  margin: 4px 0 0;
  font-size: 12px;
  color: #94a3b8;
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  line-height: 1.4;
  word-break: break-all;
}

.skill-card__desc {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: #64748b;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skill-card__footer {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  font-size: 12px;
  color: #94a3b8;
}

.skill-card__stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
  color: #64748b;
}

.skill-card__stat-icon {
  font-size: 10px;
  opacity: 0.65;
}

.skill-card__tags {
  flex: 1;
  min-width: 0;
  line-height: 1.4;
}
</style>
