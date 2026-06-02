<template>
  <PageHeader :title="quotation ? `报价单 ${quotation.quote_number}` : '报价单详情'" :breadcrumb="[{ label: '报价单', to: '/quotations' }, { label: quotation?.quote_number || '详情', to: '' }]">
    <button v-if="quotation" class="btn-secondary" @click="openExport">导出 xlsx</button>
    <button class="btn-secondary" @click="$router.back()">返回</button>
  </PageHeader>

  <div v-if="loading" class="empty-state"><p>加载中...</p></div>
  <div v-else-if="loadError" class="empty-state"><p style="color:var(--color-danger)">{{ loadError }}</p><button class="btn-secondary btn-sm" style="margin-top:8px" @click="load">重试</button></div>
  <div v-else-if="quotation" class="card mb-16">
    <div class="form-grid" style="margin-bottom:16px">
      <div><span class="text-muted text-sm">编号</span><br class="font-mono">{{ quotation.quote_number }}</div>
      <div><span class="text-muted text-sm">客户</span><br>{{ quotation.client_name || '—' }}</div>
      <div><span class="text-muted text-sm">有效期</span><br>{{ quotation.valid_days }}天</div>
      <div><span class="text-muted text-sm">税率</span><br>{{ quotation.tax_rate }}%</div>
      <div><span class="text-muted text-sm">状态</span><br>{{ quotation.status }}</div>
      <div><span class="text-muted text-sm">总金额</span><br class="font-mono">{{ quotation.total_amount }}</div>
    </div>

    <table class="data-table" v-if="quotation.items.length">
      <thead><tr><th>序号</th><th>产品</th><th>SKU</th><th>数量</th><th>单价</th><th>金额</th><th>折扣(%)</th><th>备注</th></tr></thead>
      <tbody>
        <tr v-for="(item, idx) in quotation.items" :key="item.id">
          <td>{{ idx + 1 }}</td>
          <td>{{ item.product_snapshot?.name || '—' }}</td>
          <td class="font-mono text-sm">{{ item.product_snapshot?.sku || '' }}</td>
          <td>{{ item.quantity }}</td>
          <td class="font-mono">{{ item.unit_price }}</td>
          <td class="font-mono">{{ item.amount?.toFixed(2) }}</td>
          <td>{{ item.discount_rate }}</td>
          <td>{{ item.remark }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state" style="padding:24px"><p>暂无项目</p></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../components/PageHeader.vue'
import { fetchQuotation, quotationExportUrl } from '../api'
import type { Quotation } from '../types'

const route = useRoute()
const quotation = ref<Quotation | null>(null)
const loading = ref(false)
const loadError = ref('')
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

function openExport() { if (quotation.value) window.open(quotationExportUrl(quotation.value.id), '_blank') }

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetchQuotation(Number(route.params.id))
    quotation.value = res.quotation
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  }
  loading.value = false
}

onMounted(load)
</script>
