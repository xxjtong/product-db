<template>
  <PageHeader title="报价单">
    <button class="btn-primary" @click="$router.push('/solutions')">
      <PlusIcon style="width:16px;height:16px" />新增
    </button>
  </PageHeader>

  <div class="card">
    <table class="data-table" v-if="quotations.length">
      <thead><tr><th>编号</th><th>标题</th><th>客户</th><th>状态</th><th>金额</th><th>创建时间</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="q in quotations" :key="q.id">
          <td class="font-mono text-sm">{{ q.quote_number }}</td>
          <td>{{ q.title || '—' }}</td>
          <td>{{ q.client_name || '—' }}</td>
          <td><span :class="['tag', q.status === 'draft' ? 'tag-default' : q.status === 'sent' ? 'tag-wifi' : 'tag-lorawan']">{{ q.status }}</span></td>
          <td class="font-mono">{{ q.total_amount }}</td>
          <td class="text-sm">{{ q.created_at }}</td>
          <td>
            <button class="btn-icon btn-sm" title="查看" @click="$router.push(`/quotations/${q.id}`)"><EyeIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" title="删除" @click="confirmDelete(q)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state"><InboxIcon /><p>暂无报价单</p></div>
    <Pagination :total="total" :page="page" :per-page="perPage" @change="p => { page = p; load() }" />
  </div>

  <ConfirmDialog title="删除报价单" :message="`确定删除报价单「${deleteTarget?.quote_number}」？`" :visible="!!deleteTarget" @confirm="doDelete" @cancel="deleteTarget = null" />
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { PlusIcon, Trash2Icon, InboxIcon, EyeIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Pagination from '../components/Pagination.vue'
import { fetchQuotations, deleteQuotation } from '../api'

const showToast = inject<(msg: string, type?: string) => void>('toast')!

const quotations = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const perPage = 20
const deleteTarget = ref<any>(null)

async function load() {
  const res = await fetchQuotations(`page=${page.value}&per_page=${perPage}`)
  quotations.value = res.quotations
  total.value = res.total
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

onMounted(load)
</script>
