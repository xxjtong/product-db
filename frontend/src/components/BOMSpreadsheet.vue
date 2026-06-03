<template>
  <div class="bom-spreadsheet">
    <div class="flex gap-8 items-center mb-12">
      <button class="btn-secondary btn-sm" @click="loadSnapshot"><RefreshCwIcon style="width:14px;height:14px" />重新加载</button>
      <button class="btn-primary btn-sm" @click="save"><SaveIcon style="width:14px;height:14px" />保存</button>
      <button class="btn-secondary btn-sm" @click="exportXlsx"><DownloadIcon style="width:14px;height:14px" />导出 xlsx</button>
      <button class="btn-secondary btn-sm" @click="saveAsTemplate"><CopyIcon style="width:14px;height:14px" />另存为模板</button>
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
            <th style="width:60px">数量</th>
            <th style="width:80px">单价</th>
            <th style="width:60px">折扣%</th>
            <th style="width:80px">小计</th>
            <th style="width:80px">备注</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td class="text-center text-muted">{{ i + 1 }}</td>
            <td><input v-model="row.name" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model="row.sku" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model.number="row.qty" type="number" min="0" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model.number="row.price" type="number" min="0" style="width:100%" @input="dirty = true" /></td>
            <td><input v-model.number="row.discount" type="number" min="0" max="100" style="width:100%" @input="dirty = true" /></td>
            <td class="font-mono text-right">{{ subtotal(row) }}</td>
            <td><input v-model="row.remark" style="width:100%" @input="dirty = true" /></td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td colspan="6" class="text-right" style="font-weight:600">合计</td>
            <td class="font-mono text-right" style="font-weight:700">{{ totalPrice }}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { RefreshCwIcon, SaveIcon, DownloadIcon, CopyIcon } from 'lucide-vue-next'
import { fetchBomSnapshot, saveBomSnapshot, bomExportUrl, saveBomAsTemplate } from '../api'

const props = defineProps<{ solutionId: number }>()

interface BomRow { name: string; sku: string; qty: number; price: number; discount: number; remark: string }
const rows = ref<BomRow[]>([])
const loading = ref(true)
const dirty = ref(false)

function subtotal(r: BomRow): string {
  return (r.qty * r.price * (r.discount / 100)).toFixed(0)
}

const totalPrice = computed(() => {
  return rows.value.reduce((sum, r) => sum + r.qty * r.price * (r.discount / 100), 0).toFixed(0)
})

async function loadSnapshot() {
  loading.value = true
  try {
    const res = await fetchBomSnapshot(props.solutionId)
    const cells = res.bom_snapshot?.snapshot?.cells || {}
    // Parse cells into rows
    const rowMap: Record<number, BomRow> = {}
    for (const [ref, cell] of Object.entries(cells)) {
      const c = cell as any
      const m = ref.match(/^([A-Z])(\d+)$/)
      if (!m) continue
      const col = m[1]
      const rowNum = parseInt(m[2])
      if (!rowMap[rowNum]) rowMap[rowNum] = { name: '', sku: '', qty: 1, price: 0, discount: 100, remark: '' }
      const v = c.v ?? ''
      if (col === 'A') rowMap[rowNum].name = String(v)
      else if (col === 'B') rowMap[rowNum].name = String(v) // merge B into name if A is sequence number
      else if (col === 'C') rowMap[rowNum].sku = String(v)
      else if (col === 'D') rowMap[rowNum].qty = Number(v) || 1
      else if (col === 'E') rowMap[rowNum].price = Number(v) || 0
      else if (col === 'F') {/* subtotal, computed */}
      else if (col === 'G') rowMap[rowNum].discount = Number(v) || 100
      else if (col === 'H') rowMap[rowNum].remark = String(v)
    }
    rows.value = Object.keys(rowMap).sort((a,b) => Number(a)-Number(b)).map(k => rowMap[Number(k)])
    dirty.value = false
  } catch (e: any) {
    console.warn('BOM load failed:', e)
  }
  loading.value = false
}

async function save() {
  try {
    // Convert rows back to snapshot format
    const cells: Record<string, any> = {}
    rows.value.forEach((r, i) => {
      const row = i + 1
      cells[`A${row}`] = { v: i + 1 }
      cells[`B${row}`] = { v: r.name }
      cells[`C${row}`] = { v: r.sku }
      cells[`D${row}`] = { v: r.qty }
      cells[`E${row}`] = { v: r.price }
      cells[`F${row}`] = { v: Number(subtotal(r)) }
      cells[`G${row}`] = { v: r.discount }
      cells[`H${row}`] = { v: r.remark }
    })
    await saveBomSnapshot(props.solutionId, { snapshot: { cells, sheet_name: 'BOM' } })
    dirty.value = false
    alert('BOM 已保存')
  } catch (e: any) {
    alert('保存失败: ' + (e.detail || e.message))
  }
}

function exportXlsx() {
  window.open(bomExportUrl(props.solutionId), '_blank')
}

async function saveAsTemplate() {
  const name = prompt('模板名称:')
  if (!name) return
  try {
    const cells: Record<string, any> = {}
    rows.value.forEach((r, i) => {
      const row = i + 1
      cells[`A${row}`] = { v: i + 1 }
      cells[`B${row}`] = { v: r.name }
      cells[`C${row}`] = { v: r.sku }
      cells[`D${row}`] = { v: r.qty }
      cells[`E${row}`] = { v: r.price }
      cells[`G${row}`] = { v: r.discount }
      cells[`H${row}`] = { v: r.remark }
    })
    await saveBomAsTemplate(props.solutionId, { name, snapshot: { cells, sheet_name: 'BOM' } })
    alert('模板已保存')
  } catch (e: any) {
    alert('保存模板失败')
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
