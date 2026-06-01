<template>
  <PageHeader :title="solution ? `方案: ${solution.name}` : '方案详情'">
    <button class="btn-secondary" @click="checkDeps"><ShieldCheckIcon style="width:14px;height:14px" />依赖检查</button>
    <button class="btn-secondary" @click="$router.back()">返回</button>
  </PageHeader>

  <div v-if="solution" class="card mb-16">
    <div class="form-grid" style="margin-bottom:16px">
      <div><span class="text-muted text-sm">客户</span><br>{{ solution.client_name || '—' }}</div>
      <div><span class="text-muted text-sm">项目</span><br>{{ solution.project_name || '—' }}</div>
      <div><span class="text-muted text-sm">状态</span><br>{{ solution.status }}</div>
      <div><span class="text-muted text-sm">总价</span><br class="font-mono">{{ solution.total_price }}</div>
    </div>

    <!-- Add product -->
    <div class="flex gap-8 items-center mb-16">
      <select v-model="addProductId" style="flex:1"><option :value="null">选择产品添加...</option><option v-for="p in allProducts" :key="p.id" :value="p.id">{{ p.name }} (¥{{ p.base_price }})</option></select>
      <input v-model.number="addQty" type="number" min="1" style="width:80px" placeholder="数量" />
      <button class="btn-primary btn-sm" @click="addItem" :disabled="!addProductId">添加</button>
    </div>

    <!-- Items table -->
    <table class="data-table" v-if="solution.items.length">
      <thead><tr><th>产品</th><th>数量</th><th>单价</th><th>折扣(%)</th><th>小计</th><th>备注</th><th></th></tr></thead>
      <tbody>
        <tr v-for="item in solution.items" :key="item.id">
          <td>{{ item.product_name }}</td>
          <td><input v-model.number="item.quantity" type="number" min="1" style="width:70px" @change="updateItem(item)" /></td>
          <td class="font-mono">{{ item.unit_price }}</td>
          <td><input v-model.number="item.discount_rate" type="number" style="width:70px" @change="updateItem(item)" /></td>
          <td class="font-mono">{{ (item.quantity * item.unit_price * (item.discount_rate / 100)).toFixed(2) }}</td>
          <td><input v-model="item.remark" style="width:120px" @change="updateItem(item)" /></td>
          <td><button class="btn-icon btn-sm" @click="removeItem(item.id)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state" style="padding:24px"><p>暂无产品</p></div>

    <!-- Actions -->
    <div class="flex gap-8 mt-16">
      <button class="btn-primary" @click="createQuotation">生成报价单</button>
      <button class="btn-secondary" @click="showBom = !showBom">{{ showBom ? '收起' : '编辑' }} BOM 表格</button>
    </div>
  </div>

  <!-- BOM Spreadsheet -->
  <div v-if="showBom" class="card mb-16">
    <h3 style="margin-bottom:8px">BOM 表格</h3>
    <BOMSpreadsheet :solutionId="Number(route.params.id)" />
  </div>

  <!-- Dependency check results -->
  <div v-if="checkResult" class="card mb-16">
    <h3 style="margin-bottom:8px">依赖检查</h3>
    <div v-if="checkResult.ok" style="color:var(--color-success)">✓ 所有依赖已满足</div>
    <div v-else>
      <div v-for="w in checkResult.warnings" :key="w.description" style="color:var(--color-danger);margin-bottom:4px">
        ⚠ {{ w.type === 'missing_category' ? '缺少品类' : '缺少产品' }}: {{ w.target_name }} — {{ w.description }}
      </div>
    </div>
  </div>

  <!-- Dependency Graph -->
  <div class="card mb-16">
    <DependencyGraph :solutionId="Number(route.params.id)" />
  </div>

  <!-- AI Chat -->
  <div class="card">
    <h3 style="margin-bottom:12px">AI 助手</h3>
    <div style="max-height:300px;overflow-y:auto;margin-bottom:12px;padding:12px;background:#f8f9fa;border-radius:var(--radius-sm);font-size:13px;white-space:pre-wrap" ref="chatLog">{{ chatText || '问AI关于此方案的问题...' }}</div>
    <div class="flex gap-8">
      <input v-model="chatInput" style="flex:1" placeholder="输入问题..." @keyup.enter="sendChat" />
      <button class="btn-primary btn-sm" @click="sendChat" :disabled="chatLoading">发送</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ShieldCheckIcon, Trash2Icon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import BOMSpreadsheet from '../components/BOMSpreadsheet.vue'
import DependencyGraph from '../components/DependencyGraph.vue'
import { fetchSolution, fetchProducts, addSolutionItem, updateSolutionItem, deleteSolutionItem, checkSolution, createQuotation, bomExportUrl, streamAiChat } from '../api'

const route = useRoute()
const router = useRouter()
const showBom = ref(false)
const showToast = inject<(msg: string, type?: string) => void>('toast')!

const solution = ref<any>(null)
const allProducts = ref<any[]>([])
const addProductId = ref<number | null>(null)
const addQty = ref(1)
const checkResult = ref<any>(null)

const chatInput = ref('')
const chatText = ref('')
const chatLoading = ref(false)
const chatCid = ref<number | null>(null)
const chatLog = ref<HTMLElement | null>(null)

async function load() {
  const [solRes, prodRes] = await Promise.all([
    fetchSolution(Number(route.params.id)),
    fetchProducts('per_page=200'),
  ])
  solution.value = solRes.solution
  allProducts.value = prodRes.products
}

async function addItem() {
  if (!addProductId.value) return
  try {
    await addSolutionItem(Number(route.params.id), {
      product_id: addProductId.value,
      quantity: addQty.value,
    })
    showToast('已添加', 'success')
    addProductId.value = null
    addQty.value = 1
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

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
  try {
    await deleteSolutionItem(Number(route.params.id), itemId)
    showToast('已移除', 'success')
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function checkDeps() {
  try {
    checkResult.value = await checkSolution(Number(route.params.id))
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function doCreateQuotation() {
  try {
    const res = await createQuotation({ solution_id: Number(route.params.id) }) as any
    showToast('报价单已生成', 'success')
    router.push(`/quotations/${res.quotation.id}`)
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function sendChat() {
  if (!chatInput.value.trim() || chatLoading.value) return
  const question = chatInput.value
  chatInput.value = ''
  chatLoading.value = true
  chatText.value += `你: ${question}\n\nAI: `
  try {
    for await (const text of streamAiChat(question, chatCid.value)) {
      if (typeof text === 'string' && text.startsWith('[CONVERSATION:')) {
        const match = text.match(/\[CONVERSATION:(\d+)\]/)
        if (match) chatCid.value = parseInt(match[1])
        continue
      }
      chatText.value += text
    }
    chatText.value += '\n\n'
  } catch (e: any) {
    chatText.value += `\n[错误: ${e.message}]\n\n`
  }
  chatLoading.value = false
}

onMounted(load)
</script>
