<template>
  <div class="agent-view">
    <!-- Header -->
    <div class="agent-header">
      <div class="agent-header-left">
        <BotIcon :size="20" />
        <span class="agent-title">Hermes Agent</span>
        <span class="agent-subtitle">AI 开发 & 产品方案助手</span>
      </div>
      <div class="agent-header-actions">
        <button class="btn-secondary btn-sm" @click="newChat" :disabled="!messages.length && !chats.length">
          <PlusIcon :size="14" /> 新对话
        </button>
        <button v-if="chats.length" class="btn-secondary btn-sm" @click="showHistory = !showHistory">
          <HistoryIcon :size="14" /> 历史
        </button>
      </div>
    </div>

    <div class="agent-body">
      <!-- Chat history sidebar -->
      <div v-if="showHistory" class="agent-history">
        <div v-for="(c, i) in chats" :key="c.id" class="agent-history-item" @click="loadChat(c.id)">
          <div class="agent-history-title">{{ c.title }}</div>
          <div class="agent-history-time">{{ formatTime(c.updatedAt) }}</div>
          <button class="btn-icon btn-sm" @click.stop="deleteChat(c.id)">✕</button>
        </div>
        <div v-if="!chats.length" class="text-muted text-sm" style="padding:16px;text-align:center">暂无历史对话</div>
      </div>

      <!-- Messages -->
      <div class="agent-messages" ref="msgContainer">
        <div v-if="!messages.length" class="agent-welcome">
          <BotIcon :size="56" stroke-width="1" style="color:var(--color-accent);margin-bottom:16px" />
          <h2>Hermes Agent</h2>
          <p>全能 AI 助手 — 搜索产品、设计方案、分析数据、辅助开发</p>
          <div class="agent-suggestions">
            <button v-for="q in suggestions" :key="q" class="btn-secondary" @click="send(q)">{{ q }}</button>
          </div>
        </div>

        <div v-for="(m, i) in messages" :key="i" :class="['agent-msg', m.role]">
          <div v-if="m.role === 'assistant'" class="agent-msg-avatar">
            <BotIcon :size="18" />
          </div>
          <div class="agent-msg-body">
            <div v-if="m.role === 'user'" class="agent-msg-text user-text">{{ m.content }}</div>
            <div v-else class="agent-msg-text" v-html="renderMd(m.content)" />
            <div v-if="m.role === 'assistant' && m.tokens" class="agent-msg-meta">
              {{ m.tokens }}
            </div>
          </div>
        </div>

        <div v-if="streaming" class="agent-msg assistant">
          <div class="agent-msg-avatar streaming"><BotIcon :size="18" /></div>
          <div class="agent-msg-body">
            <div class="agent-msg-text" v-html="streamText ? renderMd(streamText) : '<span class=&quot;ai-cursor&quot;>▊</span>'" />
          </div>
        </div>
      </div>
    </div>

    <!-- Input -->
    <div class="agent-input-bar">
      <textarea
        ref="inputEl"
        v-model="input"
        placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
        @keydown.enter.exact.prevent="send()"
        :disabled="streaming"
        rows="1"
      />
      <button
        v-if="streaming"
        class="btn-danger btn-sm"
        @click="stopStreaming"
      >停止</button>
      <button
        v-else
        class="btn-primary"
        @click="send()"
        :disabled="!input.trim()"
      >发送</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, watch } from 'vue'
import { BotIcon, PlusIcon, HistoryIcon } from 'lucide-vue-next'
import DOMPurify from 'dompurify'

// ── Types ──────────────────────────────────────────────
interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  tokens?: string
}

interface ChatMeta {
  id: string
  title: string
  updatedAt: number
}

// ── Constants ──────────────────────────────────────────
const HERMES_BASE = '/product-db/hermes'

const SYSTEM_PROMPT = `You are Hermes, an AI assistant integrated into the product-db (产品数据库) system — an IoT product selection, comparison, specification sheet generation, and solution design platform.

## System Context
- **Stack**: FastAPI backend + Vue 3 frontend + SQLite database
- **Scale**: 414 products, 27 categories, 48 manufacturers, 60 suppliers
- **Product categories**: sensors, gateways, nodes, security, tools, actuators, cellular devices, etc.
- **Key attributes**: communication methods (LoRaWAN, WiFi, 4G, 5G, Ethernet, BLE, Zigbee), protocols (MQTT, HTTP, ModbusRTU, BACnet), power (DC 12V, DC 24V, PoE, Battery, AC)
- **Features**: product comparison matrix, spec sheet generation (HTML/PDF), solution BOM editor, quotation generation, AI-powered product search

## Your Capabilities
1. **Product search & recommendation** — help find IoT products by category, specs, price range, communication method, brand
2. **Solution design** — help assemble multi-product solutions with dependency analysis
3. **Technical analysis** — compare products, explain specs, recommend alternatives
4. **Development assistance** — this is a Vue 3 + FastAPI project, you can help with code questions, architecture, debugging

## Guidelines
- Be specific about products: mention category, communication method, key specs
- When comparing products, use a structured format
- If asked about project code/structure, reference the actual tech stack
- Be concise and actionable
- Use Chinese when the user writes in Chinese, English when they write in English

You are helpful, technically knowledgeable, and focused on delivering value for IoT product engineering workflows.`

const suggestions = [
  '推荐一款支持LoRaWAN的温湿度传感器',
  '列出所有5G工业路由器',
  '设计一套智慧农业环境监测方案',
  '帮我理解 product-db 的项目结构',
  '对比 WiFi vs LoRaWAN 网关的优缺点',
]

// ── State ──────────────────────────────────────────────
const input = ref('')
const inputEl = ref<HTMLTextAreaElement | null>(null)
const msgContainer = ref<HTMLElement | null>(null)
const messages = ref<Message[]>([])
const streamText = ref('')
const streaming = ref(false)
const showHistory = ref(false)

const chats = ref<ChatMeta[]>([])
const activeChatId = ref<string | null>(null)
let abortCtrl: AbortController | null = null

// ── localStorage persistence ───────────────────────────
const STORAGE_PREFIX = 'agent_'

function saveMessages() {
  if (!activeChatId.value) return
  localStorage.setItem(
    STORAGE_PREFIX + 'msgs_' + activeChatId.value,
    JSON.stringify(messages.value)
  )
}

function loadMessages(id: string): Message[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_PREFIX + 'msgs_' + id) || '[]')
  } catch { return [] }
}

function saveChats() {
  localStorage.setItem(STORAGE_PREFIX + 'chats', JSON.stringify(chats.value))
}

function loadChats(): ChatMeta[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_PREFIX + 'chats') || '[]')
  } catch { return [] }
}

// ── Chat management ────────────────────────────────────
function newChat() {
  activeChatId.value = null
  messages.value = []
  streamText.value = ''
  showHistory.value = false
  nextTick(() => inputEl.value?.focus())
}

function loadChat(id: string) {
  activeChatId.value = id
  messages.value = loadMessages(id)
  streamText.value = ''
  showHistory.value = false
  scrollDown()
}

function deleteChat(id: string) {
  localStorage.removeItem(STORAGE_PREFIX + 'msgs_' + id)
  chats.value = chats.value.filter(c => c.id !== id)
  saveChats()
  if (activeChatId.value === id) {
    newChat()
  }
}

function ensureChat(title: string) {
  if (activeChatId.value) return
  activeChatId.value = 'c_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
  chats.value.unshift({ id: activeChatId.value, title, updatedAt: Date.now() })
  saveChats()
}

function bumpChat() {
  if (!activeChatId.value) return
  const c = chats.value.find(c => c.id === activeChatId.value)
  if (c) {
    c.updatedAt = Date.now()
    // Move to top
    chats.value = chats.value.filter(x => x.id !== c!.id)
    chats.value.unshift(c)
    saveChats()
  }
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// ── Markdown rendering ─────────────────────────────────
// Pre-compiled regex for markdown (avoid backtick-in-regex TS parsing issues)
const RE_CODE_BLOCK = /```(\w*)\n([\s\S]*?)```/g
const RE_INLINE_CODE = /`([^`]+)`/g
const RE_BOLD = /\*\*(.+?)\*\*/g
const RE_ITALIC = /\*(.+?)\*/g
const RE_H5 = /^#### (.+)$/gm
const RE_H4 = /^### (.+)$/gm
const RE_H3 = /^## (.+)$/gm
const RE_H2 = /^# (.+)$/gm
const RE_HR = /^---$/gm
const RE_NUM_LIST = /^(\d+)[.、]\s+(.+)$/gm
const RE_BULLET = /^[-•]\s+(.+)$/gm
const RE_BLOCKQUOTE = /^&gt;\s?(.+)$/gm
const RE_URL = /(https?:\/\/[^\s<>]+)/g
const RE_NL = /\n/g
const RE_MD_LIST = /(<div class="md-li">.*?<\/div>(<br>)?)+/g

function renderTable(html: string): string {
  // Find table blocks: consecutive lines that start/end with |
  return html.replace(/((?:\|.+\|\n?)+)/g, (block) => {
    const lines = block.trim().split('\n')
    if (lines.length < 2) return block
    // Filter out separator lines like |---|---|
    const rows = lines.filter(l => !/^\|[-:\s|]+\|$/.test(l))
    if (rows.length < 2) return block
    const isHeader = /^\|[-:\s|]+\|$/.test(lines[1])
    const tbody = rows.slice(isHeader ? 1 : 0).map(row => {
      const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('')
      return `<tr>${cells}</tr>`
    }).join('')
    const thead = isHeader ? '<thead><tr>' + rows[0].split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('') + '</tr></thead>' : ''
    return `<table class="md-table">${thead}<tbody>${tbody}</tbody></table>`
  })
}

function renderMd(text: string): string {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(RE_CODE_BLOCK, '<pre><code>$2</code></pre>')
    .replace(RE_INLINE_CODE, '<code>$1</code>')
    .replace(RE_BOLD, '<b>$1</b>')
    .replace(RE_ITALIC, '<i>$1</i>')
    .replace(RE_H5, '<h5>$1</h5>')
    .replace(RE_H4, '<h4>$1</h4>')
    .replace(RE_H3, '<h3>$1</h3>')
    .replace(RE_H2, '<h2>$1</h2>')
    .replace(RE_HR, '<hr>')
    .replace(RE_NUM_LIST, '<div class="md-li">$1. $2</div>')
    .replace(RE_BULLET, '<div class="md-li">• $1</div>')
    .replace(RE_BLOCKQUOTE, '<blockquote>$1</blockquote>')
    .replace(RE_URL, '<a href="$1" target="_blank">$1</a>')

  html = renderTable(html)  // before newline→<br> so table rows stay intact
  html = html.replace(RE_NL, '<br>')

  html = html.replace(RE_MD_LIST, '<div class="md-list">$&</div>')
  return DOMPurify.sanitize(html) as string
}

// ── SSE Streaming ──────────────────────────────────────
async function send(question?: string) {
  const q = question || input.value.trim()
  if (!q || streaming.value) return
  input.value = ''

  // Ensure chat exists
  ensureChat(q.slice(0, 30))

  // Add user message
  messages.value.push({ role: 'user', content: q })
  saveMessages()
  scrollDown()

  // Build conversation for API
  const apiMessages: { role: string; content: string }[] = [
    { role: 'system', content: SYSTEM_PROMPT },
    ...messages.value.map(m => ({ role: m.role, content: m.content })),
  ]

  streamText.value = ''
  streaming.value = true
  abortCtrl = new AbortController()
  let fullContent = ''
  let tokenUsage = { prompt: 0, completion: 0, total: 0 }

  try {
    const resp = await fetch(HERMES_BASE + '/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'hermes-agent',
        messages: apiMessages,
        stream: true,
      }),
      signal: abortCtrl.signal,
    })

    if (!resp.ok) {
      const err = await resp.text()
      throw new Error(`${resp.status}: ${err}`)
    }

    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6).trim()
        if (data === '[DONE]') continue
        try {
          const chunk = JSON.parse(data)
          const delta = chunk.choices?.[0]?.delta?.content
          if (delta) {
            fullContent += delta
            streamText.value = fullContent
            scrollDown()
          }
          // Capture token usage from final chunk
          if (chunk.usage) {
            tokenUsage.prompt = chunk.usage.prompt_tokens || 0
            tokenUsage.completion = chunk.usage.completion_tokens || 0
            tokenUsage.total = chunk.usage.total_tokens || 0
          }
        } catch { /* skip malformed SSE */ }
      }
    }
  } catch (e: any) {
    if (e.name === 'AbortError') {
      // User stopped — save partial content
      if (fullContent) {
        messages.value.push({ role: 'assistant', content: fullContent + '\n\n*[已停止]*' })
      }
    } else {
      messages.value.push({
        role: 'assistant',
        content: `**请求失败**: ${e.message || '请检查 Hermes 服务是否运行'}`,
      })
    }
    saveMessages()
    streamText.value = ''
    streaming.value = false
    scrollDown()
    return
  }

  // Add assistant message (with token count)
  if (fullContent) {
    const tk = tokenUsage.total
    messages.value.push({
      role: 'assistant',
      content: fullContent,
      tokens: tk ? `${tk.toLocaleString()} tokens (入 ${tokenUsage.prompt.toLocaleString()} + 出 ${tokenUsage.completion.toLocaleString()})` : undefined,
    })
  }
  streamText.value = ''
  streaming.value = false
  saveMessages()
  bumpChat()
  scrollDown()
  nextTick(() => inputEl.value?.focus())
}

function stopStreaming() {
  abortCtrl?.abort()
}

// ── Helpers ────────────────────────────────────────────
function scrollDown() {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    }
  })
}

// ── Lifecycle ──────────────────────────────────────────
onMounted(() => {
  chats.value = loadChats()
})

watch(streaming, (val) => {
  if (!val) nextTick(() => inputEl.value?.focus())
})
</script>

<style scoped>
.agent-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  background: var(--color-bg);
}

/* Header */
.agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-card);
  flex-shrink: 0;
}
.agent-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-accent);
}
.agent-title {
  font-weight: 700;
  font-size: 15px;
  color: var(--color-text);
}
.agent-subtitle {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.agent-header-actions {
  display: flex;
  gap: 6px;
}

/* Body */
.agent-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

/* History sidebar */
.agent-history {
  width: 260px;
  border-right: 1px solid var(--color-border);
  overflow-y: auto;
  background: var(--color-card);
  flex-shrink: 0;
}
.agent-history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background .12s;
}
.agent-history-item:hover {
  background: var(--color-hover);
}
.agent-history-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-history-time {
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

/* Messages */
.agent-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Welcome */
.agent-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}
.agent-welcome h2 {
  margin: 0 0 6px;
  font-size: 22px;
  color: var(--color-text);
}
.agent-welcome p {
  margin: 0 0 24px;
  color: var(--color-text-secondary);
  font-size: 14px;
}
.agent-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 600px;
}

/* Message */
.agent-msg {
  display: flex;
  gap: 12px;
  max-width: 85%;
}
.agent-msg.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.agent-msg-avatar {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: var(--color-accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: box-shadow .3s;
}
.agent-msg-avatar.streaming {
  animation: agent-pulse 1.6s ease-in-out infinite;
}
@keyframes agent-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(59,130,246,.4); }
  50% { box-shadow: 0 0 0 8px rgba(59,130,246,0); }
}
.agent-msg-body {
  min-width: 0;
}
.agent-msg-text {
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13.5px;
  line-height: 1.65;
  word-break: break-word;
}
.agent-msg.assistant .agent-msg-text {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-top-left-radius: 2px;
}
.agent-msg.user .agent-msg-text {
  background: var(--color-accent);
  color: #fff;
  border-top-right-radius: 2px;
}
.agent-msg-meta {
  font-size: 11px;
  color: var(--color-text-secondary);
  padding: 2px 14px 0;
}

/* Markdown content */
.agent-msg-text :deep(h2) { font-size: 16px; margin: 10px 0 4px; }
.agent-msg-text :deep(h3) { font-size: 14px; margin: 8px 0 4px; }
.agent-msg-text :deep(h4) { font-size: 13px; margin: 6px 0 2px; }
.agent-msg-text :deep(h5) { font-size: 12px; margin: 4px 0 2px; }
.agent-msg-text :deep(p) { margin: 4px 0; }
.agent-msg-text :deep(hr) { border: none; border-top: 1px solid var(--color-border); margin: 10px 0; }
.agent-msg-text :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 12.5px;
  line-height: 1.5;
  margin: 8px 0;
}
.agent-msg-text :deep(code) {
  font-family: 'SF Mono', 'Menlo', 'Monaco', monospace;
  font-size: 12px;
}
.agent-msg-text :deep(code:not(pre code)) {
  background: var(--color-hover);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
}
.agent-msg-text :deep(blockquote) {
  border-left: 3px solid var(--color-accent);
  padding-left: 12px;
  margin: 6px 0;
  color: var(--color-text-secondary);
}
.agent-msg-text :deep(a) {
  color: var(--color-accent);
  text-decoration: underline;
}
.agent-msg-text :deep(ul), .agent-msg-text :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}
.agent-msg-text :deep(li) {
  margin: 2px 0;
}
.md-list {
  margin: 4px 0;
}
.md-li {
  font-size: 13.5px;
  line-height: 1.6;
  padding: 1px 0;
}
/* Table */
.agent-msg-text :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin: 6px 0;
}
.agent-msg-text :deep(td), .agent-msg-text :deep(th) {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
}
.agent-msg-text :deep(th) {
  background: var(--color-hover);
  font-weight: 600;
}

/* Cursor blink */
.ai-cursor {
  animation: cursor-blink 1s infinite;
  color: var(--color-accent);
}
@keyframes cursor-blink {
  50% { opacity: 0; }
}

/* Input bar */
.agent-input-bar {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--color-border);
  background: var(--color-card);
  flex-shrink: 0;
}
.agent-input-bar textarea {
  flex: 1;
  resize: none;
  font-size: 13.5px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-bg);
  color: var(--color-text);
  line-height: 1.4;
  min-height: 22px;
  max-height: 150px;
  font-family: inherit;
}
.agent-input-bar textarea:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px var(--color-accent-light, rgba(59,130,246,.15));
}
.agent-input-bar textarea::placeholder {
  color: var(--color-text-secondary);
}

@media (max-width: 640px) {
  .agent-msg { max-width: 95%; }
  .agent-messages { padding: 12px; }
  .agent-header { padding: 8px 12px; }
  .agent-input-bar { padding: 8px 12px; }
  .agent-subtitle { display: none; }
}
</style>
