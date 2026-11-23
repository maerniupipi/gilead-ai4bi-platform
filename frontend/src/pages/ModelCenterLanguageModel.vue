<template>
  <div class="model-center-page">
    <PageHeader
      :breadcrumbs="[{ label: '模型中心' }, { label: '语言模型' }]"
    >
      <template #actions>
        <el-button type="primary" @click="$router.push('/model-provider')">前往管理</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="never">
          <template #header>当前语言模型入口</template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="说明">继续沿用现有模型供应商页面</el-descriptions-item>
            <el-descriptions-item label="功能">API Key、模型列表、连接测试</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>快捷操作</template>
          <el-space direction="vertical" fill style="width:100%">
            <el-button @click="$router.push('/model-provider')">打开供应商配置</el-button>
            <el-button @click="$router.push('/model-provider/vector-store')">打开向量库配置</el-button>
          </el-space>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>
