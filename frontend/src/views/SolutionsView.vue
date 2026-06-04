<template>
  <PageHeader title="方案管理">
    <button class="btn-primary" @click="openAdd">
      <PlusIcon style="width:16px;height:16px" />新增方案
    </button>
    <button v-if="selectedIds.size" class="btn-danger" @click="confirmBatchDelete">
      <Trash2Icon style="width:14px;height:14px" />删除选中 ({{ selectedIds.size }})
    </button>
  </PageHeader>

  <div class="card" style="margin-bottom:16px;padding:8px 12px">
    <div style="display:flex;gap:12px;align-items:center">
      <input v-model="search" placeholder="搜索方案/客户/项目..." style="width:240px" @input="onSearch" />
      <select v-model="statusFilter" @change="load()" style="width:120px">
        <option value="">全部状态</option>
        <option value="draft">草稿</option>
        <option value="active">进行中</option>
        <option value="done">完成</option>
      </select>
    </div>
  </div>

  <div class="card">
    <div v-if="loading" class="empty-state"><p>加载中...</p></div>
    <div v-else-if="loadError" class="empty-state"><p style="color:var(--color-danger)">{{ loadError }}</p><button class="btn-secondary btn-sm" style="margin-top:8px" @click="load">重试</button></div>
    <table v-else-if="solutions.length" class="data-table">
      <thead><tr>
        <th style="width:32px"><input type="checkbox" :checked="allSelected" @change="toggleAll" /></th>
        <th>名称</th><th>客户</th><th>项目</th><th>状态</th><th>总价</th><th>更新时间</th><th>操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="s in solutions" :key="s.id">
          <td><input type="checkbox" :checked="selectedIds.has(s.id)" @change="toggleSelect(s.id)" /></td>
          <td>{{ s.name }}</td>
          <td>{{ s.client_name || '—' }}</td>
          <td>{{ s.project_name || '—' }}</td>
          <td>
            <select :value="s.status" @change="changeStatus(s, ($event.target as HTMLSelectElement).value)" style="font-size:12px;padding:2px 6px;width:90px">
              <option value="draft">草稿</option>
              <option value="active">进行中</option>
              <option value="done">完成</option>
            </select>
          </td>
          <td class="font-mono">¥{{ Number(s.total_price).toLocaleString() }}</td>
          <td class="text-sm">{{ s.updated_at }}</td>
          <td>
            <button class="btn-icon btn-sm" title="查看" @click="$router.push(`/solutions/${s.id}`)"><EyeIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" title="编辑" @click="openEdit(s)"><PencilIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" title="删除" @click="confirmDelete(s)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else-if="!loading" class="empty-state"><InboxIcon /><p>暂无方案</p></div>
    <Pagination :total="total" :page="page" :per-page="perPage" @change="p => { page = p; load() }" @update:per-page="s => { perPage = s; page = 1; load() }" />
  </div>

  <Modal :title="editing ? '编辑方案' : '新增方案'" :visible="modalVisible" @close="modalVisible = false">
    <div class="form-grid">
      <div class="form-group full"><label>名称 *</label><input v-model="form.name" /></div>
      <div class="form-group"><label>客户</label><input v-model="form.client_name" /></div>
      <div class="form-group"><label>项目</label><input v-model="form.project_name" /></div>
      <div class="form-group full"><label>备注</label><textarea v-model="form.notes" rows="2" /></div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="modalVisible = false">取消</button>
      <button class="btn-primary" @click="save">保存</button>
    </template>
  </Modal>

  <ConfirmDialog title="删除方案" :message="`确定删除「${deleteTarget?.name}」？`" :visible="!!deleteTarget" @confirm="doDelete" @cancel="deleteTarget = null" />
  <ConfirmDialog title="批量删除" :message="`确定删除 ${selectedIds.size} 个方案？`" :visible="showBatchConfirm" @confirm="doBatchDelete" @cancel="showBatchConfirm = false" />
</template>

<script setup lang="ts">
import { ref, onMounted, inject, computed } from 'vue'
import { useRouter } from 'vue-router'
import { PlusIcon, PencilIcon, Trash2Icon, InboxIcon, EyeIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Pagination from '../components/Pagination.vue'
import { fetchSolutions, createSolution, updateSolution, deleteSolution, batchDeleteSolutions } from '../api'
import type { Solution } from '../types'

const router = useRouter()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const search = ref('')
const solutions = ref<Solution[]>([])
const statusFilter = ref('')
const total = ref(0)
const page = ref(1)
const perPage = ref(20)
const modalVisible = ref(false)
const editing = ref<any>(null)
const form = ref<any>({ name: '', client_name: '', project_name: '', notes: '' })
const deleteTarget = ref<any>(null)
const selectedIds = ref<Set<number>>(new Set())
const showBatchConfirm = ref(false)
let searchTimer: any = null

const allSelected = computed(() => solutions.value.length > 0 && solutions.value.every(s => selectedIds.value.has(s.id)))

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; load() }, 300)
}

const loading = ref(false)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    let params = `page=${page.value}&per_page=${perPage.value}`
    if (search.value) params += `&search=${encodeURIComponent(search.value)}`
    if (statusFilter.value) params += `&status=${statusFilter.value}`
    const res = await fetchSolutions(params)
    solutions.value = res.solutions
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
    selectedIds.value = new Set(solutions.value.map(s => s.id))
  }
}

function confirmBatchDelete() {
  showBatchConfirm.value = true
}

async function doBatchDelete() {
  try {
    await batchDeleteSolutions([...selectedIds.value])
    showToast(`已删除 ${selectedIds.value.size} 个方案`, 'success')
    selectedIds.value = new Set()
    showBatchConfirm.value = false
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

function openAdd() {
  editing.value = null
  form.value = { name: '', client_name: '', project_name: '', notes: '' }
  modalVisible.value = true
}

function openEdit(s: any) {
  editing.value = s
  form.value = { name: s.name, client_name: s.client_name, project_name: s.project_name, notes: s.notes }
  modalVisible.value = true
}

async function save() {
  try {
    if (editing.value) {
      await updateSolution(editing.value.id, form.value)
      showToast('已更新', 'success')
    } else {
      const res = await createSolution(form.value) as any
      showToast('已创建', 'success')
      modalVisible.value = false
      router.push(`/solutions/${res.solution.id}`)
      return
    }
    modalVisible.value = false
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function changeStatus(s: any, status: string) {
  try {
    await updateSolution(s.id, { status })
    s.status = status
    showToast('状态已更新', 'success')
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

function confirmDelete(s: any) { deleteTarget.value = s }

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await deleteSolution(deleteTarget.value.id)
    showToast('已删除', 'success')
    deleteTarget.value = null
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

onMounted(load)
</script>
