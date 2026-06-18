<template>
  <PageHeader :title="isEdit ? '编辑产品' : '新增产品'" :breadcrumb="[{ label: '产品列表', to: '/products' }, { label: isEdit ? '编辑产品' : '新增产品', to: '' }]">
    <button class="btn-secondary" @click="scrollToAi">AI 智能录入</button>
    <button class="btn-secondary" @click="$router.back()">取消</button>
    <button class="btn-primary" @click="save">保存</button>
  </PageHeader>

  <div class="card" v-if="loaded">
    <!-- Basic info -->
    <div class="form-grid form-grid-3">
      <div class="form-group"><label>产品名称 *</label><input v-model="form.name" /></div>
      <div class="form-group"><label>型号 *</label><input v-model="form.model" placeholder="e.g. EG71" /></div>
      <div class="form-group"><label>SKU</label><input v-model="form.sku" /></div>
      <div class="form-group">
        <label>厂商 *</label>
        <select v-model="form.manufacturer_id">
          <option :value="null">—</option>
          <option v-for="m in manufacturers" :key="m.id" :value="m.id">{{ m.name }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>供应商</label>
        <select v-model="form.supplier_id">
          <option :value="null">—</option>
          <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="form-group"><label>价格 *</label><input v-model.number="form.base_price" type="number" step="0.01" /></div>
      <div class="form-group"><label>成本价</label><input v-model.number="form.cost_price" type="number" step="0.01" /></div>
      <div class="form-group"><label>状态</label>
        <select v-model="form.status"><option value="active">在售</option><option value="discontinued">停售</option><option value="planned">规划中</option></select>
      </div>
      <div class="form-group full">
        <label>产品URL</label>
        <div class="form-row-sm" style="display:flex;gap:8px">
          <input v-model="form.product_url" placeholder="https://..." style="flex:1" />
          <button v-if="isValidUrl(form.product_url)" class="btn-primary btn-sm" @click="aiFetchFromUrl" style="white-space:nowrap">AI 识别</button>
        </div>
      </div>
      <div class="form-group full">
        <label>品类 *</label>
        <div class="category-tags">
          <span v-for="c in flatCategories" :key="c.id"
                :class="['filter-tag', { active: form.category_ids.includes(c.id) }]"
                @click="selectCategory(c.id)"
                >
            {{ c.name }}
          </span>
        </div>
      </div>
    </div>

    <!-- Images -->
    <h3>产品图片</h3>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">
      <div v-for="(img, idx) in form.images" :key="idx" style="position:relative">
        <img :src="img.url" style="width:64px;height:64px;object-fit:cover;border-radius:4px;border:1px solid var(--color-border)" />
        <button class="btn-icon btn-sm" style="position:absolute;top:1px;right:1px;background:var(--color-surface);padding:2px" @click="form.images.splice(idx, 1)"><XIcon style="width:10px;height:10px" /></button>
      </div>
      <!-- Live preview of typed URL -->
      <div v-if="imagePreviewUrl && !form.images.some((i: any) => i.url === imagePreviewUrl)" style="position:relative;opacity:0.6">
        <img :src="imagePreviewUrl" style="width:64px;height:64px;object-fit:cover;border-radius:4px;border:1px dashed var(--color-accent)" />
      </div>
    </div>
    <div class="form-row-sm" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
      <label class="btn-secondary btn-sm btn-label" style="gap:4px">
        <UploadIcon style="width:14px;height:14px" />上传
        <input type="file" accept="image/*" style="display:none" @change="onFileSelect" />
      </label>
      <input v-model="imageUrlInput" style="flex:1;min-width:180px;font-size:13px" placeholder="粘贴图片URL" @keyup.enter="onAddImageUrl" @paste="onPasteImage" />
      <button class="btn-secondary btn-sm" @click="onAddImageUrl" :disabled="!isValidUrl(imageUrlInput)">添加URL</button>
      <button class="btn-secondary btn-sm" @click="onDownloadImage" :disabled="imageDownloading || !isValidUrl(imageUrlInput)">下载到本地</button>
    </div>

    <hr style="margin:12px 0;border:none;border-top:1px solid var(--color-border)" />
    <!-- Comm Methods -->
    <div class="section-header"><h3 class="m-0">通讯方式</h3><button class="btn-primary btn-sm" @click="form.comm_methods.push({ method_id: null, details: '' })">+ 添加</button></div>
    <table class="data-table" style="margin-bottom:16px">
      <thead><tr><th>方式</th><th>详情</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(cm, idx) in form.comm_methods" :key="idx">
          <td>
            <select v-model="cm.method_id" style="width:120px">
              <option v-for="m in commMethods" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
          </td>
          <td><input v-model="cm.details" placeholder="e.g. CN470 8通道" style="width:100%" /></td>
          <td><button class="btn-icon btn-sm" @click="form.comm_methods.splice(idx, 1)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
        </tr>
      </tbody>
    </table>

    <!-- Comm Protocols -->
    <div class="section-header"><h3 class="m-0">通讯协议</h3><button class="btn-primary btn-sm" @click="form.comm_protocols.push({ protocol_id: null, direction: 'both' })">+ 添加</button></div>
    <table class="data-table" style="margin-bottom:16px">
      <thead><tr><th>协议</th><th>方向</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(cp, idx) in form.comm_protocols" :key="idx">
          <td>
            <select v-model="cp.protocol_id" style="width:120px">
              <option v-for="p in commProtocols" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </td>
          <td>
            <select v-model="cp.direction" style="width:100px">
              <option value="both">双向</option><option value="acquisition">采集(下行)</option><option value="forwarding">转发(上行)</option>
            </select>
          </td>
          <td><button class="btn-icon btn-sm" @click="form.comm_protocols.splice(idx, 1)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
        </tr>
      </tbody>
    </table>

    <!-- Power Supplies -->
    <div class="section-header"><h3 class="m-0">供电方式</h3><button class="btn-primary btn-sm" @click="form.power_supplies.push({ power_id: null, voltage_range: '', battery_life: '' })">+ 添加</button></div>
    <table class="data-table" style="margin-bottom:16px">
      <thead><tr><th>方式</th><th>电压/规格</th><th>续航</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(ps, idx) in form.power_supplies" :key="idx">
          <td>
            <select v-model="ps.power_id" style="width:100px">
              <option v-for="p in powerSupplies" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </td>
          <td><input v-model="ps.voltage_range" placeholder="e.g. 9-24V DC" style="width:100%" /></td>
          <td><input v-model="ps.battery_life" placeholder="e.g. 5年" style="width:100%" /></td>
          <td><button class="btn-icon btn-sm" @click="form.power_supplies.splice(idx, 1)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
        </tr>
      </tbody>
    </table>

    <!-- Hardware Interfaces -->
    <div class="section-header"><h3 class="m-0">硬件接口</h3><button class="btn-primary btn-sm" @click="form.hardware_interfaces.push({ interface_name: '', quantity: 1, description: '' })">+ 添加</button></div>
    <table class="data-table" style="margin-bottom:16px">
      <thead><tr><th>接口名称</th><th>数量</th><th>描述</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(hi, idx) in form.hardware_interfaces" :key="idx">
          <td><input v-model="hi.interface_name" placeholder="e.g. RS485" style="width:100%" /></td>
          <td><input v-model.number="hi.quantity" type="number" min="1" style="width:60px" /></td>
          <td><input v-model="hi.description" placeholder="e.g. 波特率1200~115200" style="width:100%" /></td>
          <td><button class="btn-icon btn-sm" @click="form.hardware_interfaces.splice(idx, 1)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
        </tr>
      </tbody>
    </table>

    <!-- Sensor Capabilities -->
    <div class="section-header"><h3 class="m-0">传感能力</h3><button class="btn-primary btn-sm" @click="form.sensor_capabilities.push({ metric_id: null, measure_range: '', accuracy: '', resolution: '' })">+ 添加</button></div>
    <table class="data-table" style="margin-bottom:16px">
      <thead><tr><th>指标</th><th>量程</th><th>精度</th><th>分辨率</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(sc, idx) in form.sensor_capabilities" :key="idx">
          <td>
            <select v-model="sc.metric_id" style="width:100px">
              <option v-for="m in sensorMetrics" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
          </td>
          <td><input v-model="sc.measure_range" :placeholder="getMetricPlaceholder(sc.metric_id, 'range')" style="width:100%" /></td>
          <td><input v-model="sc.accuracy" :placeholder="getMetricPlaceholder(sc.metric_id, 'accuracy')" style="width:100%" /></td>
          <td><input v-model="sc.resolution" :placeholder="getMetricPlaceholder(sc.metric_id, 'resolution')" style="width:100%" /></td>
          <td><button class="btn-icon btn-sm" @click="form.sensor_capabilities.splice(idx, 1)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
        </tr>
      </tbody>
    </table>

    <!-- Dynamic spec fields -->
    <div v-if="specDefs.length">
      <h3>规格参数</h3>
      <div class="form-grid form-grid-3">
        <div v-for="sd in specDefs" :key="sd.id" class="form-group">
          <label>{{ sd.display_name }} <span v-if="sd.unit" class="text-muted">({{ sd.unit }})</span></label>
          <input v-if="sd.spec_type === 'string'" v-model="form.specs[sd.spec_key]" />
          <input v-else-if="sd.spec_type === 'number'" v-model.number="form.specs[sd.spec_key]" type="number" step="any" />
          <input v-else-if="sd.spec_type === 'boolean'" type="checkbox" v-model="form.specs[sd.spec_key]" />
          <select v-else-if="sd.spec_type === 'enum' && sd.options" v-model="form.specs[sd.spec_key]">
            <option :value="null">—</option>
            <option v-for="opt in sd.options" :key="opt" :value="opt">{{ opt }}</option>
          </select>
          <input v-else v-model="form.specs[sd.spec_key]" />
        </div>
      </div>
    </div>
    <!-- Generic specs editor table -->
    <div v-if="form.specs && !specDefs.length">
      <div class="section-header">
        <h3 class="m-0">规格参数</h3>
        <button class="btn-primary btn-sm" @click="addSpecRow">+ 添加</button>
      </div>
      <table class="data-table" style="margin-bottom:8px">
        <thead><tr><th>参数名</th><th>参数值</th><th style="width:50px"></th></tr></thead>
        <tbody>
          <tr v-for="(val, key) in form.specs" :key="key">
            <td><input :value="String(key)" @change="renameSpecKey(String(key), ($event.target as HTMLInputElement).value)" style="width:100%;font-size:12px;font-family:monospace" /></td>
            <td>
              <span v-if="typeof val === 'boolean'">
                <input type="checkbox" :checked="val" @change="form.specs[key] = ($event.target as HTMLInputElement).checked" />
              </span>
              <input v-else v-model="form.specs[key]" class="input-sm" placeholder="参数值" />
            </td>
            <td><button class="btn-icon btn-sm" @click="deleteSpecKey(String(key))" title="删除"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="form-grid" style="margin-top:12px">
      <div class="form-group full">
        <label>功能描述 *</label>
        <textarea v-model="form.description" rows="3" />
      </div>
      <div class="form-group full">
        <label>备注</label>
        <textarea v-model="form.remark" rows="3" />
      </div>
    </div>
  </div>

  <div class="card mt-16">
    <DependencyEditor :productId="Number(route.params.id) || 0" />
  </div>
  <ProductFiles v-if="route.params.id" :productId="Number(route.params.id)" class="mt-16" />

  <div v-if="loaded" ref="aiCardRef"><AiExtractCard ref="aiCard" @fill="onAiFill" /></div>
  <div v-else style="text-align:center;padding:48px;color:var(--color-text-secondary)">加载中...</div>


</template>

<script setup lang="ts">
import { ref, computed, onMounted, inject, watch, nextTick } from 'vue'
import ProductFiles from '../components/ProductFiles.vue'
import DependencyEditor from '../components/DependencyEditor.vue'
import AiExtractCard from '../components/AiExtractCard.vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { UploadIcon, DownloadIcon, XIcon, Trash2Icon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { flattenTree } from '../utils/markdown'
import { fetchCategories, fetchSuppliers, fetchProducts, fetchProduct, createProduct, updateProduct, uploadProductImage, downloadProductImage,
  fetchCommMethods, fetchCommProtocols, fetchPowerSupplies, fetchSensorMetrics, fetchManufacturers, fetchSpecDefinitions } from '../api'

const route = useRoute()
const router = useRouter()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const isEdit = computed(() => !!route.params.id)
const loaded = ref(false)
const dirty = ref(false)

// Warn before leaving with unsaved changes
onBeforeRouteLeave((_to, _from, next) => {
  if (dirty.value && !window.confirm('有未保存的修改，确定离开吗？')) {
    next(false)
  } else {
    next()
  }
})

// Track form changes


const categories = ref<any[]>([])
const flatCategories = ref<any[]>([])
const suppliers = ref<any[]>([])
const manufacturers = ref<any[]>([])
const commMethods = ref<any[]>([])
const commProtocols = ref<any[]>([])
const powerSupplies = ref<any[]>([])
const sensorMetrics = ref<any[]>([])
function getMetricPlaceholder(metricId: any, field: string): string {
  if (!metricId) return ''
  const m = sensorMetrics.value.find((x: any) => x.id == metricId)
  if (!m) return ''
  if (field === 'accuracy') return m.accuracy || ''
  if (field === 'resolution') return m.resolution || ''
  if (field === 'range') return m.measure_range || ''
  return ''
}
const specDefs = ref<any[]>([])
function addSpecRow() {
  const key = 'new_' + Date.now()
  form.value.specs[key] = ''
}
function renameSpecKey(oldKey: string, newKey: string) {
  if (!newKey.trim() || newKey === oldKey || newKey in form.value.specs) return
  form.value.specs[newKey.trim()] = form.value.specs[oldKey]
  delete form.value.specs[oldKey]
}
function deleteSpecKey(key: string) { delete form.value.specs[key] }

const imageUrlInput = ref('')
const imageDownloading = ref(false)
const imagePreviewUrl = computed(() => {
  const u = imageUrlInput.value.trim()
  return /^https?:\/\/.+\.(jpg|jpeg|png|gif|webp|svg|bmp)(\?.*)?$/i.test(u) ? u : ''
})

function onAiFill(p: Record<string, any>) {
  try {
  if (!p || !Object.keys(p).length) return

  // Basic fields
  if (p.name) form.value.name = p.name
  if (p.model) form.value.model = p.model
  if (p.description) form.value.description = p.description
  if (p.base_price) form.value.base_price = p.base_price

  // Category lookup by slug
  if (p.category_slug) {
    const cat = flatCategories.value.find((c: any) => c.slug === p.category_slug)
    if (cat) {
      form.value.category_id = cat.id
      onCategoryChange()
    }
  }

  // Manufacturer lookup by name
  if (p.manufacturer_name) {
    const mfg = manufacturers.value.find((m: any) =>
      m.name.toLowerCase() === p.manufacturer_name.toLowerCase() ||
      m.name.toLowerCase().includes(p.manufacturer_name.toLowerCase())
    )
    if (mfg) form.value.manufacturer_id = mfg.id
  }

  // Comm methods lookup by name
  if (p.comm_methods?.length) {
    form.value.comm_methods = p.comm_methods.map((cm: any) => {
      const found = commMethods.value.find((m: any) => m.name.toLowerCase() === (cm.name || '').toLowerCase())
      return { method_id: found?.id || null, details: cm.details || '' }
    })
  }

  // Comm protocols lookup by name
  if (p.comm_protocols?.length) {
    form.value.comm_protocols = p.comm_protocols.map((cp: any) => {
      const found = commProtocols.value.find((pr: any) => pr.name.toLowerCase() === (cp.name || '').toLowerCase())
      return { protocol_id: found?.id || null, direction: cp.direction || 'both' }
    })
  }

  // Power supplies lookup by name
  if (p.power_supplies?.length) {
    form.value.power_supplies = p.power_supplies.map((ps: any) => {
      const found = powerSupplies.value.find((pw: any) => pw.name.toLowerCase() === (ps.name || '').toLowerCase())
      return { power_id: found?.id || null, voltage_range: ps.voltage_range || '', battery_life: ps.battery_life || '' }
    })
  }

  // Hardware interfaces
  if (p.hardware_interfaces?.length) {
    form.value.hardware_interfaces = p.hardware_interfaces.map((hi: any) => ({
      interface_name: hi.interface_name || '', quantity: hi.quantity || 1, description: hi.description || ''
    }))
  }

  // Sensor capabilities lookup by metric name
  if (p.sensor_capabilities?.length) {
    form.value.sensor_capabilities = p.sensor_capabilities.map((sc: any) => {
      const found = sensorMetrics.value.find((sm: any) => sm.name.toLowerCase() === (sc.metric_name || '').toLowerCase())
      return { metric_id: found?.id || null, measure_range: sc.measure_range || '', accuracy: sc.accuracy || '', resolution: sc.resolution || '' }
    })
  }

  // Specs — handle both object and key:value text format
  if (p.specs) {
    if (typeof p.specs === 'object') {
      form.value.specs = { ...p.specs }
    } else if (typeof p.specs === 'string') {
      const parsed: Record<string,any> = {}
      for (const line of p.specs.split('\n')) {
        const idx = line.indexOf(':')
        if (idx > 0) parsed[line.substring(0, idx).trim()] = line.substring(idx + 1).trim()
      }
      if (Object.keys(parsed).length) form.value.specs = parsed
    }
  }

  document.querySelector('.page-header')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  showToast('已填入表单，请检查修改后保存', 'success')
  } catch (err: any) {
    showToast(err.message || '填入表单失败', 'error')
  }
}

const form = ref<any>({
  name: '', model: '', sku: '', category_id: null, category_ids: [] as number[], manufacturer_id: null, supplier_id: null,
  base_price: 0, cost_price: 0, description: '', status: 'active', parent_id: null,
  comm_methods: [], comm_protocols: [], power_supplies: [],
  hardware_interfaces: [], sensor_capabilities: [], images: [],
  image_url: '', product_url: '', remark: '',
  specs: {},
})

// Track form changes for unsaved warning
watch(form, () => { if (loaded.value) dirty.value = true }, { deep: true })

async function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await uploadProductImage(fd)
    if (res.url) {
      form.value.images.push({ url: res.url, is_primary: form.value.images.length === 0, sort_order: form.value.images.length })
    }
  } catch (err: any) { showToast(err.message, 'error') }
  ;(e.target as HTMLInputElement).value = ''
}

const aiCardRef = ref<HTMLElement | null>(null)
const aiCard = ref<InstanceType<typeof AiExtractCard> | null>(null)
function scrollToAi() { aiCardRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
async function aiFetchFromUrl() {
  const url = form.value.product_url?.trim()
  if (!url) return
  scrollToAi()
  await aiCard.value?.fetchFromUrl(url)
}

function isValidUrl(s: string) { return /^https?:\/\/.+/.test(s.trim()) || /^www\..+\..+/.test(s.trim()) }

function onAddImageUrl() {
  const url = imageUrlInput.value.trim()
  if (!url || !isValidUrl(url)) return
  // Don't add duplicate
  if (form.value.images.some((i: any) => i.url === url)) { showToast('URL已存在', 'error'); return }
  form.value.images.push({ url, is_primary: form.value.images.length === 0, sort_order: form.value.images.length })
  imageUrlInput.value = ''
}

async function onDownloadImage() {
  const url = imageUrlInput.value.trim()
  if (!url) return
  imageDownloading.value = true
  try {
    const res = await downloadProductImage(url)
    if (res.url) {
      form.value.images.push({ url: res.url, is_primary: form.value.images.length === 0, sort_order: form.value.images.length })
      imageUrlInput.value = ''
    }
  } catch (err: any) { showToast(err.detail || err.message, 'error') }
  imageDownloading.value = false
}

async function onPasteImage(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const blob = item.getAsFile()
      if (!blob) continue
      const fd = new FormData()
      fd.append('file', blob, 'paste.' + (item.type.split('/')[1] || 'png'))
      try {
        const res = await uploadProductImage(fd)
        if (res.url) {
          form.value.images.push({ url: res.url, is_primary: form.value.images.length === 0, sort_order: form.value.images.length })
          showToast('图片已粘贴', 'success')
        }
      } catch (err: any) { showToast(err.detail || err.message, 'error') }
      break
    }
  }
}
let _catChangeSeq = 0

function selectCategory(id: number) {
  const idx = form.value.category_ids.indexOf(id)
  if (idx >= 0) {
    form.value.category_ids.splice(idx, 1)
  } else {
    form.value.category_ids.push(id)
  }
  form.value.category_id = form.value.category_ids[0] || null
  onCategoryChange()
}

async function onCategoryChange() {
  if (!form.value.category_id) {
    specDefs.value = []
    return
  }
  const seq = ++_catChangeSeq
  const res = await fetchSpecDefinitions(form.value.category_id)
  if (seq !== _catChangeSeq) return
  specDefs.value = res.spec_definitions
  // Only init new spec keys, keep existing values
  for (const sd of specDefs.value) {
    if (!(sd.spec_key in form.value.specs)) {
      form.value.specs[sd.spec_key] = sd.spec_type === 'boolean' ? false : null
    }
  }
}

async function save() {
  if (!form.value.name?.trim()) { showToast('请填写产品名称', 'error'); return }
  if (!form.value.model?.trim()) { showToast('请填写型号', 'error'); return }
  if (!form.value.manufacturer_id) { showToast('请选择厂商', 'error'); return }
  if (form.value.base_price === undefined || form.value.base_price === null || form.value.base_price === '') { showToast('请填写价格', 'error'); return }
  if (!form.value.category_id) { showToast('请选择品类', 'error'); return }
  if (!form.value.description?.trim()) { showToast('请填写功能描述', 'error'); return }
  // Clean empty mapping entries (no method/protocol/power/metric selected)
  const cleanMappings = (list: any[], key: string) => list?.filter((m: any) => m && m[key])
  const cleaned = { ...form.value,
    comm_methods: cleanMappings(form.value.comm_methods, 'method_id'),
    comm_protocols: cleanMappings(form.value.comm_protocols, 'protocol_id'),
    power_supplies: cleanMappings(form.value.power_supplies, 'power_id'),
    sensor_capabilities: cleanMappings(form.value.sensor_capabilities, 'metric_id'),
    hardware_interfaces: form.value.hardware_interfaces?.filter((m: any) => m?.interface_name),
  }
  try {
    const payload = cleaned
    // Set image_url from primary image in images array
    const primaryImg = payload.images?.find((i: any) => i.is_primary)
    if (primaryImg?.url) payload.image_url = primaryImg.url
    // Store remark in custom_fields
    if (payload.remark) {
      payload.custom_fields = { ...(payload.custom_fields || {}), remark: payload.remark }
    }
    delete payload.remark
    if (isEdit.value) {
      await updateProduct(Number(route.params.id), payload)
      dirty.value = false
      showToast('产品已更新', 'success')
    } else {
      const res = await createProduct(payload) as any
      const newId = res?.product?.id
      dirty.value = false
      showToast('产品已创建', 'success')
      router.push(`/products/${newId}/edit`)
    }
  } catch (e: any) {
    showToast(e.detail || e.message, 'error')
  }
}

onMounted(async () => {
  const [catRes, supRes, mfgRes, cmRes, cpRes, psRes, smRes] = await Promise.all([
    fetchCategories(), fetchSuppliers('', true), fetchManufacturers(1, 200),
    fetchCommMethods(1, 100), fetchCommProtocols(1, 100), fetchPowerSupplies(1, 100), fetchSensorMetrics(1, 100),
  ])
  categories.value = catRes.categories
  flatCategories.value = flattenTree(categories.value)
  suppliers.value = supRes.suppliers
  manufacturers.value = mfgRes.manufacturers
  commMethods.value = cmRes.comm_methods
  commProtocols.value = cpRes.comm_protocols
  powerSupplies.value = psRes.power_supplies
  sensorMetrics.value = smRes.sensor_metrics

  if (isEdit.value) {
    const res = await fetchProduct(Number(route.params.id))
    const p = res.product
    form.value = {
      name: p.name, model: p.model, sku: p.sku, category_id: p.category_id, category_ids: p.category_ids || [p.category_id],
      manufacturer_id: p.manufacturer_id, supplier_id: p.supplier_id,
      base_price: p.base_price, cost_price: p.cost_price,
      description: p.description, status: p.status, parent_id: p.parent_id,
      comm_methods: p.comm_methods || [],
      comm_protocols: p.comm_protocols || [],
      power_supplies: p.power_supplies || [],
      hardware_interfaces: p.hardware_interfaces || [],
      sensor_capabilities: p.sensor_capabilities || [],
      images: p.images?.length ? p.images : (p.image_url ? [{url: p.image_url, is_primary: true, sort_order: 0}] : []),
      image_url: '',
      product_url: p.product_url || '',
      remark: (p.custom_fields && p.custom_fields.remark) || '',
      specs: { ...(p.specs || {}) },
    }
    if (p.category_id) await onCategoryChange()
  }
  loaded.value = true
})
</script>

<style scoped>
.category-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 0;
}
.category-tags .filter-tag {
  margin: 0;
}
</style>
