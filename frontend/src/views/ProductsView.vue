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
      <div class="filter-group" v-if="categoryTree.length">
        <span class="filter-label">品类</span>
        <span v-for="c in flatCategories" :key="c.id" :class="['filter-tag', { active: filters.category_id === c.id }]" @click="toggleCategory(c.id)">{{ c.name }}</span>
      </div>
      <div class="filter-group">
        <span class="filter-label">通讯方式</span>
        <span v-for="m in commMethods" :key="m.id" :class="['filter-tag', { active: filters.comm_method === m.id }]" @click="toggleFilter('comm_method', m.id)">{{ m.name }}</span>
      </div>
      <div class="filter-group">
        <span class="filter-label">协议</span>
        <span v-for="p in commProtocols" :key="p.id" :class="['filter-tag', { active: filters.comm_protocol === p.id }]" @click="toggleFilter('comm_protocol', p.id)">{{ p.name }}</span>
      </div>
      <div class="filter-group">
        <span class="filter-label">供电</span>
        <span v-for="p in powerSupplies" :key="p.id" :class="['filter-tag', { active: filters.power_supply === p.id }]" @click="toggleFilter('power_supply', p.id)">{{ p.name }}</span>
      </div>
      <div class="filter-group" v-if="manufacturers.length > 1">
        <span class="filter-label">厂商</span>
        <span v-for="m in manufacturers" :key="m.id" :class="['filter-tag', { active: filters.manufacturer_id === m.id }]" @click="toggleFilter('manufacturer_id', m.id)">{{ m.name }}</span>
      </div>
    </div>
  </div>

  <div class="card">
    <table class="data-table" v-if="products.length">
      <thead>
        <tr>
          <th style="width:32px"><input type="checkbox" :checked="selectedIds.length === products.length" @change="toggleAll($event)" /></th>
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
            <button class="btn-icon btn-sm" @click="$router.push(`/products/${p.id}/edit`)"><PencilIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" @click="confirmDelete(p)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state"><InboxIcon /><p>暂无产品</p></div>
    <Pagination :total="total" :page="page" :per-page="perPage" @change="p => { page = p; loadProducts() }" />
  </div>

  <ConfirmDialog title="删除产品" :message="`确定删除「${deleteTarget?.name}」？`" :visible="!!deleteTarget" @confirm="doDelete" @cancel="deleteTarget = null" />
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue'
import { PlusIcon, PencilIcon, Trash2Icon, InboxIcon, DownloadIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import SearchInput from '../components/SearchInput.vue'
import TagBadge from '../components/TagBadge.vue'
import Pagination from '../components/Pagination.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { fetchProducts, deleteProduct, exportProducts, fetchCommMethods, fetchCommProtocols, fetchPowerSupplies, fetchManufacturers, fetchCategoryTree } from '../api'

const products = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const search = ref('')
const deleteTarget = ref<any>(null)
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

const commMethods = ref<any[]>([])
const commProtocols = ref<any[]>([])
const powerSupplies = ref<any[]>([])
const manufacturers = ref<any[]>([])
const categoryTree = ref<any[]>([])
const flatCategories = ref<any[]>([])

const exportUrl = exportProducts()

const filters = reactive<Record<string, any>>({
  category_id: null,
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
  if (filters.category_id) parts.push(`category_id=${filters.category_id}`)
  if (filters.comm_method) parts.push(`comm_method=${filters.comm_method}`)
  if (filters.comm_protocol) parts.push(`comm_protocol=${filters.comm_protocol}`)
  if (filters.power_supply) parts.push(`power_supply=${filters.power_supply}`)
  if (filters.manufacturer_id) parts.push(`manufacturer_id=${filters.manufacturer_id}`)
  parts.push(`page=${page.value}`)
  parts.push(`per_page=${perPage}`)
  return parts.join('&')
}

async function loadProducts() {
  try {
    const res = await fetchProducts(buildParams())
    products.value = res.products
    total.value = res.total
  } catch (e: any) {
    console.error(e)
  }
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
