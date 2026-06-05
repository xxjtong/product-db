<template>
  <PageHeader :title="product?.name || '产品详情'" :breadcrumb="[{ label: '产品列表', to: '/products' }, { label: product?.name || '产品详情', to: '' }]">
    <button v-if="product?.product_url" class="btn-secondary" @click="openUrl(product.product_url)">产品URL</button>
    <button v-if="product" class="btn-secondary" @click="openUrl(specSheetUrl(product.id))">
      <FileTextIcon style="width:14px;height:14px" />规格书
    </button>
    <button class="btn-secondary" @click="$router.push(`/products/${product?.id}/edit`)">
      <PencilIcon style="width:14px;height:14px" />编辑
    </button>
    <button class="btn-secondary" @click="$router.back()">返回</button>
  </PageHeader>

  <div v-if="product" class="card">
    <!-- Product images -->
    <div v-if="allImages.length" class="image-gallery">
      <img v-for="(img, idx) in allImages" :key="idx"
        :src="img" class="gallery-thumb" @click="lightboxIdx = idx" />
    </div>
    <!-- Lightbox -->
    <div v-if="lightboxIdx !== null" class="lightbox" @click="lightboxIdx = null">
      <button class="lightbox-close" @click.stop="lightboxIdx = null">✕</button>
      <button v-if="allImages.length > 1" class="lightbox-prev" @click.stop="lightboxIdx = (lightboxIdx - 1 + allImages.length) % allImages.length">‹</button>
      <img :src="allImages[lightboxIdx]" class="lightbox-img" @click.stop />
      <button v-if="allImages.length > 1" class="lightbox-next" @click.stop="lightboxIdx = (lightboxIdx + 1) % allImages.length">›</button>
    </div>

    <!-- Basic info -->
    <div class="info-bar">
      <div class="info-item"><label>型号</label><span>{{ product.model || '—' }}</span></div>
      <div class="info-item"><label>SKU</label><span>{{ product.sku || '—' }}</span></div>
      <div class="info-item"><label>厂商</label><span>{{ product.manufacturer_name || '—' }}</span></div>
      <div class="info-item"><label>供应商</label><span>{{ product.supplier_name || '—' }}</span></div>
      <div class="info-item"><label>价格</label><span class="font-mono">{{ product.base_price || '—' }}</span></div>
      <div class="info-item"><label>成本</label><span class="font-mono">{{ product.cost_price || '—' }}</span></div>
      <div class="info-item"><label>浏览</label><span>{{ product.view_count || 0 }} 次</span></div>
    </div>
    <div class="info-bar" style="margin-top:4px">
      <div class="info-item"><label>状态</label><span :class="['tag', `tag-${product.status}`]">{{ product.status }}</span></div>
      <div class="info-item" style="flex:1"><label>品类</label>
        <span v-for="cid in (product.category_ids || [product.category_id])" :key="cid" class="tag" :style="{margin:'0 3px', background: catColor(categoryNames[cid] || String(cid)), color:'var(--color-surface)'}" >{{ categoryNames[cid] || cid }}</span>
      </div>
    </div>

    <!-- Comm Methods -->
    <h3 v-if="product.comm_methods?.length">通讯方式</h3>
    <table v-if="product.comm_methods?.length" class="data-table">
      <thead><tr><th>类型</th><th>方式</th><th>详情</th></tr></thead>
      <tbody>
        <tr v-for="cm in product.comm_methods" :key="cm.method_id">
          <td>{{ cm.method_type === 'wired' ? '有线' : '无线' }}</td>
          <td><TagBadge :label="cm.method_name" /></td>
          <td>{{ cm.details || '—' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="text-muted text-sm" style="margin-bottom:16px">暂无通讯方式</p>

    <!-- Comm Protocols -->
    <h3 v-if="product.comm_protocols?.length">通讯协议</h3>
    <table v-if="product.comm_protocols?.length" class="data-table">
      <thead><tr><th>协议</th><th>方向</th></tr></thead>
      <tbody>
        <tr v-for="cp in product.comm_protocols" :key="cp.protocol_id">
          <td><TagBadge :label="cp.protocol_name" /></td>
          <td>{{ cp.direction === 'acquisition' ? '采集(下行)' : cp.direction === 'forwarding' ? '转发(上行)' : '双向' }}</td>
        </tr>
      </tbody>
    </table>

    <!-- Power Supplies -->
    <h3 v-if="product.power_supplies?.length">供电方式</h3>
    <table v-if="product.power_supplies?.length" class="data-table">
      <thead><tr><th>方式</th><th>电压/规格</th><th>续航</th></tr></thead>
      <tbody>
        <tr v-for="ps in product.power_supplies" :key="ps.power_id">
          <td><TagBadge :label="ps.power_name" /></td>
          <td>{{ ps.voltage_range || '—' }}</td>
          <td>{{ ps.battery_life || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <!-- Hardware Interfaces -->
    <h3 v-if="product.hardware_interfaces?.length">硬件接口</h3>
    <table v-if="product.hardware_interfaces?.length" class="data-table">
      <thead><tr><th>接口</th><th>数量</th><th>描述</th></tr></thead>
      <tbody>
        <tr v-for="hi in product.hardware_interfaces" :key="hi.id">
          <td>{{ hi.interface_name }}</td>
          <td>×{{ hi.quantity }}</td>
          <td>{{ hi.description || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <!-- Sensor Capabilities -->
    <h3 v-if="product.sensor_capabilities?.length">传感能力</h3>
    <table v-if="product.sensor_capabilities?.length" class="data-table">
      <thead><tr><th>指标</th><th>单位</th><th>量程</th><th>精度</th><th>分辨率</th></tr></thead>
      <tbody>
        <tr v-for="sc in product.sensor_capabilities" :key="sc.metric_id">
          <td>{{ sc.metric_name }}</td>
          <td>{{ sc.unit }}</td>
          <td>{{ sc.measure_range || '—' }}</td>
          <td>{{ sc.accuracy || '—' }}</td>
          <td>{{ sc.resolution || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <!-- Specs by group -->
    <h3 v-if="specDefs.length">规格参数</h3>
    <div v-if="specDefs.length">
      <div v-for="group in specGroups" :key="group.name" class="spec-group">
        <div v-if="group.name" class="spec-group-title">{{ group.name }}</div>
        <table class="data-table">
          <tbody>
            <tr v-for="sd in group.items" :key="sd.spec_key">
              <td style="width:200px">{{ sd.display_name }} <span v-if="sd.unit" class="text-muted">({{ sd.unit }})</span></td>
              <td>{{ formatSpec(product.specs[sd.spec_key], sd) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="unmatchedSpecs.length" class="spec-group">
        <div class="spec-group-title">其他</div>
        <table class="data-table">
          <tbody>
            <tr v-for="key in unmatchedSpecs" :key="key">
              <td style="width:200px">{{ key }}</td>
              <td>{{ product.specs[key] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Variants -->
    <div v-if="product.variants?.length">
      <h3>变体</h3>
      <table class="data-table">
        <thead><tr><th>名称</th><th>型号</th></tr></thead>
        <tbody>
          <tr v-for="v in product.variants" :key="v.id">
            <td><router-link :to="`/products/${v.id}`">{{ v.name }}</router-link></td>
            <td class="font-mono text-sm">{{ v.model || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Dependencies -->
    <DependencyEditor v-if="product" :productId="product.id" @change="reload" />

    <!-- Description & Remark -->
    <div v-if="product.description">
      <h3>功能描述</h3>
      <p class="text-sm" style="white-space:pre-wrap">{{ product.description }}</p>
    </div>
    <div v-if="product.custom_fields?.remark">
      <h3>备注</h3>
      <p class="text-sm" style="white-space:pre-wrap">{{ product.custom_fields.remark }}</p>
    </div>

  </div>

  <ProductFiles v-if="product" :productId="Number(route.params.id)" class="mt-16" />

  <div v-else-if="loadError" style="text-align:center;padding:48px;color:var(--color-danger)">{{ loadError }}<br /><button class="btn-primary btn-sm" style="margin-top:12px" @click="load">重试</button><br /><router-link to="/products" class="btn-secondary btn-sm" style="margin-top:8px;display:inline-block">返回产品列表</router-link></div>
  <div v-else style="text-align:center;padding:48px;color:var(--color-text-secondary)">加载中...</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { PencilIcon, FileTextIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import TagBadge from '../components/TagBadge.vue'
import DependencyEditor from '../components/DependencyEditor.vue'
import ProductFiles from '../components/ProductFiles.vue'
import { fetchProduct, specSheetUrl, fetchCategories } from '../api'
import type { Product, SpecDefinition } from '../types'

const route = useRoute()
const product = ref<Product | null>(null)
const categoryNames = ref<Record<number, string>>({})
const specDefs = ref<SpecDefinition[]>([])
const lightboxIdx = ref<number | null>(null)

const allImages = computed(() => {
  const imgs: string[] = []
  if (product.value) {
    if (product.value.images?.length) {
      imgs.push(...product.value.images.map((i: any) => i.url))
    } else if (product.value.image_url) {
      imgs.push(product.value.image_url)
    }
  }
  return imgs
})

const specGroups = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const sd of specDefs.value) {
    const g = sd.display_group || ''
    if (!groups[g]) groups[g] = []
    groups[g].push(sd)
  }
  return Object.entries(groups).map(([name, items]) => ({ name, items }))
})

const unmatchedSpecs = computed(() => {
  if (!product.value) return []
  const defined = new Set(specDefs.value.map(sd => sd.spec_key))
  return Object.keys(product.value.specs || {}).filter(k => !defined.has(k))
})

function openUrl(url: string) {
  window.open(url, '_blank')
}

function catColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  const h = Math.abs(hash) % 360
  return `hsl(${h}, 55%, 45%)`
}

function formatSpec(val: any, sd: any): string {
  if (val === null || val === undefined) return '—'
  if (sd.spec_type === 'boolean') return val ? '✓' : '—'
  return String(val)
}

const loadError = ref('')
async function loadCategories() {
  try {
    const res = await fetchCategories('per_page=1000')
    for (const c of (res.categories || [])) {
      categoryNames.value[c.id] = c.name
    }
  } catch { /* ignore */ }
}

async function load() {
  loadError.value = ''
  try {
    const res = await fetchProduct(Number(route.params.id))
    product.value = res.product
    specDefs.value = res.product.spec_definitions || []
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  }
}

onMounted(() => { loadCategories(); load() })
watch(() => route.params.id, () => { if (route.params.id) load() })

function reload() {
  load()
}
</script>

<style scoped>
.info-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 24px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border);
}
.info-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  line-height: 1.5;
}
.info-item label {
  color: var(--color-text-secondary);
  font-size: 12px;
}
.info-item span {
  font-weight: 500;
}
h3 {
  font-size: 13px;
  margin: 12px 0 4px;
}
h3:first-of-type {
  margin-top: 0;
}
.data-table {
  margin-bottom: 8px;
  font-size: 13px;
}
.data-table th,
.data-table td {
  padding: 4px 10px;
}
.spec-group {
  margin-bottom: 8px;
}
.spec-group-title {
  font-size: 12px;
  color: var(--color-text-secondary);
  font-weight: 600;
  margin-bottom: 2px;
}
.image-gallery {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.gallery-thumb {
  width: 200px;
  height: 200px;
  object-fit: contain;
  background: #f5f5f5;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  cursor: pointer;
  transition: transform .15s;
}
.gallery-thumb:hover {
  transform: scale(1.05);
  box-shadow: var(--shadow-sm);
}
.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.85);
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.lightbox-img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 4px;
}
.lightbox-close {
  position: absolute;
  top: 16px;
  right: 20px;
  color: #fff;
  font-size: 28px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
}
.lightbox-prev, .lightbox-next {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  color: #fff;
  font-size: 48px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 16px;
  opacity: .7;
}
.lightbox-prev:hover, .lightbox-next:hover { opacity: 1; }
.lightbox-prev { left: 8px; }
.lightbox-next { right: 8px; }
.font-mono {
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
}
</style>
