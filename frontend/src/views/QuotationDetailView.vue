<template>
  <PageHeader :title="quotation ? `报价单 ${quotation.quote_number}` : '报价单详情'" :breadcrumb="[{ label: '报价单', to: '/quotations' }, { label: quotation?.quote_number || '详情', to: '' }]">
    <span v-if="quotation?.download_count" class="text-sm text-muted" style="margin:0 8px">已下载 {{ quotation.download_count }} 次</span>
    <button v-if="quotation" class="btn-secondary" @click="openExport">导出表格</button>
    <button v-if="quotation" class="btn-secondary" @click="showBom = !showBom">{{ showBom ? '收起' : '编辑' }} BOM 表格</button>
    <button class="btn-secondary" @click="$router.back()">返回</button>
  </PageHeader>

  <AsyncContainer :loading="loading" :error="loadError" retry @retry="load" />
  <template v-if="!loading && !loadError && quotation">
  <div class="card mb-16">
    <div class="form-grid" style="margin-bottom:16px">
      <div><span class="text-muted text-sm">编号</span><br class="font-mono">{{ quotation!.quote_number }}</div>
      <div><span class="text-muted text-sm">客户</span><br>{{ quotation!.client_name || '—' }}</div>
      <div><span class="text-muted text-sm">有效期</span><br>{{ quotation!.valid_days }}天</div>
      <div><span class="text-muted text-sm">税率（含税）</span><br>{{ fmtRate(quotation!.tax_rate) }}%</div>
      <div><span class="text-muted text-sm">状态</span><br>{{ quotation!.status }}</div>
    </div>

    <table class="data-table" v-if="quotation.items.length">
      <thead><tr><th>#</th><th>产品名称</th><th>型号/SKU</th><th>功能描述</th><th>数量</th><th>单价</th><th>折扣%</th><th>小计</th><th>备注</th><th v-if="canViewCost">成本</th></tr></thead>
      <tbody>
        <tr v-for="(item, idx) in quotation.items" :key="item.id">
          <td>{{ idx + 1 }}</td>
          <td>{{ item.product_snapshot?.name || '—' }}</td>
          <td class="font-mono text-sm">{{ (item.product_snapshot?.model || '') + (item.product_snapshot?.sku ? ' / ' + item.product_snapshot.sku : '') || '—' }}</td>
          <td class="text-sm text-muted" style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="getDesc(item)">{{ getDesc(item) || '—' }}</td>
          <td>{{ item.quantity }}</td>
          <td class="font-mono">{{ item.unit_price }}</td>
          <td>{{ item.discount_rate }}</td>
          <td class="font-mono">{{ item.amount?.toFixed(2) }}</td>
          <td>{{ item.remark || '—' }}</td>
          <td class="font-mono" v-if="canViewCost">{{ item.product_snapshot?.cost_price || '—' }}</td>
        </tr>
      </tbody>
      <tfoot>
        <tr>
          <td colspan="7" style="text-align:right;font-weight:600">合计（含税）</td>
          <td class="font-mono" style="font-weight:700">¥{{ quotation.items.reduce((s: number, i: QuotationItem) => s + (i.amount || 0), 0).toLocaleString(undefined, {minimumFractionDigits:2}) }}</td>
          <td></td>
          <td v-if="canViewCost"></td>
        </tr>
      </tfoot>
    </table>
    <div v-else class="empty-state" style="padding:24px"><p>暂无项目</p></div>
  </div>

  </template>

  <div v-if="showBom" class="card mb-16">
    <BOMSpreadsheet :quotationId="Number(route.params.id)" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { useRoute } from 'vue-router'
import AsyncContainer from '../components/AsyncContainer.vue'
import PageHeader from '../components/PageHeader.vue'
import BOMSpreadsheet from '../components/BOMSpreadsheet.vue'
import { fetchQuotation, quotationExportUrl } from '../api'
import { formatDescriptionWithSpecs } from '../utils/markdown'
import type { Quotation, QuotationItem } from '../types'

const route = useRoute()
const quotation = ref<Quotation | null>(null)
const loading = ref(false)
const loadError = ref('')
const showBom = ref(false)
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})
// 成本列只在有权限时渲染（后端同样会裁掉值）
const canViewCost = inject('canViewCost', ref(false))

function getDesc(item: { product_snapshot?: { description?: string; specs?: Record<string, unknown> } }): string {
  const snap = item.product_snapshot || {}
  return formatDescriptionWithSpecs(snap.description || '', snap.specs || {}) || '—'
}

function openExport() { if (quotation.value) window.open(quotationExportUrl(quotation.value.id), '_blank', 'noopener') }

// 税率展示：与导出 xlsx 的 _fmt_rate 一致，13.0 显示为 13（不要出现「13.0%」）
function fmtRate(rate: unknown): string {
  const value = Number(rate ?? 0)
  if (!Number.isFinite(value)) return '0'
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)))
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetchQuotation(Number(route.params.id))
    quotation.value = res.quotation
  } catch (e: unknown) {
    loadError.value = (e instanceof Error ? e.message : String(e)) || '加载失败'
  }
  loading.value = false
}

onMounted(load)
</script>
