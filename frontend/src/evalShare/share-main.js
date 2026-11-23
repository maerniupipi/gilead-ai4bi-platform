import { createApp, defineComponent, h } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import { createRouter, createWebHashHistory, RouterView } from 'vue-router'
import EvalShareWorkbench from '@/pages/eval-share/EvalShareWorkbench.vue'

document.documentElement.style.setProperty('--el-color-primary', '#1fb8cc')
document.documentElement.style.setProperty('--el-color-primary-light-3', '#62cdd9')
document.documentElement.style.setProperty('--el-color-primary-light-5', '#8fdce6')
document.documentElement.style.setProperty('--el-color-primary-light-7', '#bceaf0')
document.documentElement.style.setProperty('--el-color-primary-light-8', '#d2f1f5')
document.documentElement.style.setProperty('--el-color-primary-light-9', '#e9f8fa')
document.documentElement.style.setProperty('--el-color-primary-dark-2', '#1993a3')

const MissingToken = defineComponent({
  name: 'EvalShareMissing',
  render() {
    return h('div', {
      style: 'min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f0f2f5;font-family:system-ui;color:#666;padding:24px;text-align:center'
    }, [
      '请通过完整的分享链接访问（',
      h('code', { style: 'background:#e8e8e8;padding:2px 6px;border-radius:4px' }, '#/your-token'),
      '）'
    ])
  }
})

const routes = [
  { path: '/', name: 'share-root', component: MissingToken },
  { path: '/:token', name: 'share', component: EvalShareWorkbench, props: true },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

const RootApp = defineComponent({
  name: 'EvalShareRoot',
  render: () => h(RouterView),
})

const app = createApp(RootApp)
app.use(ElementPlus, { locale: zhCn })
app.use(router)
app.mount('#app')
