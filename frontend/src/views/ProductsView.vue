<template>
  <PageHeader title="产品列表">
    <SearchInput v-model="search" placeholder="搜索型号/名称..." autofocus />
    <button v-if="selectedIds.length >= 2" class="btn-primary" style="background:var(--color-accent)" @click="$router.push(`/products/compare?ids=${selectedIds.join(',')}`)">
      对比选中 ({{ selectedIds.length }})
    </button>
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
      <!-- 品类 — two-level, default open -->
      <div class="filter-group" v-if="categoryTree.length">
        <div class="filter-group-header" @click="filterOpen.category = !filterOpen.category">
          <span class="filter-label">品类</span><span class="filter-toggle">{{ filterOpen.category ? '▲' : '▼' }}</span>
        </div>
        <div :class="['filter-tags', filterOpen.category ? 'expanded' : 'collapsed']">
          <!-- Row 1: parent categories -->
          <div class="filter-row">
            <span v-for="p in categoryTree" :key="p.id" :class="['filter-tag', { active: filters.category_id === p.id }]" @click="toggleCategory(p.id)">{{ p.name }}</span>
          </div>
          <!-- Row 2: children of selected parent -->
          <div v-for="p in categoryTree" :key="'sub-'+p.id">
            <div v-if="filters.category_id === p.id && p.children?.length" class="filter-row sub-row">
              <span v-for="c in p.children" :key="c.id" :class="['filter-tag sub', { active: filters.sub_category_id === c.id }]" @click="toggleSubCategory(c.id)">{{ c.name }}</span>
            </div>
          </div>
        </div>
      </div>
      <!-- 厂商 — default open -->
      <div class="filter-group" v-if="manufacturers.length > 1">
        <div class="filter-group-header" @click="filterOpen.manufacturer = !filterOpen.manufacturer">
          <span class="filter-label">厂商</span><span class="filter-toggle">{{ filterOpen.manufacturer ? '▲' : '▼' }}</span>
        </div>
        <div :class="['filter-tags', filterOpen.manufacturer ? 'expanded' : 'collapsed']">
          <span v-for="m in manufacturers" :key="m.id" :class="['filter-tag', { active: filters.manufacturer_id === m.id }]" @click="toggleFilter('manufacturer_id', m.id)">{{ m.name }}</span>
        </div>
      </div>
      <!-- 通讯方式/协议/供电 — same row -->
      <div style="display:flex;gap:16px;flex-wrap:wrap">
        <div class="filter-group" style="flex:1;min-width:140px">
          <div class="filter-group-header" @click="filterOpen.comm_method = !filterOpen.comm_method">
            <span class="filter-label">通讯方式</span><span class="filter-toggle">{{ filterOpen.comm_method ? '▲' : '▼' }}</span>
          </div>
          <div :class="['filter-tags', filterOpen.comm_method ? 'expanded' : 'collapsed']">
            <span v-for="m in commMethods" :key="m.id" :class="['filter-tag', { active: filters.comm_method === m.id }]" @click="toggleFilter('comm_method', m.id)">{{ m.name }}</span>
          </div>
        </div>
        <div class="filter-group" style="flex:1;min-width:140px">
          <div class="filter-group-header" @click="filterOpen.comm_protocol = !filterOpen.comm_protocol">
            <span class="filter-label">协议</span><span class="filter-toggle">{{ filterOpen.comm_protocol ? '▲' : '▼' }}</span>
          </div>
          <div :class="['filter-tags', filterOpen.comm_protocol ? 'expanded' : 'collapsed']">
            <span v-for="p in commProtocols" :key="p.id" :class="['filter-tag', { active: filters.comm_protocol === p.id }]" @click="toggleFilter('comm_protocol', p.id)">{{ p.name }}</span>
          </div>
        </div>
        <div class="filter-group" style="flex:1;min-width:140px">
          <div class="filter-group-header" @click="filterOpen.power_supply = !filterOpen.power_supply">
            <span class="filter-label">供电</span><span class="filter-toggle">{{ filterOpen.power_supply ? '▲' : '▼' }}</span>
          </div>
          <div :class="['filter-tags', filterOpen.power_supply ? 'expanded' : 'collapsed']">
            <span v-for="p in powerSupplies" :key="p.id" :class="['filter-tag', { active: filters.power_supply === p.id }]" @click="toggleFilter('power_supply', p.id)">{{ p.name }}</span>
          </div>
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
          <th>名称</th><th>型号</th><th>品类</th><th>厂商</th><th>通讯</th><th>供电</th><th>操作</th>
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
          <td>{{ p.category_name }}</td>
          <td>{{ p.manufacturer_name }}</td>
          <td>
            <TagBadge v-for="cm in p.comm_methods.slice(0,3)" :key="cm.method_id" :label="cm.method_name" />
            <span v-if="p.comm_methods.length > 3" class="text-sm text-muted">+{{ p.comm_methods.length - 3 }}</span>
          </td>
          <td>
            <TagBadge v-for="ps in p.power_supplies" :key="ps.power_id" :label="ps.power_name" />
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
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue'
import { PlusIcon, PencilIcon, Trash2Icon, InboxIcon, DownloadIcon } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import SearchInput from '../components/SearchInput.vue'
import TagBadge from '../components/TagBadge.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { fetchProducts, deleteProduct, exportProducts, fetchCommMethods, fetchCommProtocols, fetchPowerSupplies, fetchManufacturers, fetchCategoryTree } from '../api'
import type { Product, Manufacturer } from '../types'

const route = useRoute()

const products = ref<Product[]>([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const MAX_PER_PAGE = 100
const search = ref('')
const deleteTarget = ref<Product | null>(null)
const filterExpanded = ref(true)
const filterOpen = reactive({
  category: true,
  manufacturer: true,
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
  filters.sub_category_id = null  // reset sub when parent changes
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
    console.error(e)
  }
}

watch(search, () => { page.value = 1; loadProducts() })

onMounted(async () => {
  const q = (route.query.search as string) || ''
  if (q) search.value = q
  const [cmRes, cpRes, psRes, mfgRes, catRes] = await Promise.all([
    fetchCommMethods(), fetchCommProtocols(), fetchPowerSupplies(), fetchManufacturers(), fetchCategoryTree(),
  ])
  commMethods.value = cmRes.comm_methods
  commProtocols.value = cpRes.comm_protocols
  powerSupplies.value = psRes.power_supplies
  manufacturers.value = mfgRes.manufacturers
  categoryTree.value = catRes.tree || []
  flatCategories.value = flattenTree(categoryTree.value)
  await loadProducts()
})
</script>
