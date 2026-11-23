import { createApp, defineComponent, h } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import { createRouter, createWebHashHistory, RouterView } from 'vue-router'
import XlsxQaShareWorkbench from '@/pages/xlsx-qa-share/XlsxQaShareWorkbench.vue'
import { initLang } from '@/utils/xlsxQaI18n'

// 分享页默认英文（首次访问，不覆盖用户已保存的偏好）
initLang('en')

document.documentElement.style.setProperty('--el-color-primary', '#1fb8cc')
document.documentElement.style.setProperty('--el-color-primary-light-3', '#62cdd9')
document.documentElement.style.setProperty('--el-color-primary-light-5', '#8fdce6')
document.documentElement.style.setProperty('--el-color-primary-light-7', '#bceaf0')
document.documentElement.style.setProperty('--el-color-primary-light-8', '#d2f1f5')
document.documentElement.style.setProperty('--el-color-primary-light-9', '#e9f8fa')
document.documentElement.style.setProperty('--el-color-primary-dark-2', '#1993a3')

const MissingToken = defineComponent({
  name: 'XlsxShareMissing',
  render() {
    return h('div', {
      style: 'min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f8fafc;font-family:system-ui;color:#64748b;padding:24px;text-align:center'
    }, [
      'Please open via a full share link (',
      h('code', { style: 'background:#e2e8f0;padding:2px 6px;border-radius:4px' }, '#/your-token'),
      ').'
    ])
  }
})

const routes = [
  { path: '/', name: 'share-root', component: MissingToken },
  { path: '/:token', name: 'share', component: XlsxQaShareWorkbench, props: true },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 使用 RouterView 组件而非内联 template 字符串，避免运行时模板编译问题
const RootApp = defineComponent({
  name: 'ShareRoot',
  render: () => h(RouterView),
})

const app = createApp(RootApp)
app.use(ElementPlus, { locale: zhCn })
app.use(router)
app.mount('#app')
