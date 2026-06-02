<template>
  <PageHeader title="供应商管理">
    <SearchInput v-model="search" placeholder="搜索供应商..." autofocus />
    <button class="btn-primary" @click="openAdd">
      <PlusIcon style="width:16px;height:16px" />新增供应商
    </button>
  </PageHeader>

  <div class="card">
    <div v-if="loading" class="empty-state"><p>加载中...</p></div>
    <table v-else-if="suppliers.length" class="data-table">
      <thead><tr><th>名称</th><th>联系人</th><th>电话</th><th>邮箱</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="s in suppliers" :key="s.id">
          <td>{{ s.name }}</td>
          <td>{{ s.contact_person || '—' }}</td>
          <td>{{ s.phone || '—' }}</td>
          <td>{{ s.email || '—' }}</td>
          <td>
            <button class="btn-icon btn-sm" @click="openEdit(s)"><PencilIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" @click="confirmDelete(s)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state"><InboxIcon /><p>暂无供应商</p></div>
    <Pagination :total="total" :page="page" :per-page="perPage" @change="p => { page = p; load() }" />
  </div>

  <Modal :title="editing ? '编辑供应商' : '新增供应商'" :visible="modalVisible" @close="modalVisible = false">
    <div class="form-grid">
      <div class="form-group"><label>名称 *</label><input v-model="form.name" /></div>
      <div class="form-group"><label>联系人</label><input v-model="form.contact_person" /></div>
      <div class="form-group"><label>电话</label><input v-model="form.phone" /></div>
      <div class="form-group"><label>邮箱</label><input v-model="form.email" /></div>
      <div class="form-group full"><label>网站</label><input v-model="form.website" /></div>
      <div class="form-group full"><label>备注</label><textarea v-model="form.notes" rows="2" /></div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="modalVisible = false">取消</button>
      <button class="btn-primary" @click="save">保存</button>
    </template>
  </Modal>

  <ConfirmDialog title="删除供应商" :message="`确定删除「${deleteTarget?.name}」？`" :visible="!!deleteTarget" @confirm="doDelete" @cancel="deleteTarget = null" />
</template>

<script setup lang="ts">
import { ref, watch, onMounted, inject } from 'vue'
import { PlusIcon, PencilIcon, Trash2Icon, InboxIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import SearchInput from '../components/SearchInput.vue'
import Pagination from '../components/Pagination.vue'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { fetchSuppliersPaginated, createSupplier, updateSupplier, deleteSupplier } from '../api'
import type { Supplier } from '../types'

const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const suppliers = ref<Supplier[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 25
const search = ref('')
const modalVisible = ref(false)
const editing = ref<any>(null)
const form = ref<any>({ name: '', contact_person: '', phone: '', email: '', website: '', notes: '' })
const deleteTarget = ref<any>(null)

function buildQuery() {
  const parts: string[] = []
  if (search.value) parts.push(`search=${encodeURIComponent(search.value)}`)
  parts.push(`page=${page.value}`)
  parts.push(`per_page=${perPage}`)
  return parts.join('&')
}

const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await fetchSuppliersPaginated(buildQuery())
    suppliers.value = res.suppliers
    total.value = res.total
  } catch (e: any) { showToast(e.message || '加载失败', 'error') }
  loading.value = false
}

function openAdd() {
  editing.value = null
  form.value = { name: '', contact_person: '', phone: '', email: '', website: '', notes: '' }
  modalVisible.value = true
}

function openEdit(s: any) {
  editing.value = s
  form.value = { ...s }
  modalVisible.value = true
}

async function save() {
  try {
    if (editing.value) {
      await updateSupplier(editing.value.id, form.value)
      showToast('已更新', 'success')
    } else {
      await createSupplier(form.value)
      showToast('已创建', 'success')
    }
    modalVisible.value = false
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

function confirmDelete(s: any) { deleteTarget.value = s }

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await deleteSupplier(deleteTarget.value.id)
    showToast('已删除', 'success')
    deleteTarget.value = null
    await load()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

watch(search, () => { page.value = 1; load() })
onMounted(load)
</script>
