import { createApp, defineComponent, h } from 'vue'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import 'element-plus/dist/index.css'
import { createRouter, createWebHashHistory, RouterView } from 'vue-router'
import AutobiLabShareWorkbench from '@/pages/autobi-lab-share/AutobiLabShareWorkbench.vue'

document.documentElement.style.setProperty('--el-color-primary', '#1fb8cc')

const MissingToken = defineComponent({
  name: 'LabShareMissing',
  render() {
    return h('div', {
      style: 'display:flex;align-items:center;justify-content:center;height:100vh;font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#606266;font-size:15px;'
    }, [
      '请通过完整的分享链接访问（',
      h('code', { style: 'background:#f0f2f5;padding:2px 6px;border-radius:4px;' }, '#/your-token'),
      '）。'
    ])
  }
})

const routes = [
  { path: '/', name: 'share-root', component: MissingToken },
  { path: '/:token', name: 'share', component: AutobiLabShareWorkbench, props: true },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

const RootApp = defineComponent({
  name: 'LabShareRoot',
  render: () => h(RouterView),
})

const app = createApp(RootApp)
app.use(ElementPlus, { locale: zhCn })
app.use(router)
app.mount('#app')
