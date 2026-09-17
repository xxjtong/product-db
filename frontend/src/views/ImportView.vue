<template>
  <PageHeader title="Excel 导入" />
  <div class="card">
    <div class="form-group" style="margin-bottom:16px">
      <label>选择 Excel 文件</label>
      <input type="file" accept=".xlsx,.xls" @change="onFileSelect" />
    </div>

    <div v-if="loading">解析中...</div>

    <div v-if="headers.length && !loading">
      <h3 style="margin:12px 0 8px">列映射 ({{ rows.length }} 行)</h3>
      <table class="data-table" style="overflow-x:auto;display:block">
        <thead>
          <tr>
            <th v-for="(h, i) in headers" :key="i">
              <select v-model="mapping[i]" style="width:100px;font-size:12px">
                <option value="">忽略</option>
                <option v-for="f in fields" :key="f.value" :value="f.value">{{ f.label }}</option>
              </select>
              <div style="font-size:10px;color:var(--color-text-secondary)">{{ h }}</div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, ri) in previewRows" :key="ri">
            <td v-for="(cell, ci) in row" :key="ci" style="font-size:12px;white-space:nowrap;max-width:150px;overflow:hidden;text-overflow:ellipsis">{{ cell }}</td>
          </tr>
        </tbody>
      </table>

      <div style="margin-top:12px;display:flex;gap:8px">
        <button class="btn-primary" @click="doImport" :disabled="importing">
          {{ importing ? '导入中...' : `确认导入 ${rows.length} 条` }}
        </button>
        <button class="btn-secondary" @click="autoMap">自动映射</button>
      </div>
      <p v-if="result" class="text-sm" style="margin-top:8px;color:var(--color-success)">成功导入 {{ result.imported }} 条</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, inject } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import { readErrorDetail } from '../api'

const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const fields = [
  { label: '产品名称', value: 'name' }, { label: '型号', value: 'model' },
  { label: 'SKU', value: 'sku' }, { label: '品类', value: 'category' },
  { label: '厂商', value: 'manufacturer' }, { label: '价格', value: 'price' },
  { label: '成本', value: 'cost' }, { label: '描述', value: 'description' },
  { label: '产品URL', value: 'product_url' },
]

const headers = ref<string[]>([])
const rows = ref<any[]>([])
const previewRows = ref<any[]>([])
const mapping = ref<Record<number, string>>({})
const loading = ref(false)
const importing = ref(false)
const result = ref<any>(null)

async function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  loading.value = true; result.value = null
  const formData = new FormData(); formData.append('file', file)
  try {
    // 注意：这里的变量名不能叫 headers —— 会遮蔽上面的 headers ref（历史 bug：
    // `headers.value = res.headers` 写到了局部对象上，导致映射表永不渲染）
    const authHeaders: Record<string,string> = {}
    const token = localStorage.getItem('token')
    if (token) authHeaders['Authorization'] = `Bearer ${token}`
    const res = await fetch('/product-db/api/products/import-preview', { method: 'POST', body: formData, headers: authHeaders })
    if (!res.ok) throw new Error(await readErrorDetail(res))
    const data = await res.json()
    headers.value = data.headers ?? []
    rows.value = data.rows ?? []
    previewRows.value = rows.value.slice(0, 10)
    mapping.value = {}
    autoMap()
  } catch (e: any) {
    // 失败必须清空上一次的预览状态：否则旧的列映射表会留在页面上、「确认导入 N 条」
    // 仍可点，用户会误把上一个文件的数据再导一遍（浏览器走查发现的遗留问题）
    headers.value = []
    rows.value = []
    previewRows.value = []
    mapping.value = {}
    showToast(e.message || '解析失败', 'error')
  }
  loading.value = false
}

function autoMap() {
  mapping.value = {}
  for (let i = 0; i < headers.value.length; i++) {
    const h = headers.value[i].toLowerCase()
    if (h.includes('名称') || h.includes('name')) mapping.value[i] = 'name'
    else if (h.includes('型号') || h.includes('model')) mapping.value[i] = 'model'
    else if (h.includes('sku')) mapping.value[i] = 'sku'
    else if (h.includes('品类') || h.includes('分类') || h.includes('category')) mapping.value[i] = 'category'
    else if (h.includes('厂商') || h.includes('品牌') || h.includes('manufacturer') || h.includes('brand')) mapping.value[i] = 'manufacturer'
    else if (h.includes('价格') || h.includes('price') || h.includes('售价')) mapping.value[i] = 'price'
    else if (h.includes('成本') || h.includes('cost')) mapping.value[i] = 'cost'
    else if (h.includes('描述') || h.includes('desc')) mapping.value[i] = 'description'
    else if (h.includes('url') || h.includes('链接')) mapping.value[i] = 'product_url'
  }
}

async function doImport() {
  importing.value = true
  try {
    const h: Record<string,string> = { 'Content-Type': 'application/json' }
    const t = localStorage.getItem('token')
    if (t) h['Authorization'] = `Bearer ${t}`
    const res = await fetch('/product-db/api/products/import-confirm', {
      method: 'POST', headers: h,
      body: JSON.stringify({ mapping: mapping.value, rows: rows.value }),
    })
    if (!res.ok) throw new Error(await readErrorDetail(res))
    result.value = await res.json()
    showToast(`成功导入 ${result.value?.imported ?? 0} 条`, 'success')
  } catch (e: any) { showToast(e.message || '导入失败', 'error') }
  importing.value = false
}
</script>