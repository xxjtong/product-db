<template>
  <div class="ai-chat">
    <button v-if="!open" class="ai-fab" @click="open = true; loadConvs()">
      <MessageCircleIcon style="width:22px;height:22px" />
    </button>

    <div v-if="open" class="ai-panel" :class="{ expanded: expanded }">
      <!-- Header -->
      <div class="ai-header" @mousedown="startDragHeader">
        <span>AI 产品助手</span>
        <div style="display:flex;gap:4px">
          <button v-if="convs.length && convId" class="btn-icon btn-sm" @click="convId = null; messages = []" title="新对话">+</button>
          <button class="btn-icon btn-sm" @click="toggleSize" :title="expanded ? '缩小' : '放大'">{{ expanded ? '⊡' : '⊞' }}</button>
          <button class="btn-icon btn-sm" @click="open = false">✕</button>
        </div>
      </div>

      <!-- Conversations -->
      <div v-if="!convId && convs.length" class="ai-convs">
        <div v-for="c in convs" :key="c.id" class="ai-conv-item" @click="loadConv(c.id)">
          <span>{{ c.title || '新对话' }}</span>
          <span class="text-muted text-sm">{{ c.updated_at }}</span>
          <button class="btn-icon btn-sm" @click.stop="deleteConv(c.id)">✕</button>
        </div>
      </div>

      <!-- Messages -->
      <div class="ai-messages" ref="msgContainer">
        <!-- DEBUG: show message count -->
        <div v-if="messages.length" style="font-size:10px;color:#999;padding:2px 4px;border-bottom:1px dashed #ccc;margin-bottom:4px">
          消息数:{{ messages.length }}
          <span v-for="(m,i) in messages" :key="i">[{{i}}:{{m.role}}]</span>
        </div>
        <div v-if="!convId && !convs.length" class="ai-hint">
          <p>问我任何产品问题：</p>
          <button v-for="q in sampleQuestions" :key="q" class="btn-secondary btn-sm" @click="send(q)">{{ q }}</button>
        </div>
        <template v-for="(m, i) in messages" :key="i">
          <!-- User message -->
          <div v-if="m.role === 'user'" style="float:right;clear:both;max-width:70%;margin:4px 0">
            <div v-html="m.content" style="background:#1a56db;color:#fff;border-radius:12px 12px 4px 12px;padding:8px 12px" />
          </div>
          <!-- Assistant message -->
          <div v-else class="ai-msg assistant" style="max-width:85%">
            <div class="ai-msg-text" v-html="m.content" v-if="!m.products?.length" />
            <div v-if="m.products?.length" class="ai-products">
              <div class="ai-products-header">找到 {{ m.products.length }} 个产品：</div>
              <div v-for="p in m.products" :key="p.id" class="ai-product-card" @click="router.push('/products/' + p.id)">
                <span class="ai-prod-name">{{ p.name }}</span>
                <span class="font-mono" style="font-size:11px;color:var(--color-text-secondary);margin:0 8px">{{ p.model }}</span>
                <span style="font-weight:600;font-size:13px" v-if="p.price">¥{{ p.price }}</span>
              </div>
            </div>
            <div v-if="m.tools?.length" class="ai-tool-calls">
              <span v-for="t in collapseTools(m.tools)" :key="t.name" class="tag tag-default">🔧 {{ t.name }}{{ t.count > 1 ? ' ×' + t.count : '' }}</span>
            </div>
            <div v-if="m.components?.length">
              <component v-for="(comp, ci) in m.components" :key="ci" :is="genuiRegistry[comp.component]" v-bind="comp.props" />
            </div>
            <div v-if="m.quickReplies?.length" class="ai-quick-replies">
              <button v-for="(qr, qi) in m.quickReplies" :key="qi" class="btn-secondary btn-sm" @click="quickReply(qr, m)">{{ qr }}</button>
            </div>
          </div>
        </template>
        <div v-if="loading" class="ai-msg assistant"><div class="ai-msg-text"><span class="ai-cursor">▊</span></div></div>
      </div>

      <!-- Input -->
      <div class="ai-input">
        <input ref="inputEl" v-model="input" placeholder="输入问题..." @keyup.enter="send()" :disabled="loading" />
        <button class="btn-primary btn-sm" @click="send()" :disabled="loading || !input.trim()">发送</button>
        <button class="btn-icon btn-sm" @click="open = false" title="最小化"><Minimize2Icon style="width:14px;height:14px" /></button>
      </div>

      <!-- Resize handle -->
      <div class="ai-resize" @mousedown="startResizeTL($event)"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { MessageCircleIcon, Minimize2Icon } from 'lucide-vue-next'
import SolutionProductCard from './GenUI/SolutionProductCard.vue'
import QuoteDraftCard from './GenUI/QuoteDraftCard.vue'

const genuiRegistry: Record<string, any> = { SolutionProductCard, QuoteDraftCard }

const router = useRouter()
const open = ref(false)
const inputEl = ref<HTMLInputElement | null>(null)

watch(open, (val) => {
  if (val) nextTick(() => inputEl.value?.focus())
})
const expanded = ref(false)
const input = ref('')
const loading = ref(false)
const messages = ref<any[]>([])
const convId = ref<number | null>(null)
const convs = ref<any[]>([])
const msgContainer = ref<HTMLElement | null>(null)
const sampleQuestions = [
  '找支持LoRaWAN的温湿度传感器',
  '推荐一款5G工业路由器',
  '列出所有网关产品',
]

function collapseTools(tools: string[]): { name: string; count: number }[] {
  const result: { name: string; count: number }[] = []
  for (const t of tools) {
    const last = result[result.length - 1]
    if (last && last.name === t) last.count++
    else result.push({ name: t, count: 1 })
  }
  return result
}

function toggleSize() {
  expanded.value = !expanded.value
}

function startResizeTL(e: MouseEvent) {
  e.preventDefault()
  const panel = (e.target as HTMLElement).closest('.ai-panel') as HTMLElement
  if (!panel) return
  const startX = e.clientX, startY = e.clientY
  const rect = panel.getBoundingClientRect()
  const startW = rect.width, startH = rect.height
  const startRight = window.innerWidth - rect.right
  const startBottom = window.innerHeight - rect.bottom

  function onMove(ev: MouseEvent) {
    const newW = Math.max(360, Math.min(window.innerWidth - 40, startW - (ev.clientX - startX)))
    const newH = Math.max(400, Math.min(window.innerHeight - 40, startH - (ev.clientY - startY)))
    panel.style.width = newW + 'px'
    panel.style.height = newH + 'px'
    // Keep bottom-right anchored
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// Draggable header
let dragOffset = { x: 0, y: 0 }
function startDragHeader(e: MouseEvent) {
  const panel = (e.target as HTMLElement).closest('.ai-panel')
  if (!panel) return
  const rect = panel.getBoundingClientRect()
  dragOffset = { x: e.clientX - rect.left, y: e.clientY - rect.top }
  document.addEventListener('mousemove', onDragHeader)
  document.addEventListener('mouseup', stopDragHeader)
}
function onDragHeader(e: MouseEvent) {
  const panel = document.querySelector('.ai-panel') as HTMLElement
  if (!panel) return
  panel.style.right = 'auto'
  panel.style.bottom = 'auto'
  panel.style.left = (e.clientX - dragOffset.x) + 'px'
  panel.style.top = (e.clientY - dragOffset.y) + 'px'
}
function stopDragHeader() {
  document.removeEventListener('mousemove', onDragHeader)
  document.removeEventListener('mouseup', stopDragHeader)
}

async function loadConvs() {
  try {
    const res = await fetch('/api/ai/conversations').then(r => r.json())
    convs.value = res.conversations || []
  } catch { /* ignore */ }
}

async function loadConv(id: number) {
  try {
    const res = await (await fetch(`/api/ai/conversations/${id}`)).json()
    convId.value = id
    messages.value = (res.messages || []).map((m: any) => ({
      role: m.role,
      content: formatContent(m.content, m.role),
      products: extractProducts(m.content, m.role),
    }))
    scrollDown()
  } catch { /* ignore */ }
}

async function deleteConv(id: number) {
  try {
    await fetch(`/api/ai/conversations/${id}`, { method: 'DELETE' })
    convs.value = convs.value.filter(c => c.id !== id)
    if (convId.value === id) { convId.value = null; messages.value = [] }
  } catch { /* ignore */ }
}

function extractProducts(text: string, role: string): any[] {
  if (role !== 'tool' || !text) return []
  try {
    const d = JSON.parse(text)
    if (d.products) return d.products
  } catch { /* ignore */ }
  return []
}

function formatContent(text: string, role: string): string {
  if (!text) return ''
  if (role === 'tool') {
    try {
      const d = JSON.parse(text)
      if (d.products) {
        return d.products.map((p: any) =>
          `<b>${p.name}</b> <span class="font-mono">${p.model || ''}</span> — ¥${p.price || 0}<br><span class="text-muted" style="font-size:11px">${[p.category, p.manufacturer].filter(Boolean).join(' | ')}</span>`
        ).join('<br>')
      }
      if (d.found !== undefined) return `<b>找到 ${d.found} 个产品</b>`
      if (d.categories) return d.categories.map((c: any) => c.name).join('、')
      return `<pre style="font-size:11px;margin:0">${JSON.stringify(d, null, 2)}</pre>`
    } catch { /* ignore */ }
  }
  return mdToHtml(text)
}

function mdToHtml(text: string): string {
  // Escape HTML entities before markdown conversion to prevent XSS
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    // Headings
    .replace(/^#### (.+)$/gm, '<h5>$1</h5>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
    // Italic
    .replace(/\*(.+?)\*/g, '<i>$1</i>')
    // Horizontal rule
    .replace(/^---$/gm, '<hr>')
    // Numbered lists: wrap lines starting with "1. " in proper tags
    .replace(/^(\d+)[.、]\s+(.+)$/gm, '<div class="ai-li"><span class="ai-li-num">$1.</span> $2</div>')
    // Bullet lists
    .replace(/^[-−]\s+(.+)$/gm, '<div class="ai-li">• $1</div>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // URLs
    .replace(/(https?:\/\/[^\s<>]+)/g, '<a href="$1" target="_blank">$1</a>')
    // Newlines to <br>
    .replace(/\n/g, '<br>')

  // Group consecutions ai-li into a list block
  html = html.replace(/(<div class="ai-li">.*?<\/div>(<br>)?)+/g, '<div class="ai-list">$&</div>')
  // Clean up double <div> wrapping
  html = html.replace(/<div class="ai-list">(<br>)?<div class="ai-list">/g, '<div class="ai-list">')
  html = html.replace(/<\/div><\/div>/g, '</div>')

  // Simple table: | a | b | -> inline styled table
  if (html.includes('|') && html.includes('---')) {
    html = html.replace(/(\|[^\n]+\|\n\|[-:\|\s]+\|\n((?:\|[^\n]+\|\n?)+))/g, (match) => {
      const lines = match.trim().split('\n').filter(l => !l.includes('---'))
      if (lines.length < 2) return match
      const rows = lines.map(line =>
        '<tr>' + line.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('') + '</tr>'
      ).join('')
      return `<table class="ai-table">${rows}</table>`
    })
  }

  return html
}

function parseToolProducts(resultStr: string): any[] {
  try {
    const d = JSON.parse(resultStr)
    return d.products || []
  } catch { return [] }
}

async function send(question?: string) {
  const q = question || input.value.trim()
  if (!q || loading.value) return
  input.value = ''

  messages.value.push({ role: 'user', content: q })
  loading.value = true
  scrollDown()

  try {
    const reader = (await fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: q, conversation_id: convId.value }),
    })).body!.getReader()

    const decoder = new TextDecoder()
    let buffer = ''
    let currentText = ''
    let currentTools: string[] = []
    let currentProducts: any[] = []
    let currentComponents: any[] = []
    let currentQuickReplies: string[] = []
    let lastToolResult = ''

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
          const event = JSON.parse(data)
          if (event.conversation_id && !convId.value) {
            convId.value = event.conversation_id
            loadConvs()
          }
          if (event.event === 'products' && event.data) {
            currentProducts = event.data
          } else if (event.event === 'component') {
            currentComponents.push(event)
          } else if (event.event === 'quick_replies') {
            currentQuickReplies = event.items || []
          } else if (event.event === 'tool') {
            currentTools.push(event.text || '')
          } else if (event.event === 'text') {
            currentText += event.text || ''
          } else if (event.event === 'first_token') {
            if (currentTools.length) {
              messages.value.push({ role: 'assistant', content: '正在查询...', tools: [...currentTools] })
            }
          } else if (event.event === 'done') {
            const idx = messages.value.length - 1
            const content = formatContent(currentText || '查询完成', 'assistant')
            const tools = [...currentTools]
            const products = [...currentProducts]
            const components = [...currentComponents]
            const quickReplies = [...currentQuickReplies]
            if (idx >= 0 && messages.value[idx].role === 'assistant') {
              messages.value[idx] = { role: 'assistant', content, tools, products, components, quickReplies }
            } else {
              messages.value.push({ role: 'assistant', content, tools, products, components, quickReplies })
            }
            currentText = ''
            currentTools = []
            currentProducts = []
            currentComponents = []
            currentQuickReplies = []
          } else if (event.event === 'error') {
            messages.value.push({ role: 'assistant', content: `错误: ${event.text}` })
          }
        } catch { /* skip */ }
      }
    }
  } catch (e: any) {
    messages.value.push({ role: 'assistant', content: `请求失败: ${e.message}` })
  }
  loading.value = false
  scrollDown()
  nextTick(() => inputEl.value?.focus())
}

function scrollDown() {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight + 40
    }
  })
}

function quickReply(reply: string, msg: any) {
  if (reply === '对比产品' && msg.products?.length >= 2) {
    const ids = msg.products.map((p: any) => p.id).join(',')
    router.push(`/products/compare?product_ids=${ids}`)
  } else if (reply === '全部加入方案') {
    // Notify parent if on solution page
    input.value = '全部加入方案'
    send()
  } else {
    input.value = reply
    send()
  }
}
</script>

<style scoped>
.ai-chat { position: fixed; bottom: 20px; right: 20px; z-index: 2000; }
.ai-fab {
  width: 48px; height: 48px; border-radius: 50%;
  background: var(--color-accent); color: #fff;
  border: none; cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,0,0,.2);
  display: flex; align-items: center; justify-content: center; padding: 0;
}
.ai-fab:hover { transform: scale(1.05); }
.ai-panel {
  background: #fff; border-radius: var(--radius-lg);
  box-shadow: 0 8px 30px rgba(0,0,0,.15);
  display: flex; flex-direction: column;
  position: fixed; bottom: 20px; right: 20px;
  width: 640px; height: 640px;
  min-width: 360px; min-height: 400px;
  max-width: 90vw; max-height: calc(100vh - 40px);
  overflow: hidden;
  resize: both;
}
.ai-panel.expanded {
  width: 960px;
  height: calc(100vh - 40px);
}
.ai-header {
  padding: 10px 14px; background: var(--color-accent); color: #fff;
  font-weight: 600; font-size: 14px;
  display: flex; justify-content: space-between; align-items: center;
  cursor: move; user-select: none;
}
.ai-messages { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; align-items: flex-start; gap: 6px; min-height: 300px; max-height: 60vh; }
.ai-hint { text-align: center; color: var(--color-text-secondary); padding: 16px; }
.ai-hint button { margin: 4px; }
.ai-convs { padding: 8px; max-height: 160px; overflow-y: auto; }
.ai-conv-item {
  padding: 6px 10px; cursor: pointer; border-bottom: 1px solid var(--color-border);
  display: flex; justify-content: space-between; align-items: center; font-size: 12px;
}
.ai-conv-item:hover { background: var(--color-hover); }
.ai-msg { max-width: 80%; font-size: 13px; }
.ai-msg.user { width: fit-content; margin-left: auto !important; margin-right: 0 !important; text-align: right; }
.ai-msg.user .ai-msg-text { display: inline-block !important; background: var(--color-accent) !important; color: #fff !important; border-radius: 12px 12px 4px 12px !important; }
.ai-msg.assistant { margin-left: 0 !important; margin-right: auto !important; }
.ai-msg.assistant .ai-msg-text { background: #e8edf2 !important; border-radius: 12px 12px 12px 4px !important; }
.ai-msg-text { padding: 8px 10px; line-height: 1.5; word-break: break-word; }
.ai-msg.assistant .ai-products,
.ai-msg.assistant .ai-tool-calls,
.ai-msg.assistant .ai-quick-replies,
.ai-msg.assistant .genui-card,
.ai-msg.assistant .quote-card { max-width: 100%; }
.ai-products { margin-top: 4px; display: flex; flex-direction: column; gap: 4px; }
.ai-products-header { font-size: 11px; color: var(--color-text-secondary); margin-bottom: 2px; }
.ai-product-card {
  background: #fff; border: 1px solid var(--color-border); border-radius: 6px;
  padding: 5px 8px; cursor: pointer; transition: all .15s;
  display: flex; align-items: center;
}
.ai-product-card:hover { border-color: var(--color-accent); box-shadow: var(--shadow-sm); }
.ai-prod-name { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-tool-calls { font-size: 11px; padding: 2px 8px; }
.ai-cursor { animation: blink 1s infinite; } @keyframes blink { 50% { opacity: 0; } }
.ai-quick-replies { display: flex; gap: 6px; margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--color-border); flex-wrap: wrap; }
.ai-quick-replies button { font-size: 12px; }
.ai-msg-text h3 { font-size: 14px; margin: 8px 0 4px; }
.ai-msg-text h4 { font-size: 13px; margin: 6px 0 2px; }
.ai-msg-text h5 { font-size: 12px; margin: 4px 0 2px; }
.ai-msg-text hr { border: none; border-top: 1px solid var(--color-border); margin: 8px 0; }
.ai-list { margin: 4px 0; }
.ai-li { font-size: 13px; line-height: 1.6; padding: 1px 0; }
.ai-li-num { color: var(--color-accent); font-weight: 600; margin-right: 4px; }
.ai-table { width: 100%; border-collapse: collapse; font-size: 11px; margin: 4px 0; }
.ai-table td { padding: 2px 6px; border: 1px solid var(--color-border); }
code { background: var(--color-hover); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.ai-input { padding: 8px 10px; border-top: 1px solid var(--color-border); display: flex; gap: 6px; }
.ai-input input { flex: 1; font-size: 13px; padding: 6px 8px; }
.ai-resize {
  position: absolute; top: 0; left: 0;
  width: 20px; height: 20px;
  cursor: nwse-resize;
}
.ai-resize::after {
  content: '';
  position: absolute; top: 4px; left: 4px;
  width: 10px; height: 10px;
  border-left: 2px solid var(--color-text-secondary);
  border-top: 2px solid var(--color-text-secondary);
  opacity: .3;
}
</style>