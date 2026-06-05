<template>
  <PageHeader :title="solution ? `方案: ${solution.name}` : '方案详情'" :breadcrumb="[{ label: '方案管理', to: '/solutions' }, { label: solution?.name || '方案详情', to: '' }]">
    <button class="btn-secondary" @click="doCreateQuotation">生成报价单</button>
    <button class="btn-secondary" @click="$router.back()">返回</button>
  </PageHeader>

  <div v-if="solution">
    <!-- 1. Client info row -->
    <div class="card mb-16">
      <h3>客户信息</h3>
      <div class="info-row">
        <div class="form-group"><label>客户</label><input v-model="solution.client_name" @change="saveInfo" /></div>
        <div class="form-group"><label>项目</label><input v-model="solution.project_name" @change="saveInfo" /></div>
        <div class="form-group"><label>状态</label>
          <select v-model="solution.status" @change="saveInfo">
            <option value="draft">草稿</option><option value="active">进行中</option><option value="done">完成</option>
          </select>
        </div>
        <div class="form-group"><label>总价</label><span class="font-mono" style="font-size:18px;font-weight:700">¥{{ solution.total_price || 0 }}</span></div>
        <div class="form-group" style="flex:2"><label>备注</label><input v-model="solution.notes" @change="saveInfo" /></div>
      </div>
    </div>

    <!-- 2. AI assistant row (full width below client info) -->
    <div class="card mb-16">
      <div class="flex items-center gap-8" style="margin-bottom:8px">
        <h3 style="margin:0">AI 方案助手</h3>
        <button v-if="!chatCid && !showConvs" class="btn-secondary btn-sm" @click="loadConvs">历史</button>
        <button v-if="chatCid || showConvs" class="btn-secondary btn-sm" @click="newChat">+ 新对话</button>
      </div>
      <div v-if="showConvs && convs.length" style="max-height:160px;overflow-y:auto;margin-bottom:8px">
        <div v-for="c in convs" :key="c.id" class="ai-conv-item" @click="loadConv(c.id)" style="padding:6px 8px;cursor:pointer;border-bottom:1px solid var(--color-border);font-size:12px;display:flex;justify-content:space-between">
          <span>{{ c.title || '新对话' }}</span><span class="text-muted text-sm">{{ c.updated_at }}</span>
        </div>
      </div>
      <!-- Chat messages — bubble style -->
      <div class="sol-chat-log" ref="chatLog">
        <div v-if="chatMessages.length === 0" class="text-sm text-muted" style="text-align:center;padding:24px 0">
          告诉我你的需求，帮你挑选产品加入方案。例如："10个温湿度传感器 + 1个LoRaWAN网关"
        </div>
        <div v-for="(m, i) in chatMessages" :key="i" :class="['sol-chat-msg', m.role]">
          <div class="sol-chat-bubble" v-if="m.content" v-html="sanitize(m.content)" />
          <div v-if="m.products?.length" class="sol-chat-products">
            <div v-for="p in m.products" :key="p.id" class="sol-chat-prod" @click="router.push('/products/'+p.id)">
              <span class="sol-chat-prod-name">{{ p.name }}</span>
              <span class="font-mono" style="font-size:11px;color:var(--color-text-secondary);margin:0 8px">{{ p.model }}</span>
              <span style="font-weight:600;font-size:13px" v-if="p.price">¥{{ p.price }}</span>
              <button class="btn-primary btn-sm" style="margin-left:auto;padding:2px 8px;font-size:11px" @click.stop="onAddToBom([{id:p.id, qty:1}])">加入方案</button>
            </div>
          </div>
          <div v-if="m.components?.length">
            <component v-for="(comp, ci) in m.components" :key="ci" :is="componentRegistry[comp.component]" v-bind="comp.props" @addToBom="onAddToBom" @compare="onCompare" @viewQuote="(id: number) => router.push(`/quotations/${id}`)" />
          </div>
        </div>
        <div v-if="chatLoading" class="sol-chat-msg assistant"><div class="sol-chat-bubble"><span class="ai-cursor">▊</span></div></div>
      </div>
      <div class="flex gap-8" style="border-top:1px solid var(--color-border);padding-top:8px">
        <input v-model="chatInput" style="flex:1" placeholder="如: 10个温湿度传感器 + LoRaWAN网关" @keyup.enter="sendChat" />
        <button class="btn-primary btn-sm" @click="sendChat" :disabled="chatLoading">{{ chatLoading ? '...' : '发送' }}</button>
      </div>
    </div>

    <!-- 3. BOM Items -->
    <div class="card mb-16">
      <div class="flex gap-8 items-center mb-12">
        <h3 style="margin:0">产品清单 ({{ solution.items?.length || 0 }} 项)</h3>
        <button class="btn-primary btn-sm" @click="pickerOpen = true"><PlusIcon style="width:14px;height:14px" />批量选品</button>
      </div>

      <table class="data-table" v-if="solution.items?.length">
        <thead><tr><th>产品</th><th>型号</th><th style="width:140px">功能描述</th><th style="width:80px">数量</th><th style="width:100px">单价</th><th style="width:80px">折扣%</th><th style="width:100px">小计</th><th style="width:120px">备注</th><th style="width:40px"></th></tr></thead>
        <tbody>
          <tr v-for="item in solution.items" :key="item.id">
            <td><router-link :to="`/products/${item.product_id}`" class="text-sm">{{ item.product_name }}</router-link></td>
            <td class="font-mono text-sm text-muted">{{ item.product_model || '—' }}</td>
            <td class="text-sm text-muted" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="item.product_description">{{ item.product_description || '—' }}</td>
            <td><input v-model.number="item.quantity" type="number" min="1" style="width:60px" @change="updateItem(item)" /></td>
            <td class="font-mono text-sm">{{ item.unit_price }}</td>
            <td><input v-model.number="item.discount_rate" type="number" style="width:60px" @change="updateItem(item)" /></td>
            <td class="font-mono text-sm">¥{{ (item.quantity * item.unit_price * (item.discount_rate / 100)).toFixed(0) }}</td>
            <td><input v-model="item.remark" style="width:100px" @change="updateItem(item)" /></td>
            <td><button class="btn-icon btn-sm" @click="removeItem(item.id)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state" style="padding:24px"><InboxIcon /><p>暂无产品，使用上方 AI 助手或批量选品添加</p></div>
    </div>

    <!-- BOM Spreadsheet -->


  </div>
  <div v-else-if="loadError" class="empty-state"><p style="color:var(--color-danger)">{{ loadError }}</p><button class="btn-secondary btn-sm" style="margin-top:8px" @click="load">重试</button></div>
  <div v-else class="empty-state"><p>加载中...</p></div>

  <!-- Batch product picker modal -->
  <Modal title="批量选品" :visible="pickerOpen" @close="pickerOpen = false">
    <div class="flex gap-8 mb-12">
      <input v-model="pickerSearch" style="flex:1" placeholder="搜索产品..." />
      <span class="text-sm text-muted">已选 {{ pickerSelected.length }} / 6</span>
    </div>
    <div style="max-height:400px;overflow-y:auto">
      <div v-for="p in pickerFiltered" :key="p.id" class="picker-row flex items-center gap-8" style="padding:6px 0;border-bottom:1px solid var(--color-border)">
        <input type="checkbox" :checked="pickerSelected.includes(p.id)" @change="togglePick(p.id)" />
        <span style="flex:1;font-size:13px">{{ p.name }} <span class="text-muted text-sm">{{ p.model }}</span></span>
        <span class="font-mono text-sm" v-if="p.base_price">¥{{ p.base_price }}</span>
        <span class="text-sm text-muted">{{ p.category_name }}</span>
      </div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="pickerOpen = false">取消</button>
      <button class="btn-primary" @click="batchAdd" :disabled="!pickerSelected.length">添加选中 ({{ pickerSelected.length }})</button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, onMounted, inject, computed, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Trash2Icon, PlusIcon, InboxIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'

import Modal from '../components/Modal.vue'
import SolutionProductCard from '../components/GenUI/SolutionProductCard.vue'
import QuoteDraftCard from '../components/GenUI/QuoteDraftCard.vue'
import { fetchSolution, fetchProducts, addSolutionItem, updateSolutionItem, deleteSolutionItem, createQuotation, updateSolution, streamAiChat, fetchConversations, fetchConversation } from '../api'
import type { Solution, Product } from '../types'
import DOMPurify from 'dompurify'
import { escapeHtml, extractProducts, formatAiContent, stripToolCalls } from '../utils/markdown'

function sanitize(html: string): string { return DOMPurify.sanitize(html) as string }

const componentRegistry: Record<string, any> = { SolutionProductCard, QuoteDraftCard }

const route = useRoute()
const router = useRouter()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const solution = ref<Solution | null>(null)
const allProducts = ref<Product[]>([])

// AI chat
interface ChatMessage {
  role: 'user' | 'assistant' | 'tool'
  content: string
  products: any[]
  components: any[]
}
const chatInput = ref('')
const chatMessages = ref<ChatMessage[]>([])
const chatLoading = ref(false)
const chatCid = ref<number | null>(null)
const showConvs = ref(false)
const convs = ref<any[]>([])
const chatLog = ref<HTMLElement | null>(null)

// Product picker
const pickerOpen = ref(false)
const pickerSearch = ref('')
const pickerSelected = ref<number[]>([])

const pickerFiltered = computed(() => {
  if (!pickerSearch.value) return allProducts.value.slice(0, 100)
  const s = pickerSearch.value.toLowerCase()
  return allProducts.value.filter((p: any) =>
    p.name.toLowerCase().includes(s) || p.model?.toLowerCase().includes(s) || p.category_name?.includes(s)
  ).slice(0, 100)
})

const loading = ref(false)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const solRes = await fetchSolution(Number(route.params.id))
    solution.value = solRes.solution
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  }
  loading.value = false
}

async function loadPickerProducts() {
  if (allProducts.value.length) return
  try {
    const prodRes = await fetchProducts('per_page=500')
    allProducts.value = prodRes.products
  } catch { /* picker is non-critical */ }
}

watch(pickerOpen, (val) => { if (val) loadPickerProducts() })

async function saveInfo() {
  if (!solution.value) return
  try {
    await updateSolution(solution.value.id, {
      client_name: solution.value.client_name, project_name: solution.value.project_name,
      status: solution.value.status, notes: solution.value.notes,
    })
  } catch { /* ignore */ }
}

// Batch add
function togglePick(id: number) {
  const idx = pickerSelected.value.indexOf(id)
  if (idx >= 0) pickerSelected.value.splice(idx, 1)
  else if (pickerSelected.value.length < 6) pickerSelected.value.push(id)
}

async function batchAdd() {
  for (const id of pickerSelected.value) {
    try { await addSolutionItem(Number(route.params.id), { product_id: id, quantity: 1 }) } catch { /* skip */ }
  }
  showToast(`已添加 ${pickerSelected.value.length} 个产品`, 'success')
  pickerOpen.value = false; pickerSelected.value = []; await load()
}

// GenUI events from AI
async function onAddToBom(items: { id: number; qty: number }[]) {
  for (const item of items) {
    try { await addSolutionItem(Number(route.params.id), { product_id: item.id, quantity: item.qty || 1 }) } catch { /* skip */ }
  }
  showToast(`已添加 ${items.length} 个产品`, 'success')
  await load()
}

function onCompare(ids: number[]) {
  if (ids.length >= 2) router.push(`/products/compare?product_ids=${ids.join(',')}`)
}

// Item CRUD
async function updateItem(item: any) {
  try {
    await updateSolutionItem(Number(route.params.id), item.id, {
      quantity: item.quantity, unit_price: item.unit_price,
      discount_rate: item.discount_rate, remark: item.remark,
    })
    // Update amount locally
    item.amount = (item.quantity || 0) * (item.unit_price || 0) * ((item.discount_rate || 100) / 100)
    if (solution.value) {
      solution.value.total_price = solution.value.items.reduce((s: number, i: any) => s + (i.amount || 0), 0)
    }
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function removeItem(itemId: number) {
  try {
    await deleteSolutionItem(Number(route.params.id), itemId)
    if (solution.value) {
      solution.value.items = solution.value.items.filter((i: any) => i.id !== itemId)
      solution.value.total_price = solution.value.items.reduce((s: number, i: any) => s + (i.amount || 0), 0)
    }
    showToast('已移除', 'success')
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function doCreateQuotation() {
  try {
    const res = await createQuotation({ solution_id: Number(route.params.id) }) as any
    showToast('报价单已生成', 'success'); router.push(`/quotations/${res.quotation.id}`)
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

// AI Chat with GenUI component support
function scrollChat() {
  nextTick(() => { if (chatLog.value) chatLog.value.scrollTop = chatLog.value.scrollHeight })
}

async function loadConvs() {
  try {
    const res = await fetchConversations()
    convs.value = res.conversations || []
    showConvs.value = true
  } catch { /* ignore */ }
}
async function loadConv(id: number) {
  try {
    const res = await fetchConversation(id)
    chatCid.value = id; showConvs.value = false
    const msgs = res.conversation?.messages || []
    chatMessages.value = []
    for (const m of msgs) {
      if (m.role === 'user' || m.role === 'assistant') {
        const products = extractProducts(m.content, m.role)
        chatMessages.value.push({
          role: m.role,
          content: m.role === 'user' ? escapeHtml(m.content || '') : formatContent(m.content || '', m.role),
          products,
          components: [],
        })
      }
    }
    nextTick(scrollChat)
  } catch { /* ignore */ }
}
function newChat() { chatCid.value = null; chatMessages.value = []; showConvs.value = false }

async function sendChat() {
  if (!chatInput.value.trim() || chatLoading.value) return
  const question = chatInput.value; chatInput.value = ''
  chatLoading.value = true

  // Add user message bubble
  chatMessages.value.push({ role: 'user', content: escapeHtml(question), products: [], components: [] })
  scrollChat()

  let curContent = ''
  let curProducts: any[] = []
  let curComponents: any[] = []
  try {
    for await (const text of streamAiChat(question, chatCid.value)) {
      if (typeof text === 'string' && text.startsWith('[CONVERSATION:')) {
        const match = text.match(/\[CONVERSATION:(\d+)\]/)
        if (match) chatCid.value = parseInt(match[1])
        continue
      }
      if (typeof text === 'string' && text.startsWith('[TOOL:')) {
        const toolText = text.slice(6, -1)  // strip [TOOL:...]
        chatMessages.value.push({ role: 'tool', content: toolText, products: [], components: [] })
        scrollChat()
        continue
      }
      if (typeof text === 'string' && text.startsWith('[PRODUCTS:')) {
        try { curProducts = JSON.parse(text.slice(10)) } catch { /* skip */ }
        continue
      }
      if (typeof text === 'string' && text.startsWith('[COMPONENT:')) {
        try {
          const json = text.slice(11, -1)
          curComponents.push(JSON.parse(json))
        } catch { /* skip */ }
        continue
      }
      curContent += text
      // Update or create assistant bubble as text streams in
      const last = chatMessages.value[chatMessages.value.length - 1]
      if (last && last.role === 'assistant') {
        last.content = formatContent(curContent, 'assistant')
        last.products = curProducts
        last.components = curComponents
      } else {
        chatMessages.value.push({ role: 'assistant', content: formatContent(curContent, 'assistant'), products: curProducts, components: curComponents })
      }
      scrollChat()
    }
    // Finalize assistant message
    const last = chatMessages.value[chatMessages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content = formatContent(curContent, 'assistant')
      last.products = curProducts
      last.components = curComponents
    } else if (curContent || curProducts.length || curComponents.length) {
      chatMessages.value.push({ role: 'assistant', content: formatContent(curContent || '查询完成', 'assistant'), products: curProducts, components: curComponents })
    }
  } catch (e: any) {
    chatMessages.value.push({ role: 'assistant', content: `错误: ${escapeHtml(e.message)}`, products: [], components: [] })
  }
  chatLoading.value = false
  scrollChat()
}

function formatContent(text: string, role: string): string {
  return sanitize(formatAiContent(text, role))
}

onMounted(load)
</script>

<style scoped>
.info-row { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: flex-end; }
.info-row .form-group { flex: 1; min-width: 120px; margin: 0; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
.picker-row:hover { background: var(--color-hover); }

/* --- Chat bubbles --- */
.sol-chat-log {
  max-height: 500px; min-height: 100px; overflow-y: auto;
  padding: 12px; display: flex; flex-direction: column; gap: 8px;
}
.sol-chat-msg { max-width: 88%; font-size: 13px; }
.sol-chat-msg.user { align-self: flex-end; }
.sol-chat-msg.user .sol-chat-bubble {
  background: var(--color-accent); color: #fff;
  border-radius: 12px 12px 0 12px;
}
.sol-chat-msg.assistant { align-self: flex-start; }
.sol-chat-msg.assistant .sol-chat-bubble {
  background: var(--color-hover);
  border-radius: 12px 12px 12px 0;
}
.sol-chat-msg.tool {
  align-self: flex-start; font-size: 11px; color: var(--color-text-secondary);
  padding: 2px 8px; background: var(--color-hover); border-radius: 10px;
}
.sol-chat-msg.tool .sol-chat-bubble { padding: 2px 4px; }
.sol-chat-bubble {
  padding: 8px 10px; line-height: 1.5; word-break: break-word;
}
.sol-chat-products {
  margin-top: 6px; display: flex; flex-direction: column; gap: 4px;
}
.sol-chat-prod {
  background: #fff; border: 1px solid var(--color-border); border-radius: 6px;
  padding: 5px 8px; cursor: pointer; transition: all .15s;
  display: flex; align-items: center; font-size: 13px;
}
.sol-chat-prod:hover { border-color: var(--color-accent); box-shadow: var(--shadow-sm); }
.sol-chat-prod-name { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-cursor { animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0; } }
.sol-chat-bubble b { font-weight: 600; }
.sol-chat-bubble code { background: rgba(0,0,0,.06); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
</style>
