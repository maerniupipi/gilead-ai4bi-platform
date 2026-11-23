import { createRouter, createWebHistory } from 'vue-router'
import { isAuthenticated } from '../utils/auth'
import Login from '../pages/Login.vue'
import UnifiedLayout from '../layouts/UnifiedLayout.vue'

import KnowledgeAccessList from '../pages/KnowledgeAccessList.vue'
import TableStructureConfig from '../pages/TableStructureConfig.vue'
import KnowledgeTerm from '../pages/KnowledgeTerm.vue'
import SampleLibrary from '../pages/SampleLibrary.vue'
import DataSourceList from '../pages/DataSourceList.vue'
import KnowledgeBaseList from '../pages/KnowledgeBaseList.vue'
import KnowledgeBaseTableStructure from '../pages/KnowledgeBaseTableStructure.vue'
import KnowledgeBaseKnowledgeTerms from '../pages/KnowledgeBaseKnowledgeTerms.vue'
import KnowledgeBaseSampleLibrary from '../pages/KnowledgeBaseSampleLibrary.vue'
import KnowledgeBaseNer from '../pages/KnowledgeBaseNer.vue'
import AutoBIAtomicCapabilities from '../pages/AutoBIAtomicCapabilities.vue'
import AutoBIList from '../pages/AutoBIList.vue'
import AutobiLaboratory from '../pages/AutobiLaboratory.vue'
import AutobiLabTraceLookup from '../pages/AutobiLabTraceLookup.vue'
import AutobiLabTraceView from '../pages/AutobiLabTraceView.vue'
import ModelProviderList from '../pages/ModelProviderList.vue'
import VectorStoreList from '../pages/VectorStoreList.vue'
import OssConfigList from '../pages/OssConfigList.vue'
import ModelCenterLanguageModel from '../pages/ModelCenterLanguageModel.vue'
import ModelCenterVectorModel from '../pages/ModelCenterVectorModel.vue'
import ModelCenterMultimodalModel from '../pages/ModelCenterMultimodalModel.vue'
import ModelCenterEsConfig from '../pages/ModelCenterEsConfig.vue'
import ChatCenter from '../pages/ChatCenter.vue'
import ApiInterface from '../pages/ApiInterface.vue'
import AccountManagement from '../pages/AccountManagement.vue'
import AgentAgentsHome from '../pages/agent-platform/AgentAgentsHome.vue'
import AgentAppVersions from '../pages/agent-platform/AgentAppVersions.vue'
import AgentPlatformLayout from '../pages/agent-platform/AgentPlatformLayout.vue'
import AgentToolsHome from '../pages/agent-platform/AgentToolsHome.vue'
import AgentKnowledgeHome from '../pages/agent-platform/AgentKnowledgeHome.vue'
import AgentPluginsHome from '../pages/agent-platform/AgentPluginsHome.vue'
import SpaceManagement from '../pages/management-center/SpaceManagement.vue'
import AuditLog from '../pages/management-center/AuditLog.vue'
import HelpCenterIndex from '../pages/help-center/HelpCenterIndex.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { title: '登录', requiresAuth: false }
  },
  {
    path: '/xlsx-qa/share/:token',
    name: 'XlsxQaSharePublic',
    component: () => import('../pages/xlsx-qa-share/XlsxQaShareWorkbench.vue'),
    props: true,
    meta: { title: 'XLSX 表格智能问答（分享）', requiresAuth: false }
  },
  {
    path: '/eval/share/:token',
    name: 'EvalSharePublic',
    component: () => import('../pages/eval-share/EvalShareWorkbench.vue'),
    props: true,
    meta: { title: '评测中心（分享）', requiresAuth: false }
  },
  {
    path: '/',
    redirect: '/data-source'
  },
  // ChatBI 模块 - 使用统一布局
  {
    path: '/data-source',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'DataSourceList',
        component: DataSourceList,
        meta: { title: '数据源列表' }
      }
    ]
  },
  {
    path: '/knowledge-access',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'KnowledgeAccessList',
        component: KnowledgeAccessList,
        meta: { title: '数据接入列表' }
      },
      {
        path: ':id/table-structure',
        name: 'TableStructureConfig',
        component: TableStructureConfig,
        props: true,
        meta: { title: '表结构配置' }
      },
      {
        path: ':id/knowledge-term',
        name: 'KnowledgeTerm',
        component: KnowledgeTerm,
        props: true,
        meta: { title: '知识词条' }
      },
      {
        path: ':id/sample-library',
        name: 'SampleLibrary',
        component: SampleLibrary,
        props: true,
        meta: { title: '样例库' }
      }
    ]
  },
  {
    path: '/knowledge-base',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'KnowledgeBaseList',
        component: KnowledgeBaseList,
        meta: { title: '知识中心' }
      },
      {
        path: 'table-structure',
        name: 'KnowledgeBaseTableStructure',
        component: KnowledgeBaseTableStructure,
        meta: { title: '知识库表结构配置' }
      },
      {
        path: 'knowledge-terms',
        name: 'KnowledgeBaseKnowledgeTerms',
        component: KnowledgeBaseKnowledgeTerms,
        meta: { title: '知识库知识词条' }
      },
      {
        path: 'sample-library',
        name: 'KnowledgeBaseSampleLibrary',
        component: KnowledgeBaseSampleLibrary,
        meta: { title: '知识库样例库' }
      },
      {
        path: 'ner',
        name: 'KnowledgeBaseNer',
        component: KnowledgeBaseNer,
        meta: { title: '知识库 ner' }
      }
    ]
  },
  {
    path: '/autobi',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'AutoBIList',
        component: AutoBIList,
        meta: { title: '实验中心' }
      },
      {
        path: 'lab/:projectId',
        name: 'AutobiLaboratory',
        component: AutobiLaboratory,
        meta: { title: '实验中心 · 实验室' }
      }
    ]
  },
  {
    path: '/autobi/lab-trace',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'AutobiLabTraceLookup',
        component: AutobiLabTraceLookup,
        meta: { title: '追踪日志' }
      }
    ]
  },
  {
    path: '/autobi/lab/trace/:traceId',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'AutobiLabTraceView',
        component: AutobiLabTraceView,
        meta: { title: '实验室追踪详情', immersive: true }
      }
    ]
  },
  {
    path: '/autobi-atomic-capabilities',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'AutoBIAtomicCapabilities',
        component: AutoBIAtomicCapabilities,
        meta: { title: '原子能力' }
      }
    ]
  },
  {
    path: '/chat',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'ChatCenter',
        component: ChatCenter,
        meta: { title: '聊天中心' }
      }
    ]
  },
  {
    path: '/api-interface',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'ApiInterface',
        component: ApiInterface,
        meta: { title: '接口文档' }
      }
    ]
  },
  {
    path: '/help-center',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'HelpCenter',
        component: HelpCenterIndex,
        meta: { title: '帮助中心' }
      }
    ]
  },
  // 管理中心 - 使用统一布局
  {
    path: '/management',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/management/model-provider' },
      {
        path: 'model-provider',
        name: 'ManagementLanguageModel',
        component: ModelProviderList,
        meta: { title: '语言模型' }
      },
      {
        path: 'vector-store',
        name: 'ManagementVectorStore',
        component: VectorStoreList,
        meta: { title: '向量库' }
      },
      {
        path: 'oss-config',
        name: 'ManagementOssConfig',
        component: OssConfigList,
        meta: { title: '对象存储' }
      },
      {
        path: 'vector-model',
        name: 'ManagementVectorModel',
        component: ModelCenterVectorModel,
        meta: { title: '向量模型' }
      },
      {
        path: 'multimodal',
        name: 'ManagementMultimodal',
        component: ModelCenterMultimodalModel,
        meta: { title: '多模态模型' }
      },
      {
        path: 'es-config',
        name: 'ManagementEsConfig',
        component: ModelCenterEsConfig,
        meta: { title: 'ES配置' }
      },
      {
        path: 'admin',
        name: 'ManagementAdmin',
        component: AccountManagement,
        meta: { title: '用户管理' }
      },
      {
        path: 'space',
        name: 'ManagementSpace',
        component: SpaceManagement,
        meta: { title: '空间管理' }
      },
      {
        path: 'chatbi-keys',
        name: 'ManagementChatBIKeys',
        redirect: '/management'
      },
      {
        path: 'conversations',
        name: 'ManagementConversations',
        redirect: '/management'
      },
      {
        path: 'audit-log',
        name: 'ManagementAuditLog',
        component: AuditLog,
        meta: { title: '审计日志' }
      },
      {
        path: 'system-logs',
        name: 'ManagementSystemLogs',
        component: () => import('../pages/management-center/SystemLogs.vue'),
        meta: { title: '系统日志' }
      },
      {
        path: 'data-sync',
        name: 'ManagementDataSync',
        component: () => import('../pages/management-center/DataSync.vue'),
        meta: { title: '数据同步' }
      },
    ]
  },
  // 工作流中心 - 使用统一布局
  {
    path: '/agent-platform',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/agent-platform/agents' },
      {
        path: 'agents/:appId/versions/:versionId/design',
        name: 'AgentWorkflowDesign',
        component: () => import('../pages/agent-platform/workflow/AgentWorkflowDesign.vue'),
        props: true,
        meta: { title: '工作流设计' }
      },
      {
        path: 'agents/:appId/versions/:versionId/debug',
        name: 'AgentWorkflowDebug',
        component: () => import('../pages/agent-platform/workflow/AgentWorkflowDebug.vue'),
        props: true,
        meta: { title: '效果测试' }
      },
      {
        path: 'agents/:appId',
        name: 'AgentAppVersions',
        component: AgentAppVersions,
        props: true,
        meta: { title: '工作流配置' }
      },
      {
        path: 'agents',
        name: 'AgentPlatformAgents',
        component: AgentAgentsHome,
        meta: { title: '工作流' }
      },
      {
        path: 'agents/ai-create',
        name: 'AgentAICreatorChat',
        component: () => import('../pages/agent-platform/AgentAICreatorChat.vue'),
        meta: { title: 'AI 创建工作流' }
      },
      {
        path: 'tools',
        name: 'AgentPlatformTools',
        component: AgentToolsHome,
        meta: { title: '工具' }
      },
      {
        path: 'tools/xlsx-qa',
        name: 'XlsxQaHome',
        component: () => import('../pages/agent-platform/tools/XlsxQaHome.vue'),
        meta: { title: 'XLSX 表格智能问答' }
      },
      {
        path: 'tools/xlsx-qa/:moduleId',
        name: 'XlsxQaWorkbench',
        component: () => import('../pages/agent-platform/tools/XlsxQaWorkbench.vue'),
        props: true,
        meta: { title: 'XLSX 问答工作台' }
      },
      {
        path: 'knowledge',
        name: 'AgentPlatformKnowledge',
        component: AgentKnowledgeHome,
        meta: { title: '知识' }
      },
      {
        path: 'plugins',
        name: 'AgentPlatformPlugins',
        component: AgentPluginsHome,
        meta: { title: '插件' }
      },
      {
        path: 'traces',
        name: 'AgentTraceLookup',
        component: () => import('../pages/agent-platform/AgentTraceLookup.vue'),
        meta: { title: '运行日志' }
      },
      {
        path: 'traces/:traceId',
        name: 'AgentTraceView',
        component: () => import('../pages/agent-platform/AgentTraceView.vue'),
        meta: { title: '运行日志详情' }
      }
    ]
  },
  // 评测中心 - 使用统一布局
  {
    path: '/eval',
    component: UnifiedLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/eval/suites' },
      {
        path: 'suites',
        name: 'EvalSuites',
        component: () => import('../pages/eval/EvalSuiteList.vue'),
        meta: { title: '评测集' }
      },
      {
        path: 'suite/create',
        name: 'EvalSuiteCreate',
        component: () => import('../pages/eval/EvalSuiteCreate.vue'),
        meta: { title: '创建评测集' }
      },
      {
        path: 'suite/:id',
        name: 'EvalSuiteDetail',
        component: () => import('../pages/eval/EvalSuiteDetail.vue'),
        props: true,
        meta: { title: '评测集详情' }
      },
      {
        path: 'tasks',
        name: 'EvalTasks',
        component: () => import('../pages/eval/EvalTaskList.vue'),
        meta: { title: '任务管理' }
      },
      {
        path: 'task/create',
        name: 'EvalTaskCreate',
        component: () => import('../pages/eval/EvalTaskCreate.vue'),
        meta: { title: '创建任务' }
      },
      {
        path: 'task/:id',
        name: 'EvalTaskDetail',
        component: () => import('../pages/eval/EvalTaskDetail.vue'),
        props: true,
        meta: { title: '任务详情' }
      },
      {
        path: 'results',
        name: 'EvalResults',
        component: () => import('../pages/eval/EvalResults.vue'),
        meta: { title: '评测结果' }
      },
      {
        path: 'templates',
        name: 'EvalTemplates',
        component: () => import('../pages/eval/EvalTemplateList.vue'),
        meta: { title: '评测模板' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes
})

// 全局前置守卫，设置页面标题和认证检查
router.beforeEach((to, from, next) => {
  if (/^\/(agent-platform|eval)(\/|$)/.test(to.path)) return next('/autobi')
  if (to.meta.title) {
    document.title = `${to.meta.title} - Chat-BI系统`
  }

  // 检查路由是否需要认证
  const requiresAuth = to.meta.requiresAuth !== false

  if (requiresAuth && !isAuthenticated()) {
    next('/login')
    return
  }
  if (to.path === '/login' && isAuthenticated()) {
    next('/')
    return
  }
  next()
})

export default router
