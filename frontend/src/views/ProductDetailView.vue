<template>
  <PageHeader :title="product?.name || '产品详情'">
    <a v-if="product" :href="specSheetUrl(product.id)" target="_blank" class="btn-secondary" style="text-decoration:none;display:inline-flex;align-items:center">
      <FileTextIcon style="width:14px;height:14px;margin-right:4px" />规格书
    </a>
    <button class="btn-secondary" @click="$router.push(`/products/${product?.id}/edit`)">
      <PencilIcon style="width:14px;height:14px;display:inline;vertical-align:middle;margin-right:4px" />编辑
    </button>
    <button class="btn-secondary" @click="$router.back()">返回</button>
  </PageHeader>

  <div v-if="product" class="card">
    <!-- Product images -->
    <div v-if="product.images?.length" style="margin-bottom:16px">
      <img v-for="img in product.images.filter((i:any) => i.is_primary)" :key="img.id"
        :src="img.url" style="max-height:180px;max-width:300px;border-radius:var(--radius-md);border:1px solid var(--color-border)" />
      <div v-if="product.images.length > 1" style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
        <img v-for="img in product.images.filter((i:any) => !i.is_primary)" :key="img.id"
          :src="img.url" style="width:60px;height:60px;object-fit:cover;border-radius:4px;border:1px solid var(--color-border)" />
      </div>
    </div>

    <!-- Basic info -->
    <div class="form-grid" style="margin-bottom:20px">
      <div><span class="text-muted text-sm">型号</span><br class="font-mono">{{ product.model || '—' }}</div>
      <div><span class="text-muted text-sm">SKU</span><br>{{ product.sku || '—' }}</div>
      <div><span class="text-muted text-sm">品类</span><br>{{ product.category_name }}</div>
      <div><span class="text-muted text-sm">厂商</span><br>{{ product.manufacturer_name || '—' }}</div>
      <div><span class="text-muted text-sm">供应商</span><br>{{ product.supplier_name || '—' }}</div>
      <div><span class="text-muted text-sm">价格</span><br class="font-mono">{{ product.base_price || '—' }}</div>
      <div><span class="text-muted text-sm">成本</span><br class="font-mono">{{ product.cost_price || '—' }}</div>
      <div><span class="text-muted text-sm">状态</span><br>{{ product.status }}</div>
    </div>

    <!-- Comm Methods -->
    <h3 style="margin-bottom:8px">通讯方式</h3>
    <table class="data-table" style="margin-bottom:16px">
      <thead><tr><th>类型</th><th>方式</th><th>详情</th></tr></thead>
      <tbody>
        <tr v-for="cm in product.comm_methods" :key="cm.method_id">
          <td>{{ cm.method_type === 'wired' ? '有线' : '无线' }}</td>
          <td><TagBadge :label="cm.method_name" /></td>
          <td>{{ cm.details || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <!-- Comm Protocols -->
    <h3 v-if="product.comm_protocols?.length" style="margin-bottom:8px">通讯协议</h3>
    <table v-if="product.comm_protocols?.length" class="data-table" style="margin-bottom:16px">
      <thead><tr><th>协议</th><th>方向</th></tr></thead>
      <tbody>
        <tr v-for="cp in product.comm_protocols" :key="cp.protocol_id">
          <td><TagBadge :label="cp.protocol_name" /></td>
          <td>{{ cp.direction === 'acquisition' ? '采集(下行)' : cp.direction === 'forwarding' ? '转发(上行)' : '双向' }}</td>
        </tr>
      </tbody>
    </table>

    <!-- Power Supplies -->
    <h3 v-if="product.power_supplies?.length" style="margin-bottom:8px">供电方式</h3>
    <table v-if="product.power_supplies?.length" class="data-table" style="margin-bottom:16px">
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
    <h3 v-if="product.hardware_interfaces?.length" style="margin-bottom:8px">硬件接口</h3>
    <table v-if="product.hardware_interfaces?.length" class="data-table" style="margin-bottom:16px">
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
    <h3 v-if="product.sensor_capabilities?.length" style="margin-bottom:8px">传感能力</h3>
    <table v-if="product.sensor_capabilities?.length" class="data-table" style="margin-bottom:16px">
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
    <h3 v-if="specDefs.length" style="margin-bottom:8px">规格参数</h3>
    <div v-if="specDefs.length">
      <div v-for="group in specGroups" :key="group.name" style="margin-bottom:16px">
        <div v-if="group.name" class="text-sm text-muted" style="margin-bottom:4px;font-weight:600">{{ group.name }}</div>
        <table class="data-table">
          <tbody>
            <tr v-for="sd in group.items" :key="sd.spec_key">
              <td style="width:200px">{{ sd.display_name }} <span v-if="sd.unit" class="text-muted">({{ sd.unit }})</span></td>
              <td>{{ formatSpec(product.specs[sd.spec_key], sd) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="unmatchedSpecs.length">
        <div class="text-sm text-muted" style="margin-bottom:4px;font-weight:600">其他</div>
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
    <div v-if="product.variants?.length" style="margin-top:20px">
      <h3 style="margin-bottom:8px">变体</h3>
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
    <div v-if="product.dependencies?.length" style="margin-top:20px">
      <h3 style="margin-bottom:8px">依赖关系</h3>
      <table class="data-table">
        <thead><tr><th>类型</th><th>目标</th><th>描述</th></tr></thead>
        <tbody>
          <tr v-for="d in product.dependencies" :key="d.id">
            <td><span :class="['tag', d.dependency_type === 'required' ? 'tag-lorawan' : 'tag-default']">{{ d.dependency_type }}</span></td>
            <td>{{ d.depends_on_product_id || d.depends_on_category_id }}</td>
            <td>{{ d.description }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Description -->
    <div v-if="product.description" style="margin-top:20px">
      <h3 style="margin-bottom:8px">描述</h3>
      <p class="text-sm" style="white-space:pre-wrap">{{ product.description }}</p>
    </div>
  </div>
  <div v-else style="text-align:center;padding:48px;color:var(--color-text-secondary)">加载中...</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { PencilIcon, FileTextIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import TagBadge from '../components/TagBadge.vue'
import { fetchProduct, specSheetUrl } from '../api'

const route = useRoute()
const product = ref<any>(null)
const specDefs = ref<any[]>([])

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

function formatSpec(val: any, sd: any): string {
  if (val === null || val === undefined) return '—'
  if (sd.spec_type === 'boolean') return val ? '✓' : '—'
  return String(val)
}

onMounted(async () => {
  const res = await fetchProduct(Number(route.params.id))
  product.value = res.product
  specDefs.value = res.product.spec_definitions || []
})
</script>
