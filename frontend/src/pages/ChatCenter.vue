<template>
  <div class="chat-center">
    <PageHeader :breadcrumbs="[{ label: '聊天中心' }]">
      <template #actions>
        <el-tooltip content="清空当前对话" placement="bottom">
          <el-button text :icon="Delete" @click="handleClear" :disabled="messages.length === 0 && !streaming">
            清空对话
          </el-button>
        </el-tooltip>
      </template>
    </PageHeader>

    <div class="chat-body">
      <!-- 左侧参数面板 -->
      <aside class="params-panel">
        <!-- 模型配置区 -->
        <div class="panel-section">
          <div class="section-title">
            <span class="section-dot" />
            模型配置
          </div>
          <div class="section-body">
            <div class="field">
              <label class="field-label">供应商</label>
              <el-select
                v-model="providerId"
                placeholder="选择供应商"
                size="default"
                @change="handleProviderChange"
                class="field-select"
              >
                <el-option
                  v-for="p in activeProviders"
                  :key="p.id"
                  :label="p.name"
                  :value="p.id"
                />
              </el-select>
            </div>
            <div class="field">
              <label class="field-label">模型</label>
              <el-select
                v-model="model"
                placeholder="选择模型"
                size="default"
                :disabled="!providerId"
                class="field-select"
              >
                <el-option
                  v-for="m in providerModels"
                  :key="m"
                  :label="m"
                  :value="m"
                />
              </el-select>
            </div>
          </div>
        </div>

        <!-- 参数调节区 -->
        <div class="panel-section">
          <div class="section-title">
            <span class="section-dot" />
            推理参数
          </div>
          <div class="section-body">
            <div class="field">
              <div class="field-row">
                <label class="field-label">Temperature</label>
                <span class="field-val">{{ params.temperature.toFixed(1) }}</span>
              </div>
              <el-slider
                v-model="params.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                :show-tooltip="false"
              />
            </div>
            <div class="field">
              <div class="field-row">
                <label class="field-label">Max Tokens</label>
                <span class="field-val">{{ params.max_tokens }}</span>
              </div>
              <el-slider
                v-model="params.max_tokens"
                :min="100"
                :max="8000"
                :step="100"
                :show-tooltip="false"
              />
            </div>
            <div class="field">
              <div class="field-row">
                <label class="field-label">Top P</label>
                <span class="field-val">{{ params.top_p.toFixed(1) }}</span>
              </div>
              <el-slider
                v-model="params.top_p"
                :min="0"
                :max="1"
                :step="0.1"
                :show-tooltip="false"
              />
            </div>
          </div>
        </div>

        <!-- 系统提示词区 -->
        <div class="panel-section panel-section--grow">
          <div class="section-title">
            <span class="section-dot section-dot--alt" />
            系统提示词
          </div>
          <div class="section-body section-body--fill">
            <el-input
              v-model="systemPrompt"
              type="textarea"
              :rows="5"
              placeholder="可选：设置系统级提示词，引导模型行为..."
              class="system-input"
            />
          </div>
        </div>

        <!-- 快捷键提示 -->
        <div class="panel-footer">
          <span class="hint-key">Ctrl + Enter</span>
          <span class="hint-label">发送</span>
          <span class="hint-sep">·</span>
          <span class="hint-key">Esc</span>
          <span class="hint-label">停止</span>
        </div>
      </aside>

      <!-- 右侧对话区域 -->
      <main class="chat-area">
        <!-- 消息列表 -->
        <div class="messages-container" ref="messagesContainer">
          <div v-if="messages.length === 0" class="empty-state">
            <div class="empty-icon">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <rect x="4" y="8" width="40" height="28" rx="4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="M14 20h12M14 26h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <circle cx="36" cy="36" r="8" fill="var(--brand-chatbi-soft)" stroke="var(--brand-chatbi)" stroke-width="1.5"/>
                <path d="M34.5 36l1 1 2-2" stroke="var(--brand-chatbi)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <p class="empty-title">开始对话</p>
            <p class="empty-desc">选择一个模型，输入你的问题，获取 AI 实时回复</p>
          </div>

          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            class="message-item"
            :class="msg.role"
          >
            <!-- 头像 -->
            <div class="msg-avatar">
              <template v-if="msg.role === 'user'">
                <el-avatar :size="32" class="avatar-user">
                  <el-icon :size="16"><UserFilled /></el-icon>
                </el-avatar>
              </template>
              <template v-else>
                <div class="avatar-bot">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <rect x="3" y="4" width="18" height="13" rx="2" stroke="currentColor" stroke-width="1.5"/>
                    <path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    <path d="M9 10h2M13 10h2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                </div>
              </template>
            </div>

            <!-- 消息体 -->
            <div class="msg-body">
              <div class="msg-meta">
                <span class="msg-role">{{ msg.role === 'user' ? '你' : model || 'AI' }}</span>
                <span class="msg-time">{{ msg.time }}</span>
                <el-button
                  v-if="msg.role === 'assistant' && msg.content"
                  text
                  size="small"
                  class="msg-copy-btn"
                  @click="handleCopy(msg.content)"
                >
                  <el-icon :size="14"><DocumentCopy /></el-icon>
                </el-button>
              </div>
              <div
                class="msg-content"
                :class="{ 'is-markdown': msg.role === 'assistant' }"
              >
                <template v-if="msg.role === 'assistant'">
                  <div v-html="renderMarkdown(msg.content)" class="markdown-body" />
                </template>
                <template v-else>
                  {{ msg.content }}
                </template>
              </div>
            </div>
          </div>

          <!-- 流式生成中的临时气泡 -->
          <div v-if="streaming && streamingText" class="message-item assistant">
            <div class="msg-avatar">
              <div class="avatar-bot streaming">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <rect x="3" y="4" width="18" height="13" rx="2" stroke="currentColor" stroke-width="1.5"/>
                  <path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                  <path d="M9 10h2M13 10h2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
              </div>
            </div>
            <div class="msg-body">
              <div class="msg-meta">
                <span class="msg-role">{{ model || 'AI' }}</span>
                <span class="msg-time streaming-tag">生成中...</span>
              </div>
              <div class="msg-content is-markdown">
                <div v-html="renderMarkdown(streamingText)" class="markdown-body" />
              </div>
            </div>
          </div>

          <!-- 加载指示器（等待首字节） -->
          <div v-if="streaming && !streamingText" class="typing-indicator">
            <span class="typing-dot" />
            <span class="typing-dot" />
            <span class="typing-dot" />
          </div>
        </div>

        <!-- 输入区域 -->
        <div class="input-area">
          <div class="input-wrapper">
            <el-input
              ref="inputRef"
              v-model="inputText"
              type="textarea"
              :rows="1"
              :autosize="{ minRows: 1, maxRows: 5 }"
              placeholder="输入消息... (Ctrl+Enter 发送)"
              :disabled="streaming"
              @keydown="handleKeydown"
              @compositionstart="isComposing = true"
              @compositionend="isComposing = false"
              class="chat-input"
            />
            <div class="input-actions">
              <span v-if="inputText.length > 0" class="char-count">{{ inputText.length }}</span>
              <el-button
                v-if="streaming"
                type="danger"
                :icon="VideoPause"
                @click="handleStop"
                round
              >
                停止
              </el-button>
              <el-button
                v-else
                type="primary"
                :icon="Promotion"
                :disabled="!inputText.trim() || !providerId || !model"
                @click="handleSend"
                round
              >
                发送
              </el-button>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Delete, Promotion, UserFilled, DocumentCopy, VideoPause
} from '@element-plus/icons-vue'
import { Marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark-dimmed.css'
import { getModelProviders } from '../api/modelProvider'
import { streamChatMessage } from '../api/chat'

// --------------- Markdown renderer setup ---------------
const marked = new Marked(
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value
      }
      return hljs.highlightAuto(code).value
    }
  })
)

marked.setOptions({ breaks: true, gfm: true })

const renderMarkdown = (text) => {
  if (!text) return ''
  try {
    return marked.parse(text)
  } catch {
    return text
  }
}

// --------------- State ---------------
const params = reactive({
  temperature: 0.7,
  max_tokens: 2000,
  top_p: 0.9
})

const providers = ref([])
const providerId = ref(null)
const model = ref('')
const systemPrompt = ref('')
const inputText = ref('')
const messages = ref([])
const streaming = ref(false)
const streamingText = ref('')
const isComposing = ref(false)

const messagesContainer = ref(null)
const inputRef = ref(null)

let abortController = null

// --------------- Computed ---------------
const activeProviders = computed(() =>
  providers.value.filter(p => p.is_active && p.api_key)
)

const providerModels = computed(() => {
  if (!providerId.value) return []
  const p = providers.value.find(x => x.id === providerId.value)
  if (!p) return []
  try { return JSON.parse(p.models) } catch { return [] }
})

// --------------- Methods ---------------
const handleProviderChange = () => {
  model.value = ''
}

const scrollToBottom = () => {
  nextTick(() => {
    const el = messagesContainer.value
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  })
}

const handleKeydown = (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    if (!isComposing.value) handleSend()
  }
  if (e.key === 'Escape' && streaming.value) {
    e.preventDefault()
    handleStop()
  }
}

const handleSend = async () => {
  const text = inputText.value.trim()
  if (!text) return
  if (!providerId.value || !model.value) {
    ElMessage.warning('请选择供应商和模型')
    return
  }

  const now = formatTime()
  messages.value.push({ role: 'user', content: text, time: now })
  inputText.value = ''

  streaming.value = true
  streamingText.value = ''

  abortController = new AbortController()

  scrollToBottom()

  try {
    let fullContent = ''
    await streamChatMessage(
      {
        provider_id: providerId.value,
        model: model.value,
        message: text,
        system: systemPrompt.value || undefined,
        temperature: params.temperature,
        max_tokens: params.max_tokens,
        top_p: params.top_p
      },
      (chunk) => {
        fullContent += chunk
        streamingText.value = fullContent
        scrollToBottom()
      },
      abortController.signal
    )

    streamingText.value = ''
    messages.value.push({
      role: 'assistant',
      content: fullContent,
      time: formatTime()
    })
  } catch (err) {
    if (err.name === 'AbortError') {
      // User stopped — save partial content if any
      if (streamingText.value) {
        messages.value.push({
          role: 'assistant',
          content: streamingText.value + ' [已停止]',
          time: formatTime()
        })
      }
    } else {
      ElMessage.error(`发送失败: ${err.message}`)
    }
    streamingText.value = ''
  } finally {
    streaming.value = false
    abortController = null
    scrollToBottom()
  }
}

const handleStop = () => {
  if (abortController) {
    abortController.abort()
  }
}

const handleCopy = async (text) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    // Fallback for older browsers
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    ElMessage.success('已复制到剪贴板')
  }
}

const handleClear = () => {
  messages.value = []
  streamingText.value = ''
  if (abortController) {
    abortController.abort()
  }
}

const formatTime = () => {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const loadProviders = async () => {
  try {
    const data = await getModelProviders()
    providers.value = data
  } catch {
    ElMessage.error('加载供应商失败')
  }
}

// --------------- Lifecycle ---------------
onMounted(() => {
  loadProviders()
  nextTick(() => {
    inputRef.value?.focus?.()
  })
})

onUnmounted(() => {
  if (abortController) {
    abortController.abort()
  }
})
</script>

<style scoped>
/* ===== Root container ===== */
.chat-center {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-gray-50, #f8f9fb);
}

/* ===== Body layout ===== */
.chat-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* ===== Sidebar ===== */
.params-panel {
  width: 280px;
  background: var(--color-white, #fff);
  border-right: 1px solid var(--color-gray-200, #e8eaef);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}

.panel-section {
  padding: var(--space-4, 16px);
  border-bottom: 1px solid var(--color-gray-100, #f1f3f8);
}

.panel-section--grow {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-xs, 11px);
  font-weight: 700;
  color: var(--color-gray-400, #9ca3af);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 14px;
}

.section-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-chatbi, #1fb8cc);
  flex-shrink: 0;
}

.section-dot--alt {
  background: var(--color-gray-400, #9ca3af);
}

.section-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-body--fill {
  flex: 1;
  min-height: 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.field-label {
  font-size: var(--text-sm, 13px);
  font-weight: 500;
  color: var(--color-gray-500, #5c6370);
}

.field-val {
  font-size: var(--text-xs, 11px);
  font-weight: 600;
  color: var(--brand-chatbi, #1fb8cc);
  background: var(--brand-chatbi-soft, #e9f8fa);
  padding: 2px 8px;
  border-radius: 99px;
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}

.field-select {
  width: 100%;
}

/* System prompt textarea */
.system-input {
  height: 100%;
}

.system-input :deep(.el-textarea__inner) {
  height: 100% !important;
  min-height: 80px;
  resize: none;
  font-size: var(--text-sm, 13px);
  line-height: 1.6;
  border-radius: var(--radius-sm, 6px);
  border-color: var(--color-gray-200, #e8eaef);
  background: var(--color-gray-50, #f8f9fb);
  transition: border-color var(--transition-fast, 150ms ease), box-shadow var(--transition-fast, 150ms ease);
}

.system-input :deep(.el-textarea__inner):focus {
  border-color: var(--brand-chatbi, #1fb8cc);
  box-shadow: 0 0 0 3px var(--brand-chatbi-soft, #e9f8fa);
}

.system-input :deep(.el-textarea__inner)::placeholder {
  color: var(--color-gray-300, #d1d5db);
}

/* Slider overrides */
:deep(.el-slider) {
  --el-slider-main-bg-color: var(--brand-chatbi, #1fb8cc);
  --el-slider-runway-bg-color: var(--color-gray-200, #e8eaef);
  --el-slider-stop-bg-color: var(--color-white, #fff);
  --el-slider-height: 4px;
}

:deep(.el-slider__bar) {
  height: 4px;
}

:deep(.el-slider__button) {
  width: 14px;
  height: 14px;
  border: 2px solid var(--brand-chatbi, #1fb8cc);
  background: var(--color-white, #fff);
  box-shadow: var(--shadow-xs, 0 1px 2px rgba(0,0,0,0.04));
  transition: transform var(--transition-fast, 150ms ease);
}

:deep(.el-slider__button):hover {
  transform: scale(1.15);
}

/* Footer hints */
.panel-footer {
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  border-top: 1px solid var(--color-gray-100, #f1f3f8);
}

.hint-key {
  font-size: 10px;
  font-weight: 600;
  color: var(--color-gray-400, #9ca3af);
  background: var(--color-gray-100, #f1f3f8);
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--color-gray-200, #e8eaef);
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}

.hint-label {
  font-size: 11px;
  color: var(--color-gray-400, #9ca3af);
}

.hint-sep {
  font-size: 11px;
  color: var(--color-gray-300, #d1d5db);
  margin: 0 2px;
}

/* ===== Chat area ===== */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--color-white, #fff);
}

/* ===== Messages container ===== */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.messages-container::-webkit-scrollbar {
  width: 5px;
}

.messages-container::-webkit-scrollbar-track {
  background: transparent;
}

.messages-container::-webkit-scrollbar-thumb {
  background: var(--color-gray-200, #e8eaef);
  border-radius: 99px;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: var(--color-gray-300, #d1d5db);
}

/* Empty state */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-gray-300, #d1d5db);
}

.empty-icon {
  margin-bottom: 8px;
  opacity: 0.5;
}

.empty-title {
  font-size: var(--text-lg, 16px);
  font-weight: 600;
  color: var(--color-gray-400, #9ca3af);
  margin: 0;
}

.empty-desc {
  font-size: var(--text-sm, 13px);
  color: var(--color-gray-300, #d1d5db);
  margin: 0;
}

/* ===== Message item ===== */
.message-item {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  animation: msgIn 0.25s ease;
  max-width: 860px;
  width: 100%;
  align-self: center;
}

@keyframes msgIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.message-item.user {
  flex-direction: row-reverse;
}

/* Avatar */
.msg-avatar {
  flex-shrink: 0;
  margin-top: 2px;
}

.avatar-user {
  --el-avatar-bg-color: var(--brand-chatbi, #1fb8cc);
  --el-avatar-text-color: #fff;
  background: var(--brand-chatbi, #1fb8cc) !important;
  color: #fff !important;
}

.avatar-bot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-gray-100, #f1f3f8);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-gray-500, #5c6370);
  transition: background var(--transition-fast, 150ms ease), color var(--transition-fast, 150ms ease);
}

.avatar-bot.streaming {
  background: var(--brand-chatbi-soft, #e9f8fa);
  color: var(--brand-chatbi, #1fb8cc);
  animation: avatarPulse 2s ease-in-out infinite;
}

@keyframes avatarPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(79, 110, 247, 0.2); }
  50%      { box-shadow: 0 0 0 8px rgba(79, 110, 247, 0); }
}

/* Message body */
.msg-body {
  max-width: calc(100% - 56px);
  display: flex;
  flex-direction: column;
}

.msg-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  padding: 0 4px;
}

.msg-role {
  font-size: var(--text-xs, 11px);
  font-weight: 600;
  color: var(--color-gray-500, #5c6370);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.msg-time {
  font-size: 10px;
  color: var(--color-gray-400, #9ca3af);
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}

.streaming-tag {
  color: var(--brand-chatbi, #1fb8cc) !important;
  font-weight: 600 !important;
}

.msg-copy-btn {
  opacity: 0;
  transition: opacity var(--transition-fast, 150ms ease);
  margin-left: auto;
  color: var(--color-gray-400, #9ca3af);
  padding: 2px 6px;
}

.message-item:hover .msg-copy-btn {
  opacity: 1;
}

/* Message content */
.msg-content {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: var(--text-base, 14px);
  line-height: 1.7;
  word-break: break-word;
  overflow-wrap: break-word;
}

.message-item.user .msg-content {
  background: var(--brand-chatbi, #1fb8cc);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message-item.assistant .msg-content {
  background: var(--color-gray-100, #f1f3f8);
  color: var(--color-gray-900, #1a1d23);
  border-bottom-left-radius: 4px;
  border-left: 3px solid var(--brand-chatbi, #1fb8cc);
  border-top-left-radius: 4px;
}

/* ===== Markdown body ===== */
.markdown-body {
  font-size: var(--text-base, 14px);
  line-height: 1.7;
  color: inherit;
}

.markdown-body :deep(p) {
  margin: 0 0 8px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0 8px;
}

.markdown-body :deep(li) {
  margin-bottom: 2px;
}

.markdown-body :deep(strong) {
  font-weight: 700;
}

.markdown-body :deep(em) {
  font-style: italic;
}

/* Inline code */
.markdown-body :deep(code) {
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.88em;
  background: rgba(0,0,0,0.06);
  padding: 2px 5px;
  border-radius: 4px;
}

.message-item.user .markdown-body :deep(code) {
  background: rgba(255,255,255,0.2);
  color: #fff;
}

/* Code blocks */
.markdown-body :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 14px 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0 12px;
  font-size: 13px;
  line-height: 1.55;
  border: 1px solid rgba(0,0,0,0.08);
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  font-size: inherit;
  color: inherit;
}

/* Tables */
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0 12px;
  font-size: var(--text-sm, 13px);
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--color-gray-200, #e8eaef);
  padding: 6px 10px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--color-gray-50, #f8f9fb);
  font-weight: 600;
  color: var(--color-gray-500, #5c6370);
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--brand-chatbi-border, #bceaf0);
  padding: 4px 12px;
  margin: 8px 0;
  color: var(--color-gray-500, #5c6370);
  background: var(--brand-chatbi-soft, #e9f8fa);
  border-radius: 0 6px 6px 0;
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-gray-200, #e8eaef);
  margin: 12px 0;
}

.markdown-body :deep(a) {
  color: var(--brand-chatbi, #1fb8cc);
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* ===== Typing indicator ===== */
.typing-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 16px;
  margin: 8px 0;
  align-self: center;
}

.typing-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--brand-chatbi, #1fb8cc);
  animation: dotBounce 1.4s ease-in-out infinite;
}

.typing-dot:nth-child(1) { animation-delay: 0s; }
.typing-dot:nth-child(2) { animation-delay: 0.16s; }
.typing-dot:nth-child(3) { animation-delay: 0.32s; }

@keyframes dotBounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ===== Input area ===== */
.input-area {
  padding: 16px 24px 20px;
  border-top: 1px solid transparent;
  background: linear-gradient(to top, rgba(248,249,251,0.6), transparent);
}

.input-wrapper {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  align-items: flex-end;
  gap: 10px;
  background: var(--color-white, #fff);
  border: 1px solid var(--color-gray-200, #e8eaef);
  border-radius: 16px;
  padding: 10px 10px 10px 16px;
  transition: border-color var(--transition-fast, 150ms ease), box-shadow var(--transition-fast, 150ms ease);
}

.input-wrapper:focus-within {
  border-color: var(--brand-chatbi, #1fb8cc);
  box-shadow: 0 0 0 4px var(--brand-chatbi-soft, #e9f8fa);
}

.chat-input {
  flex: 1;
}

.chat-input :deep(.el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  font-size: var(--text-base, 14px);
  line-height: 1.6;
  padding: 0 !important;
  resize: none;
}

.chat-input :deep(.el-textarea__inner):focus {
  border: none !important;
  box-shadow: none !important;
}

.chat-input :deep(.el-textarea__inner)::placeholder {
  color: var(--color-gray-300, #d1d5db);
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.char-count {
  font-size: 10px;
  color: var(--color-gray-400, #9ca3af);
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
}
</style>
