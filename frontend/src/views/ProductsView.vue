<template>
  <PageHeader title="产品列表">
    <SearchInput v-model="search" placeholder="搜索型号/名称..." autofocus />
    <button v-if="selectedIds.length >= 2" class="btn-primary" style="background:var(--color-accent)" @click="$router.push(`/products/compare?ids=${selectedIds.join(',')}`)">
      对比选中 ({{ selectedIds.length }})
    </button>
    <button v-if="selectedIds.length" class="btn-danger" @click="confirmBatchDelete">
      <Trash2Icon style="width:14px;height:14px" />删除选中 ({{ selectedIds.length }})
    </button>
    <button v-if="selectedIds.length" class="btn-secondary" @click="selectedIds = []">取消选择</button>
    <button class="btn-secondary" @click="openExport">
      <DownloadIcon style="width:14px;height:14px" />导出
    </button>
    <button class="btn-secondary" @click="$router.push('/products/import')">导入</button>
    <button class="btn-primary" @click="$router.push('/products/new')">
      <PlusIcon style="width:16px;height:16px" />新增
    </button>
  </PageHeader>

  <!-- Filter panel -->
  <div class="card" style="margin-bottom:16px;padding:12px 16px">
    <div class="filter-panel">
      <!-- 品类 — inline tags with header -->
      <!-- 品类 — inline flow -->
      <div class="filter-group" v-if="categoryTree.length" :style="{ maxHeight: filterOpen.category ? 'none' : '30px', overflow: 'hidden', lineHeight: '2.2', verticalAlign: 'middle', marginBottom: '0' }">
        <span class="filter-label" @click="filterOpen.category = !filterOpen.category" style="cursor:pointer">品类</span>
        <span class="filter-toggle" @click="filterOpen.category = !filterOpen.category" style="cursor:pointer;margin:0 8px 0 4px">{{ filterOpen.category ? '▲' : '▼' }}</span>
        <span v-for="p in categoryTree" :key="p.id" :class="['filter-tag', { active: filters.category_id === p.id }]" @click="toggleCategory(p.id)" style="margin:2px 3px;display:inline-block;white-space:nowrap;line-height:normal">{{ p.name }}</span>
        <template v-for="p in categoryTree" :key="'sub-'+p.id">
          <div v-if="filters.category_id === p.id && p.children?.length" style="display:block;width:100%;margin-top:2px">
            <span v-for="c in p.children" :key="c.id" :class="['filter-tag sub', { active: filters.sub_category_id === c.id }]" @click="toggleSubCategory(c.id)" style="margin:2px 3px;display:inline-block;white-space:nowrap;line-height:normal">{{ c.name }}</span>
          </div>
        </template>
      </div>
      <!-- 厂商 — toggleable with CSS collapse -->
      <div class="filter-group" v-if="manufacturers.length > 1" :style="{ maxHeight: filterOpen.manufacturer ? 'none' : '30px', overflow: 'hidden', lineHeight: '2.2', verticalAlign: 'middle', marginBottom: '0' }">
        <span class="filter-label" @click="filterOpen.manufacturer = !filterOpen.manufacturer" style="cursor:pointer">厂商</span>
        <span class="filter-toggle" @click="filterOpen.manufacturer = !filterOpen.manufacturer" style="cursor:pointer;margin:0 8px 0 4px">{{ filterOpen.manufacturer ? '▲' : '▼' }}</span>
        <span v-for="m in manufacturers" :key="m.id" :class="['filter-tag', { active: filters.manufacturer_id === m.id }]" @click="toggleFilter('manufacturer_id', m.id)" style="margin:2px 3px;display:inline-block;white-space:nowrap;line-height:normal">{{ m.name }}</span>
      </div>
      <!-- 通讯/协议/供电 — shared row -->
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <div class="filter-group" style="flex:1;min-width:180px;margin-bottom:0" :style="{ maxHeight: filterOpen.comm_method ? 'none' : '30px', overflow: 'hidden' }">
          <span class="filter-label" @click="filterOpen.comm_method = !filterOpen.comm_method" style="cursor:pointer">通讯方式</span>
          <span class="filter-toggle" @click="filterOpen.comm_method = !filterOpen.comm_method" style="cursor:pointer;margin:0 8px 0 4px">{{ filterOpen.comm_method ? '▲' : '▼' }}</span>
          <span v-for="m in commMethods" :key="m.id" :class="['filter-tag', { active: filters.comm_method === m.id }]" @click="toggleFilter('comm_method', m.id)" style="margin:2px 3px;display:inline-block;white-space:nowrap;line-height:normal">{{ m.name }}</span>
        </div>
        <div class="filter-group" style="flex:1;min-width:180px;margin-bottom:0" :style="{ maxHeight: filterOpen.comm_protocol ? 'none' : '30px', overflow: 'hidden' }">
          <span class="filter-label" @click="filterOpen.comm_protocol = !filterOpen.comm_protocol" style="cursor:pointer">协议</span>
          <span class="filter-toggle" @click="filterOpen.comm_protocol = !filterOpen.comm_protocol" style="cursor:pointer;margin:0 8px 0 4px">{{ filterOpen.comm_protocol ? '▲' : '▼' }}</span>
          <span v-for="p in commProtocols" :key="p.id" :class="['filter-tag', { active: filters.comm_protocol === p.id }]" @click="toggleFilter('comm_protocol', p.id)" style="margin:2px 3px;display:inline-block;white-space:nowrap;line-height:normal">{{ p.name }}</span>
        </div>
        <div class="filter-group" style="flex:1;min-width:180px;margin-bottom:0" :style="{ maxHeight: filterOpen.power_supply ? 'none' : '30px', overflow: 'hidden' }">
          <span class="filter-label" @click="filterOpen.power_supply = !filterOpen.power_supply" style="cursor:pointer">供电</span>
          <span class="filter-toggle" @click="filterOpen.power_supply = !filterOpen.power_supply" style="cursor:pointer;margin:0 8px 0 4px">{{ filterOpen.power_supply ? '▲' : '▼' }}</span>
          <span v-for="p in powerSupplies" :key="p.id" :class="['filter-tag', { active: filters.power_supply === p.id }]" @click="toggleFilter('power_supply', p.id)" style="margin:2px 3px;display:inline-block;white-space:nowrap;line-height:normal">{{ p.name }}</span>
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <div v-if="loading" class="empty-state"><p>加载中...</p></div>
    <div v-else-if="loadError" class="empty-state"><p style="color:var(--color-danger)">{{ loadError }}</p><button class="btn-secondary btn-sm" style="margin-top:8px" @click="loadProducts()">重试</button></div>
    <table v-else-if="products.length" class="data-table">
      <thead>
        <tr>
          <th style="width:32px"><input type="checkbox" :checked="selectedIds.length === products.length" @change="toggleAll($event)" title="全选" /></th>
          <th>名称</th><th>型号</th><th>厂商</th><th>品类</th><th>通讯</th><th>供电</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in products" :key="p.id" :class="{ 'row-selected': selectedIds.includes(p.id) }" @click.self="toggleSelect(p.id)">
          <td>
            <input type="checkbox" :checked="selectedIds.includes(p.id)" @click.stop @change="toggleSelect(p.id)" />
          </td>
          <td>
            <div class="flex items-center gap-8">
              <img v-if="p.image_url" :src="p.image_url" style="width:32px;height:32px;object-fit:cover;border-radius:4px;border:1px solid var(--color-border)" />
              <router-link :to="`/products/${p.id}`">{{ p.name }}</router-link>
            </div>
          </td>
          <td class="font-mono text-sm">{{ p.model || p.sku || '—' }}</td>
          <td>{{ p.manufacturer_name || '—' }}</td>
          <td>
            <template v-if="p.all_category_names?.length">
              <TagBadge v-for="cn in p.all_category_names.slice(0,3)" :key="cn" :label="cn" />
              <span v-if="p.all_category_names.length > 3" class="text-sm text-muted">+{{ p.all_category_names.length - 3 }}</span>
            </template>
            <TagBadge v-else :label="p.category_name" />
          </td>
          <td>
            <TagBadge v-for="cm in p.comm_methods.slice(0,3)" :key="cm.method_id" :label="cm.method_name" />
            <span v-if="p.comm_methods.length > 3" class="text-sm text-muted">+{{ p.comm_methods.length - 3 }}</span>
          </td>
          <td>
            <TagBadge v-for="ps in p.power_supplies.slice(0,3)" :key="ps.power_id" :label="ps.power_name" />
            <span v-if="p.power_supplies.length > 3" class="text-sm text-muted">+{{ p.power_supplies.length - 3 }}</span>
          </td>
          <td>
            <button class="btn-icon btn-sm" title="编辑" @click="$router.push(`/products/${p.id}/edit`)"><PencilIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" title="删除" @click="confirmDelete(p)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state"><InboxIcon /><p>暂无产品</p></div>
    <Pagination :total="total" :page="page" :per-page="perPage" @change="p => { page = p; loadProducts() }" @update:per-page="s => { perPage = s; page = 1; loadProducts() }" />
  </div>

  <ConfirmDialog title="删除产品" :message="`确定删除「${deleteTarget?.name}」？`" :visible="!!deleteTarget" @confirm="doDelete" @cancel="deleteTarget = null" />
  <ConfirmDialog title="批量删除" :message="`确定删除 ${selectedIds.length} 个产品？`" :visible="showBatchConfirm" @confirm="doBatchDelete" @cancel="showBatchConfirm = false" />
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, inject } from 'vue'
import { PlusIcon, PencilIcon, Trash2Icon, InboxIcon, DownloadIcon } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import SearchInput from '../components/SearchInput.vue'
import TagBadge from '../components/TagBadge.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { fetchProducts, deleteProduct, exportProducts, fetchCommMethods, fetchCommProtocols, fetchPowerSupplies, fetchManufacturers, fetchCategoryTree } from '../api'
import type { Product, Manufacturer } from '../types'

const route = useRoute()
const router = useRouter()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const products = ref<Product[]>([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const MAX_PER_PAGE = 100
const search = ref('')
const deleteTarget = ref<Product | null>(null)
const showBatchConfirm = ref(false)
const filterExpanded = ref(true)
const filterOpen = reactive({
  category: false,
  manufacturer: false,
  comm_method: false,
  comm_protocol: false,
  power_supply: false,
})
const selectedIds = ref<number[]>([])

function toggleSelect(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else if (selectedIds.value.length < 6) selectedIds.value.push(id)
}

function openExport() { window.location.href = exportUrl }

function toggleAll(e: Event) {
  const checked = (e.target as HTMLInputElement).checked
  selectedIds.value = checked ? products.value.map((p: any) => p.id).slice(0, 6) : []
}

interface DictItem { id: number; name: string }

const commMethods = ref<DictItem[]>([])
const commProtocols = ref<DictItem[]>([])
const powerSupplies = ref<DictItem[]>([])
const manufacturers = ref<Manufacturer[]>([])
const categoryTree = ref<any[]>([])
const flatCategories = ref<any[]>([])

const exportUrl = exportProducts()

const filters = reactive<Record<string, any>>({
  category_id: null,
  sub_category_id: null,
  comm_method: null,
  comm_protocol: null,
  power_supply: null,
  manufacturer_id: null,
})

function flattenTree(nodes: any[], result: any[] = []) {
  for (const n of nodes) {
    result.push(n)
    if (n.children?.length) flattenTree(n.children, result)
  }
  return result
}

function toggleCategory(id: number) {
  filters.category_id = filters.category_id === id ? null : id
  filters.sub_category_id = null
  // Auto-expand filter if parent has children (to show sub-categories)
  if (filters.category_id) {
    const parent = categoryTree.value.find((c: any) => c.id === id)
    if (parent?.children?.length) filterOpen.category = true
  }
  page.value = 1
  loadProducts()
}

function toggleSubCategory(id: number) {
  filters.sub_category_id = filters.sub_category_id === id ? null : id
  page.value = 1
  loadProducts()
}

function toggleFilter(key: string, value: any) {
  filters[key] = filters[key] === value ? null : value
  page.value = 1
  loadProducts()
}

function buildParams(): string {
  const parts: string[] = []
  if (search.value) parts.push(`search=${encodeURIComponent(search.value)}`)
  if (filters.sub_category_id) parts.push(`category_id=${filters.sub_category_id}`)
  else if (filters.category_id) parts.push(`category_id=${filters.category_id}`)
  if (filters.comm_method) parts.push(`comm_method=${filters.comm_method}`)
  if (filters.comm_protocol) parts.push(`comm_protocol=${filters.comm_protocol}`)
  if (filters.power_supply) parts.push(`power_supply=${filters.power_supply}`)
  if (filters.manufacturer_id) parts.push(`manufacturer_id=${filters.manufacturer_id}`)
  parts.push(`page=${page.value}`)
  parts.push(`per_page=${perPage.value === 0 ? total.value : Math.min(perPage.value, MAX_PER_PAGE)}`)
  return parts.join('&')
}

const loading = ref(false)
const loadError = ref('')

async function loadProducts() {
  loading.value = true
  loadError.value = ''
  // Sync filters to URL so back button preserves state
  const q: Record<string, string> = {}
  if (search.value) q.search = search.value
  if (filters.category_id) q.category_id = String(filters.category_id)
  if (filters.manufacturer_id) q.manufacturer_id = String(filters.manufacturer_id)
  if (filters.comm_method) q.comm_method = String(filters.comm_method)
  if (filters.comm_protocol) q.comm_protocol = String(filters.comm_protocol)
  if (filters.power_supply) q.power_supply = String(filters.power_supply)
  if (page.value > 1) q.page = String(page.value)
  router.replace({ path: route.path, query: Object.keys(q).length ? q : {} })
  try {
    const res = await fetchProducts(buildParams())
    products.value = res.products
    total.value = res.total
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
    products.value = []
    total.value = 0
  }
  loading.value = false
}

function confirmDelete(p: any) { deleteTarget.value = p }

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await deleteProduct(deleteTarget.value.id)
    deleteTarget.value = null
    await loadProducts()
  } catch (e: any) {
    showToast('操作失败: ' + (e.detail || e.message || '未知错误'), 'error')
  }
}

function confirmBatchDelete() { showBatchConfirm.value = true }

async function doBatchDelete() {
  showBatchConfirm.value = false
  try {
    for (const id of selectedIds.value) {
      await deleteProduct(id)
    }
    selectedIds.value = []
    await loadProducts()
  } catch (e: any) {
    showToast('操作失败: ' + (e.detail || e.message || '未知错误'), 'error')
  }
}

watch(search, () => { page.value = 1; loadProducts() })

onMounted(async () => {
  // Restore all filter params from URL
  const q = route.query
  if (q.search) search.value = q.search as string
  if (q.category_id) filters.category_id = Number(q.category_id)
  if (q.manufacturer_id) filters.manufacturer_id = Number(q.manufacturer_id)
  if (q.comm_method) filters.comm_method = Number(q.comm_method)
  if (q.comm_protocol) filters.comm_protocol = Number(q.comm_protocol)
  if (q.power_supply) filters.power_supply = Number(q.power_supply)
  if (q.page) page.value = Number(q.page)
  const [cmRes, cpRes, psRes, mfgRes, catRes] = await Promise.all([
    fetchCommMethods(), fetchCommProtocols(), fetchPowerSupplies(), fetchManufacturers(1, 200), fetchCategoryTree(),
  ])
  commMethods.value = cmRes.comm_methods
  commProtocols.value = cpRes.comm_protocols
  powerSupplies.value = psRes.power_supplies
  manufacturers.value = mfgRes.manufacturers as Manufacturer[]
  categoryTree.value = catRes.tree || []
  flatCategories.value = flattenTree(categoryTree.value)
  await loadProducts()
})
</script>
