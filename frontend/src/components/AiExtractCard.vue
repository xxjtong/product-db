<template>
  <div class="card mt-16" @paste="onPaste">
    <h3 style="margin:0 0 8px">AI 智能录入</h3>
    <p style="margin:0 0 12px;font-size:13px;color:var(--color-text-secondary)">粘贴产品URL、规格文本，或上传/粘贴图片，AI自动提取产品信息填入表单</p>
    <div style="display:flex;gap:8px;align-items:flex-start">
      <textarea v-model="textInput" rows="2" placeholder="粘贴产品URL或规格文本…" style="flex:1;box-sizing:border-box;font-size:13px" @keyup.ctrl.enter="onFetch" />
      <button class="btn-primary btn-sm" @click="onFetch" :disabled="fetching || !textInput.trim()" style="white-space:nowrap">
        {{ fetching ? '提取中...' : 'AI 识别' }}
      </button>
    </div>
    <div class="ai-drop" :class="{ 'ai-drop-active': dragOver }"
      @dragover.prevent="dragOver = true" @dragleave="dragOver = false" @drop.prevent="onDrop">
      <div v-if="imagePreview" style="margin-bottom:8px">
        <img :src="imagePreview" style="max-width:200px;max-height:150px;border-radius:4px;border:1px solid var(--color-border)" />
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        粘贴图片、拖拽文件到此处 或
        <label class="btn-secondary btn-sm btn-label">选择文件
          <input type="file" accept=".pdf,.docx,.txt,.csv,.jpg,.jpeg,.png,.webp,.bmp" style="display:none" @change="onFileSelect" />
        </label>
      </div>
    </div>
    <div v-if="preview" ref="previewRef" style="margin-top:12px;padding:12px;background:white;border-radius:4px">
      <div class="section-header"><strong style="margin:0">提取结果预览（可编辑）</strong></div>
      <table class="data-table" style="margin-top:8px">
        <thead><tr><th>字段</th><th>提取值</th></tr></thead>
        <tbody>
          <tr v-for="key in displayFields" :key="key">
            <td style="font-weight:500;white-space:nowrap;vertical-align:top" class="text-sm">{{ fieldLabels[key] || key.replace(/_/g,' ') }}</td>
            <td>
              <textarea v-if="isSimpleList(editFields[key]) || (key === 'specs' && isComplexVal(editFields[key]))"
                :value="isSimpleList(editFields[key]) ? fmtListDetail(editFields[key]) : fmtSpecs(editFields[key])"
                @change="editFields[key] = parseVal(($event.target as HTMLTextAreaElement).value)"
                :rows="Math.min(12, Math.max(3, (isSimpleList(editFields[key]) ? fmtListDetail(editFields[key]) : fmtSpecs(editFields[key])).split('\n').length))"
                style="width:100%;font-size:11px;font-family:monospace;box-sizing:border-box" placeholder="未提取" />
              <input v-else v-model="editFields[key]" style="width:100%;font-size:12px" placeholder="未提取" />
            </td>
          </tr>
        </tbody>
      </table>
      <div class="flex gap-8" style="margin-top:8px">
        <button class="btn-primary btn-sm" @click="onFill">填入表单</button>
        <button class="btn-secondary btn-sm" @click="preview = null">清除</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useFileDrop } from '../composables/useFileDrop'

const emit = defineEmits<{ fill: [data: Record<string, any>] }>()

const textInput = ref('')
const fetching = ref(false)
const preview = ref<any>(null)
const editFields = ref<Record<string, any>>({})
const { dragOver, imagePreview, onFileSelect, onDrop, onPaste, clearFiles } = useFileDrop(doFileExtract)
const previewRef = ref<HTMLElement | null>(null)

function scrollToPreview() {
  nextTick(() => previewRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
}

const displayFields = computed(() => [...Object.keys(editFields.value)])

function isComplexVal(v: any) { return v !== null && typeof v === 'object' }
function isSimpleList(v: any) { return Array.isArray(v) && v.length > 0 && typeof v[0] === 'object' }
function fmtSpecs(v: any) { if (!v || typeof v !== 'object') return String(v); return Object.entries(v).map(([k,val]) => k + ': ' + (val ?? '')).join('\n') }
function fmtListDetail(v: any): string {
  if (!Array.isArray(v)) return String(v)
  return v.map((x: any) => {
    const name = x.name || x.metric_name || x.interface_name || ''
    const parts = [name]
    if (x.details) parts.push(x.details)
    if (x.voltage_range) parts.push(x.voltage_range)
    if (x.measure_range) parts.push(x.measure_range)
    if (x.accuracy) parts.push(x.accuracy)
    if (x.direction) parts.push(x.direction)
    if (x.quantity) parts.push('×'+x.quantity)
    if (x.description) parts.push(x.description)
    return parts.join(' | ')
  }).join('\n')
}
function parseVal(s: string) { try { return JSON.parse(s) } catch { return s } }

const fieldLabels: Record<string, string> = {
  name: '产品名', model: '型号', category_slug: '品类', manufacturer_name: '厂商',
  base_price: '价格', cost_price: '成本', description: '功能描述', product_url: '产品URL',
  comm_methods: '通讯方式', comm_protocols: '协议', power_supplies: '供电',
  sensor_capabilities: '传感能力', specs: '规格参数', sku: 'SKU',
  dimensions: '尺寸', weight: '重量', ip_rating: '防护等级',
  operating_temp: '工作温度', installation: '安装方式', battery_life: '电池续航',
  hardware_interfaces: '硬件接口', filename: '文件名',
}

// --- File/image upload ---
async function doFileExtract(file: File) {
  fetching.value = true
  try {
    const fd = new FormData(); fd.append('file', file)
    const token = localStorage.getItem('token')
    const res = await fetch('/product-db/api/products/ai-fetch-file', {
      method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd,
    })
    if (!res.ok) throw new Error((await res.json()).detail || 'Extraction failed')
    const data = await res.json()
    let raw = JSON.parse(JSON.stringify(data.fetched))
    if (raw.specs && typeof raw.specs === 'object') {
      const keyMap: Record<string,string> = { ip_rating:'防护等级', dimensions_mm:'尺寸', dimensions:'尺寸', weight_g:'重量', weight:'重量', operating_temp:'工作温度', operating_temperature:'工作温度', working_temperature:'工作温度', installation:'安装方式', color:'颜色', material:'材质', battery_life:'电池续航', power_supply:'供电方式', protocol:'通讯协议', communication:'通讯方式' }
      const translated: Record<string,any> = {}
      for (const [k, v] of Object.entries(raw.specs)) { translated[keyMap[k] || k] = v }
      raw.specs = translated
    }
    editFields.value = raw
    preview.value = data.fetched; scrollToPreview()
  } catch (err: any) {
    alert(err.message || '提取失败')
  }
  fetching.value = false
}

// --- Text/URL extraction ---
async function onFetch() {
  let input = textInput.value.trim()
  if (!input) return
  // Auto-prefix bare www URLs
  if (/^www\..+\..+/.test(input)) input = 'https://' + input
  const isUrl = /^https?:\/\//.test(input)
  fetching.value = true
  try {
    const token = localStorage.getItem('token')
    const resp = await fetch('/product-db/api/products/ai-fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(isUrl ? { url: input } : { text: input }),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || 'AI提取失败')
    if (!data.fetched || typeof data.fetched !== 'object') throw new Error('提取结果为空')
    preview.value = data.fetched; scrollToPreview()
    editFields.value = JSON.parse(JSON.stringify(data.fetched))
  } catch (err: any) {
    alert(err.message || 'AI提取失败')
  } finally {
    fetching.value = false
  }
}

// --- Fill form ---
function onFill() {
  if (!editFields.value || !Object.keys(editFields.value).length) return
  const raw = JSON.parse(JSON.stringify(editFields.value))
  // Parse specs from text format if needed
  try {
    if (raw.specs && typeof raw.specs === 'string') {
      const parsed: Record<string,any> = {}
      for (const line of raw.specs.split('\n')) {
        const idx = line.indexOf(':')
        if (idx > 0) parsed[line.substring(0, idx).trim()] = line.substring(idx + 1).trim()
      }
      if (Object.keys(parsed).length) raw.specs = parsed
    }
  } catch {}
  emit('fill', raw)
  preview.value = null
}

async function fetchFromUrl(url: string) {
  textInput.value = url
  await onFetch()
}

defineExpose({ fetchFromUrl })
</script>
