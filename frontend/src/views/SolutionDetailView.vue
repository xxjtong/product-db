<template>
  <PageHeader :title="solution ? `方案: ${solution.name}` : '方案详情'">
    <button class="btn-secondary" @click="checkDeps"><ShieldCheckIcon style="width:14px;height:14px" />依赖检查</button>
    <button class="btn-secondary" @click="doCreateQuotation">生成报价单</button>
    <button class="btn-secondary" @click="showBom = !showBom">{{ showBom ? '收起' : '编辑' }} BOM 表格</button>
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
      <h3>AI 方案助手</h3>
      <div style="max-height:400px;min-height:200px;overflow-y:auto;margin-bottom:8px;padding:8px 8px 60px 8px" ref="chatLog">
        <div v-if="!chatText && !chatComponents.length" class="text-sm text-muted">
          告诉我你的需求，帮你挑选产品加入方案。例如："10个温湿度传感器 + 1个LoRaWAN网关"
        </div>
        <div style="font-size:13px;white-space:pre-wrap" v-html="chatText" />
        <!-- GenUI components from SSE -->
        <component
          v-for="(comp, i) in chatComponents"
          :key="i"
          :is="componentRegistry[comp.component]"
          v-bind="comp.props"
          @addToBom="onAddToBom"
          @compare="onCompare"
          @viewQuote="(id: number) => router.push(`/quotations/${id}`)"
        />
      </div>
      <div class="flex gap-8">
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
        <thead><tr><th>产品</th><th style="width:80px">数量</th><th style="width:100px">单价</th><th style="width:80px">折扣%</th><th style="width:100px">小计</th><th style="width:120px">备注</th><th style="width:40px"></th></tr></thead>
        <tbody>
          <tr v-for="item in solution.items" :key="item.id">
            <td><router-link :to="`/products/${item.product_id}`" class="text-sm">{{ item.product_name }}</router-link></td>
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

    <!-- Dependency check + Graph -->
    <div v-if="checkResult" class="card mb-16">
      <h3>依赖检查结果</h3>
      <div v-if="checkResult.ok" style="color:var(--color-success)">✓ 所有依赖已满足</div>
      <div v-else>
        <div v-for="w in checkResult.warnings" :key="w.description" style="color:var(--color-danger);margin-bottom:4px">
          ⚠ {{ w.type === 'missing_category' ? '缺少品类' : '缺少产品' }}: {{ w.target_name }} — {{ w.description }}
        </div>
      </div>
    </div>
    <div class="card mb-16">
      <DependencyGraph :solutionId="Number(route.params.id)" />
    </div>

    <!-- BOM Spreadsheet -->
    <div v-if="showBom" class="card mb-16">
      <h3 style="margin-bottom:8px">BOM 表格编辑器</h3>
      <BOMSpreadsheet :solutionId="Number(route.params.id)" />
    </div>
  </div>
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
import { ref, onMounted, inject, computed, nextTick, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ShieldCheckIcon, Trash2Icon, PlusIcon, InboxIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import BOMSpreadsheet from '../components/BOMSpreadsheet.vue'
import DependencyGraph from '../components/DependencyGraph.vue'
import Modal from '../components/Modal.vue'
import SolutionProductCard from '../components/GenUI/SolutionProductCard.vue'
import QuoteDraftCard from '../components/GenUI/QuoteDraftCard.vue'
import { fetchSolution, fetchProducts, addSolutionItem, updateSolutionItem, deleteSolutionItem, checkSolution, createQuotation, updateSolution, streamAiChat } from '../api'

const componentRegistry: Record<string, any> = { SolutionProductCard, QuoteDraftCard }

const route = useRoute()
const router = useRouter()
const showBom = ref(false)
const showToast = inject<(msg: string, type?: string) => void>('toast')!

const solution = ref<any>(null)
const allProducts = ref<any[]>([])
const checkResult = ref<any>(null)

// AI chat
const chatInput = ref('')
const chatText = ref('')
const chatLoading = ref(false)
const chatCid = ref<number | null>(null)
const chatLog = ref<HTMLElement | null>(null)
const chatComponents = ref<any[]>([])

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

async function load() {
  const [solRes, prodRes] = await Promise.all([
    fetchSolution(Number(route.params.id)),
    fetchProducts('per_page=500'),
  ])
  solution.value = solRes.solution
  allProducts.value = prodRes.products
}

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
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function removeItem(itemId: number) {
  try { await deleteSolutionItem(Number(route.params.id), itemId); showToast('已移除', 'success'); await load() }
  catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function checkDeps() {
  try { checkResult.value = await checkSolution(Number(route.params.id)) }
  catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function doCreateQuotation() {
  try {
    const res = await createQuotation({ solution_id: Number(route.params.id) }) as any
    showToast('报价单已生成', 'success'); router.push(`/quotations/${res.quotation.id}`)
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

// AI Chat with GenUI component support
function scrollChat() {
  nextTick(() => { if (chatLog.value) chatLog.value.scrollTop = chatLog.value.scrollHeight - 40 })
}

async function sendChat() {
  if (!chatInput.value.trim() || chatLoading.value) return
  const question = chatInput.value; chatInput.value = ''
  chatLoading.value = true
  chatText.value += `<b>你:</b> ${question}<br><br><b>AI:</b> `
  scrollChat()
  try {
    let buffer = ''
    for await (const text of streamAiChat(question, chatCid.value)) {
      if (typeof text === 'string' && text.startsWith('[CONVERSATION:')) {
        const match = text.match(/\[CONVERSATION:(\d+)\]/)
        if (match) chatCid.value = parseInt(match[1])
        continue
      }
      // Check if it's a component event (passed as special marker)
      if (typeof text === 'string' && text.startsWith('[COMPONENT:')) {
        try {
          const json = text.slice(11, -1)  // strip [COMPONENT: and trailing ]
          const comp = JSON.parse(json)
          chatComponents.value.push(comp)
        } catch { /* skip */ }
        continue
      }
      buffer += text; chatText.value += text; scrollChat()
    }
    chatText.value += '<br><br>'; scrollChat()
  } catch (e: any) {
    chatText.value += `[错误: ${e.message}]<br><br>`; scrollChat()
  }
  chatLoading.value = false
}

onMounted(load)
</script>

<style scoped>
.info-row { display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: flex-end; }
.info-row .form-group { flex: 1; min-width: 120px; margin: 0; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }
.picker-row:hover { background: var(--color-hover); }
</style>
