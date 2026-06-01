<template>
  <PageHeader title="产品对比">
    <button class="btn-secondary" @click="$router.push('/products')">返回列表</button>
    <button v-if="productList.length >= 2" class="btn-secondary" @click="clearAll">清除全部</button>
  </PageHeader>

  <!-- Product selector -->
  <div class="card" style="margin-bottom:16px;padding:12px 16px">
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <span style="font-weight:600;white-space:nowrap">对比产品 ({{ productList.length }}/6):</span>
      <span v-for="p in productList" :key="p.id" class="filter-tag active" style="cursor:default">
        {{ p.name }}
        <button @click="removeProduct(p.id)" style="margin-left:4px;cursor:pointer;background:none;border:none;font-size:14px">&times;</button>
      </span>
      <SearchInput v-if="productList.length < 6" v-model="searchText" placeholder="添加产品..." style="width:200px" @input="onSearch" />
    </div>
    <div v-if="searchResults.length" class="card" style="position:absolute;z-index:10;margin-top:4px;max-height:200px;overflow-y:auto;padding:0">
      <div v-for="r in searchResults" :key="r.id" style="padding:6px 12px;cursor:pointer;border-bottom:1px solid var(--color-border);font-size:13px" @click="addProduct(r)">
        {{ r.name }} <span class="text-muted">{{ r.model || '' }}</span> <span class="text-muted">— {{ r.category_name }}</span>
      </div>
    </div>
  </div>

  <div v-if="!productList.length" class="card" style="text-align:center;padding:48px;color:var(--color-text-secondary)">
    <p>请从产品列表选择产品进行对比</p>
    <router-link to="/products">返回产品列表</router-link>
  </div>

  <!-- Comparison Matrix -->
  <div class="card" v-else-if="matrix" style="overflow-x:auto">
    <div style="margin-bottom:12px;color:var(--color-text-secondary);font-size:12px">
      共 {{ specKeys.length }} 项差异参数（仅显示值不同的参数）
    </div>
    <table class="data-table" style="min-width:600px">
      <thead>
        <tr>
          <th style="width:150px;min-width:100px">参数</th>
          <th v-for="p in productList" :key="p.id" style="min-width:120px">
            {{ p.name }}<br><span class="text-muted text-sm">{{ p.model || p.sku || '' }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="key in specKeys" :key="key">
          <td style="font-weight:500">{{ displayNames[key] || key }}</td>
          <td v-for="p in productList" :key="p.id" :class="{ 'cell-highlight': isHighlight(key, p.id) }">
            {{ formatVal(matrix[key]?.[p.id]) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-else-if="productList.length === 1" class="card" style="text-align:center;padding:48px;color:var(--color-text-secondary)">
    <p>请至少选择 2 个产品进行对比</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import SearchInput from '../components/SearchInput.vue'
import { compareProducts, fetchProducts } from '../api'

const route = useRoute()
const router = useRouter()
const loaded = ref(false)
const matrix = ref<Record<string, Record<number, any>> | null>(null)
const products = ref<Record<number, any>>({})
const displayNames = ref<Record<string, string>>({})
const searchText = ref('')
const searchResults = ref<any[]>([])
let searchTimer: any = null

const productList = computed(() => Object.values(products.value))
const specKeys = computed(() => matrix.value ? Object.keys(matrix.value) : [])

function formatVal(val: any): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'boolean') return val ? '✓' : '—'
  if (typeof val === 'number') {
    return val === 0 ? '—' : String(val)
  }
  if (Array.isArray(val)) return val.join(', ')
  return String(val)
}

function isHighlight(key: string, _productId: number): boolean {
  // Highlight numeric values where this product has the max
  if (!matrix.value) return false
  const values = matrix.value[key] || {}
  const nums: [number, number][] = []
  for (const [pid, val] of Object.entries(values)) {
    const n = Number(val)
    if (!isNaN(n) && n > 0) nums.push([Number(pid), n])
  }
  if (nums.length < 2) return false
  // Don't highlight for dimensions/weight where smaller isn't better
  return false
}

async function onSearch() {
  const q = searchText.value.trim()
  if (!q) { searchResults.value = []; return }
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    try {
      const res = await fetchProducts(`search=${encodeURIComponent(q)}&per_page=10`)
      const existing = new Set(Object.keys(products.value).map(Number))
      searchResults.value = (res.products || []).filter((p: any) => !existing.has(p.id))
    } catch { searchResults.value = [] }
  }, 300)
}

function addProduct(p: any) {
  products.value = { ...products.value, [p.id]: p }
  searchResults.value = []
  searchText.value = ''
  updateUrl()
}

function removeProduct(id: number) {
  const newProducts = { ...products.value }
  delete newProducts[id]
  products.value = newProducts
  if (Object.keys(newProducts).length < 2) matrix.value = null
  updateUrl()
}

function clearAll() {
  products.value = {}
  matrix.value = null
  router.replace('/products/compare')
}

function updateUrl() {
  const ids = Object.keys(products.value).join(',')
  if (ids) router.replace({ query: { ids } })
}

async function loadCompare(ids: number[]) {
  if (ids.length < 2) {
    // Load single products
    for (const id of ids) {
      try {
        const res = await (await fetch(`/api/products/${id}`)).json()
        products.value = { ...products.value, [id]: res.product }
      } catch {}
    }
    loaded.value = true
    return
  }
  try {
    const res = await compareProducts(ids.join(','))
    matrix.value = res.matrix
    products.value = { ...products.value, ...res.products }
    displayNames.value = res.display_names || {}
  } catch {}
  loaded.value = true
}

watch(() => route.query.ids, (newIds) => {
  if (newIds) {
    const ids = String(newIds).split(',').map(Number).filter(n => !isNaN(n))
    if (ids.length) {
      products.value = {}
      matrix.value = null
      loadCompare(ids)
    }
  }
})

onMounted(async () => {
  const ids = (route.query.ids as string || '').split(',').map(Number).filter(n => !isNaN(n))
  if (ids.length) await loadCompare(ids)
  loaded.value = true
})
</script>

<style scoped>
.cell-highlight {
  background: #fef3c7 !important;
  font-weight: 600;
}
.row-selected {
  background: var(--color-surface);
}
</style>