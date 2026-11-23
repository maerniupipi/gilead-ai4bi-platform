import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import PageIcon from './components/PageIcon.vue'
import PageHeader from './components/PageHeader.vue'
import IconDataSource from './components/icons/IconDataSource.vue'
import IconKnowledgeAccess from './components/icons/IconKnowledgeAccess.vue'
import IconKnowledgeBase from './components/icons/IconKnowledgeBase.vue'
import IconAutoBI from './components/icons/IconAutoBI.vue'
import IconLabTrace from './components/icons/IconLabTrace.vue'
import IconAtomic from './components/icons/IconAtomic.vue'
import IconModelProvider from './components/icons/IconModelProvider.vue'
import './assets/styles/global.css'
import './styles/agent-platform.css'

const app = createApp(App)

app.use(ElementPlus, {
  locale: zhCn,
})
app.use(router)
app.component('PageIcon', PageIcon)
app.component('PageHeader', PageHeader)
app.component('IconDataSource', IconDataSource)
app.component('IconKnowledgeAccess', IconKnowledgeAccess)
app.component('IconKnowledgeBase', IconKnowledgeBase)
app.component('IconAutoBI', IconAutoBI)
app.component('IconLabTrace', IconLabTrace)
app.component('IconAtomic', IconAtomic)
app.component('IconModelProvider', IconModelProvider)

app.mount('#app')
