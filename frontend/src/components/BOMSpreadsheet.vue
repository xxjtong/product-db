<template>
  <div class="bom-spreadsheet">
    <div class="flex gap-8 items-center mb-12">
      <button class="btn-secondary btn-sm" @click="loadSnapshot"><RefreshCwIcon style="width:14px;height:14px" />重新加载</button>
      <button class="btn-primary btn-sm" @click="save"><SaveIcon style="width:14px;height:14px" />保存</button>
      <button class="btn-secondary btn-sm" @click="addRow"><PlusIcon style="width:14px;height:14px" />添加行</button>
      <button class="btn-secondary btn-sm" @click="exportXlsx"><DownloadIcon style="width:14px;height:14px" />导出 xlsx</button>
      <span v-if="dirty" class="text-sm" style="color:var(--color-danger)">未保存</span>
    </div>

    <div v-if="loading" class="text-sm text-muted" style="padding:16px">加载中...</div>

    <div v-else class="bom-table-wrap">
      <table class="bom-table">
        <thead>
          <tr>
            <th style="width:40px">#</th>
            <th style="width:200px">产品名称</th>
            <th style="width:120px">型号/SKU</th>
            <th style="width:160px">功能描述</th>
            <th style="width:60px">数量</th>
            <th style="width:80px">单价</th>
            <th style="width:60px">折扣%</th>
            <th style="width:80px">小计</th>
            <th style="width:80px">备注</th>
            <th style="width:30px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td class="text-center text-muted">{{ i + 1 }}</td>
            <td><input v-model="row.name" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model="row.sku" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model="row.description" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model.number="row.qty" type="number" min="0" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model.number="row.price" type="number" min="0" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model.number="row.discount" type="number" min="0" max="100" style="width:100%" @input="dirty = true" /></td>
            <td class="font-mono text-right">{{ subtotal(row) }}</td>
            <td><input v-model="row.remark" style="width:100%" @input="dirty = true" /></td>
            <td><button class="btn-icon btn-sm" @click="deleteRow(i)" title="删除行"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td colspan="7" class="text-right" style="font-weight:600">合计</td>
            <td class="font-mono text-right" style="font-weight:700">{{ totalPrice }}</td>
            <td></td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { RefreshCwIcon, SaveIcon, DownloadIcon, PlusIcon, Trash2Icon } from 'lucide-vue-next'
import { fetchBomSnapshot, saveBomSnapshot, bomExportUrl, fetchQuotationBom, saveQuotationBom } from '../api'

const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const props = defineProps<{ solutionId?: number; quotationId?: number }>()

interface BomRow { name: string; sku: string; qty: number; price: number; discount: number; description: string; remark: string }
const rows = ref<BomRow[]>([])
const loading = ref(true)
const dirty = ref(false)

function subtotal(r: BomRow): string {
  return (r.qty * r.price * (r.discount / 100)).toFixed(0)
}

function addRow() {
  rows.value.push({ name: '', sku: '', qty: 1, price: 0, discount: 100, description: '', remark: '' })
  dirty.value = true
}

function deleteRow(i: number) {
  if (!confirm('确定删除第 ' + (i + 1) + ' 行？')) return
  rows.value.splice(i, 1)
  dirty.value = true
}

const totalPrice = computed(() => {
  return rows.value.reduce((sum, r) => sum + r.qty * r.price * (r.discount / 100), 0).toFixed(0)
})

async function loadSnapshot() {
  loading.value = true
  try {
    if (props.quotationId) {
      const res = await fetchQuotationBom(props.quotationId)
      rows.value = (res.rows || []).map((r: any) => ({
        name: r.name || '', sku: r.sku || '', qty: Number(r.qty) || 1,
        price: Number(r.price) || 0, discount: Number(r.discount) || 100,
        description: r.description || '', remark: r.remark || '',
      }))
    } else if (props.solutionId) {
      const res = await fetchBomSnapshot(props.solutionId)
      const cells = res.bom_snapshot?.snapshot?.cells || {}
      const rowMap: Record<number, BomRow> = {}
      for (const [ref, cell] of Object.entries(cells)) {
        const c = cell as any
        const m = ref.match(/^([A-Z])(\d+)$/)
        if (!m) continue
        const col = m[1]
        const rowNum = parseInt(m[2])
        if (rowNum <= 1) continue
        if (!rowMap[rowNum]) rowMap[rowNum] = { name: '', sku: '', qty: 1, price: 0, discount: 100, description: '', remark: '' }
        const v = c.v ?? ''
        if (col === 'A') {/* row number, skip */}
        else if (col === 'B') rowMap[rowNum].name = String(v)
        else if (col === 'C') rowMap[rowNum].sku = String(v)
        else if (col === 'D') rowMap[rowNum].description = String(v)
        else if (col === 'E') rowMap[rowNum].qty = Number(v) || 1
        else if (col === 'F') rowMap[rowNum].price = Number(v) || 0
        else if (col === 'G') rowMap[rowNum].discount = Number(v) || 100
        else if (col === 'H') {/* subtotal, computed */}
        else if (col === 'I') rowMap[rowNum].remark = String(v)
      }
      rows.value = Object.keys(rowMap).sort((a,b) => Number(a)-Number(b)).map(k => rowMap[Number(k)])
    }
    dirty.value = false
  } catch (e: any) {
    showToast('BOM 加载失败: ' + (e.detail || e.message || '未知错误'), 'error')
  }
  loading.value = false
}

async function save() {
  try {
    if (props.quotationId) {
      const data = rows.value.map(r => ({
        name: r.name, sku: r.sku, qty: r.qty, price: r.price,
        discount: r.discount, description: r.description, remark: r.remark,
      }))
      await saveQuotationBom(props.quotationId, { rows: data })
    } else if (props.solutionId) {
      const cells: Record<string, any> = {}
      rows.value.forEach((r, i) => {
        const row = i + 1
        cells[`A${row}`] = { v: i + 1 }
        cells[`B${row}`] = { v: r.name }
        cells[`C${row}`] = { v: r.sku }
        cells[`D${row}`] = { v: r.description }
        cells[`E${row}`] = { v: r.qty }
        cells[`F${row}`] = { v: r.price }
        cells[`G${row}`] = { v: r.discount }
        cells[`H${row}`] = { v: Number(subtotal(r)) }
        cells[`I${row}`] = { v: r.remark }
      })
      await saveBomSnapshot(props.solutionId, { snapshot: { cells, sheet_name: 'BOM' } })
    }
    dirty.value = false
    showToast('BOM 已保存', 'success')
  } catch (e: any) {
    showToast('保存失败: ' + (e.detail || e.message), 'error')
  }
}

function exportXlsx() {
  if (props.quotationId) {
    const token = localStorage.getItem('token') || ''
    window.open(`/product-db/api/quotations/${props.quotationId}/export-xlsx?token=${token}`, '_blank')
  } else if (props.solutionId) {
    window.open(bomExportUrl(props.solutionId), '_blank')
  }
}

onMounted(loadSnapshot)
</script>

<style scoped>
.bom-table-wrap {
  max-height: 500px; overflow: auto; border: 1px solid var(--color-border);
  border-radius: 6px;
}
.bom-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.bom-table th { background: var(--color-hover); padding: 6px 8px; font-size: 11px; text-transform: uppercase; letter-spacing: .5px; position: sticky; top: 0; z-index: 1; }
.bom-table td { padding: 4px 6px; border-top: 1px solid var(--color-border); }
.bom-table input { border: 1px solid transparent; padding: 4px 6px; border-radius: 4px; font-size: 13px; background: transparent; }
.bom-table input:focus { border-color: var(--color-accent); background: #fff; outline: none; }
.bom-table tfoot td { border-top: 2px solid var(--color-border); }
</style>
