<template>
  <PageHeader title="报价单">
    <button class="btn-primary" @click="$router.push('/solutions')">
      <PlusIcon style="width:16px;height:16px" />新增
    </button>
    <button v-if="selectedIds.size" class="btn-danger" @click="confirmBatchDelete">
      <Trash2Icon style="width:14px;height:14px" />删除选中 ({{ selectedIds.size }})
    </button>
  </PageHeader>

  <div class="card" style="margin-bottom:16px;padding:8px 12px">
    <div style="display:flex;gap:12px;align-items:center">
      <input v-model="search" placeholder="搜索编号/标题/客户..." style="width:240px" @input="onSearch" />
      <select v-model="statusFilter" style="width:120px" @change="load()">
        <option value="">全部状态</option>
        <option value="draft">草稿</option>
        <option value="sent">已发送</option>
        <option value="accepted">已确认</option>
        <option value="done">已完成</option>
      </select>
    </div>
  </div>

  <div class="card">
    <AsyncContainer :loading="loading" :error="loadError" retry @retry="load" />
    <table v-if="!loading && !loadError && quotations.length" class="data-table">
      <thead><tr>
        <th style="width:32px"><input type="checkbox" :checked="allSelected" @change="toggleAll" /></th>
        <th>编号</th><th>标题</th><th>客户</th><th>状态</th><th>金额</th><th>下载</th><th>创建时间</th><th>操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="q in quotations" :key="q.id">
          <td><input type="checkbox" :checked="selectedIds.has(q.id)" @change="toggleSelect(q.id)" /></td>
          <td class="font-mono text-sm">{{ q.quote_number }}</td>
          <td>{{ q.title || '—' }}</td>
          <td>{{ q.client_name || '—' }}</td>
          <td>
            <select :value="q.status" @change="changeStatus(q, ($event.target as HTMLSelectElement).value)" style="font-size:12px;padding:2px 6px;width:90px">
              <option value="draft">草稿</option>
              <option value="sent">已发送</option>
              <option value="accepted">已确认</option>
              <option value="done">已完成</option>
            </select>
          </td>
          <td class="font-mono">¥{{ Number(q.total_amount).toLocaleString() }}</td>
          <td class="text-sm text-muted">{{ q.download_count || 0 }}</td>
          <td class="text-sm">{{ formatTime(q.created_at) }}</td>
          <td>
            <button class="btn-icon btn-sm" title="查看" @click="$router.push(`/quotations/${q.id}`)"><EyeIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" title="删除" @click="confirmDelete(q)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="!loading && !loadError && !quotations.length" class="empty-state"><InboxIcon /><p>暂无报价单</p></div>
    <Pagination :total="total" :page="page" :per-page="perPage" @change="p => { page = p; load() }" @update:per-page="s => { perPage = s; page = 1; load() }" />
  </div>

  <ConfirmDialog title="删除报价单" :message="`确定删除报价单「${deleteTarget?.quote_number}」？`" :visible="!!deleteTarget" @confirm="doDelete" @cancel="deleteTarget = null" />
  <ConfirmDialog title="批量删除" :message="`确定删除 ${selectedIds.size} 个报价单？`" :visible="showBatchConfirm" @confirm="doBatchDelete" @cancel="showBatchConfirm = false" />
</template>

<script setup lang="ts">
import { ref, onMounted, inject, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PlusIcon, Trash2Icon, InboxIcon, EyeIcon } from 'lucide-vue-next'
import { formatTime } from '../utils/time'
import PageHeader from '../components/PageHeader.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import AsyncContainer from '../components/AsyncContainer.vue'
import Pagination from '../components/Pagination.vue'
import { fetchQuotations, deleteQuotation, batchDeleteQuotations, updateQuotation } from '../api'
import type { Quotation } from '../types'

const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})
const route = useRoute()
const router = useRouter()

const quotations = ref<Quotation[]>([])
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const deleteTarget = ref<any>(null)
const search = ref('')
const statusFilter = ref('')
const selectedIds = ref<Set<number>>(new Set())
const showBatchConfirm = ref(false)
let searchTimer: any = null

const allSelected = computed(() => quotations.value.length > 0 && quotations.value.every(q => selectedIds.value.has(q.id)))

const loading = ref(false)
const loadError = ref('')

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; load() }, 300)
}

async function load() {
  loading.value = true
  loadError.value = ''
  // Sync to URL
  const q: Record<string, string> = {}
  if (search.value) q.search = search.value
  if (statusFilter.value) q.status = statusFilter.value
  if (page.value > 1) q.page = String(page.value)
  router.replace({ path: route.path, query: Object.keys(q).length ? q : {} })
  try {
    let params = `page=${page.value}&per_page=${perPage.value}`
    if (search.value) params += `&search=${encodeURIComponent(search.value)}`
    if (statusFilter.value) params += `&status=${statusFilter.value}`
    const res = await fetchQuotations(params)
    quotations.value = res.quotations
    total.value = res.total
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  }
  loading.value = false
}

function toggleSelect(id: number) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleAll() {
  if (allSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(quotations.value.map(q => q.id))
  }
}

function confirmBatchDelete() {
  showBatchConfirm.value = true
}

async function doBatchDelete() {
  try {
    await batchDeleteQuotations([...selectedIds.value])
    showToast(`已删除 ${selectedIds.value.size} 个报价单`, 'success')
    selectedIds.value = new Set()
    showBatchConfirm.value = false
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function changeStatus(q: Quotation, status: string) {
  try {
    await updateQuotation(q.id, { status })
    q.status = status
    showToast('状态已更新', 'success')
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

function confirmDelete(q: any) { deleteTarget.value = q }

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await deleteQuotation(deleteTarget.value.id)
    showToast('已删除', 'success')
    deleteTarget.value = null
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

onMounted(() => {
  const q = route.query
  if (q.search) search.value = q.search as string
  if (q.status) statusFilter.value = q.status as string
  if (q.page) page.value = Number(q.page)
  load()
})
</script>
