<template>
  <PageHeader title="字典管理" />

  <div v-if="loading" class="empty-state"><p>加载中...</p></div>
  <div v-else-if="loadError" class="empty-state"><p style="color:var(--color-danger)">{{ loadError }}</p><button class="btn-secondary btn-sm" style="margin-top:8px" @click="loadAll">重试</button></div>
  <template v-else>

  <!-- Tab bar -->
  <div class="card" style="margin-bottom:16px;padding:8px 12px">
    <div class="dict-tabs">
      <button v-for="t in tabs" :key="t.key" :class="['dict-tab', { active: activeTab === t.key }]" @click="activeTab = t.key">{{ t.label }}</button>
    </div>
  </div>

  <!-- 通讯方式 -->
  <div class="card" v-show="activeTab === 'comm_methods'">
    <h3 style="margin-bottom:12px">通讯方式</h3>
    <table class="data-table">
      <thead><tr><th>ID</th><th>类型</th><th>名称</th></tr></thead>
      <tbody><tr v-for="m in commMethods" :key="m.id"><td>{{ m.id }}</td><td>{{ m.method_type === 'wired' ? '有线' : '无线' }}</td><td>{{ m.name }}</td></tr></tbody>
    </table>
    <Pagination :total="cmTotal" :page="cmPage" :per-page="dictPerPage" @change="p => { cmPage = p; loadCommMethods() }" @update:per-page="s => { dictPerPage = s; cmPage = 1; loadCommMethods() }" />
  </div>

  <!-- 通讯协议 -->
  <div class="card" v-show="activeTab === 'comm_protocols'">
    <h3 style="margin-bottom:12px">通讯协议</h3>
    <table class="data-table">
      <thead><tr><th>ID</th><th>名称</th></tr></thead>
      <tbody><tr v-for="p in commProtocols" :key="p.id"><td>{{ p.id }}</td><td>{{ p.name }}</td></tr></tbody>
    </table>
    <Pagination :total="cpTotal" :page="cpPage" :per-page="dictPerPage" @change="p => { cpPage = p; loadCommProtocols() }" @update:per-page="s => { dictPerPage = s; cpPage = 1; loadCommProtocols() }" />
  </div>

  <!-- 供电方式 -->
  <div class="card" v-show="activeTab === 'power_supplies'">
    <h3 style="margin-bottom:12px">供电方式</h3>
    <table class="data-table">
      <thead><tr><th>ID</th><th>类别</th><th>名称</th></tr></thead>
      <tbody><tr v-for="p in powerSupplies" :key="p.id"><td>{{ p.id }}</td><td>{{ p.supply_category }}</td><td>{{ p.name }}</td></tr></tbody>
    </table>
    <Pagination :total="psTotal" :page="psPage" :per-page="dictPerPage" @change="p => { psPage = p; loadPowerSupplies() }" @update:per-page="s => { dictPerPage = s; psPage = 1; loadPowerSupplies() }" />
  </div>

  <!-- 传感器指标 -->
  <div class="card" v-show="activeTab === 'sensor_metrics'">
    <h3 style="margin-bottom:12px">传感器指标</h3>
    <table class="data-table">
      <thead><tr><th>ID</th><th>名称</th><th>单位</th></tr></thead>
      <tbody><tr v-for="m in sensorMetrics" :key="m.id"><td>{{ m.id }}</td><td>{{ m.name }}</td><td>{{ m.unit || '—' }}</td></tr></tbody>
    </table>
    <Pagination :total="smTotal" :page="smPage" :per-page="dictPerPage" @change="p => { smPage = p; loadSensorMetrics() }" @update:per-page="s => { dictPerPage = s; smPage = 1; loadSensorMetrics() }" />
  </div>

  <!-- 厂商 -->
  <div class="card" v-show="activeTab === 'manufacturers'">
    <div class="flex justify-between items-center" style="margin-bottom:12px">
      <h3 style="margin:0">厂商</h3>
      <button class="btn-primary btn-sm" @click="openAddMfg">+ 新增</button>
    </div>
    <table class="data-table">
      <thead><tr><th>ID</th><th>名称</th><th>网站</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="m in manufacturers" :key="m.id">
          <td>{{ m.id }}</td>
          <td>{{ m.name }}</td>
          <td><a v-if="m.website" :href="m.website" target="_blank" class="text-sm">{{ m.website }}</a><span v-else class="text-muted">—</span></td>
          <td>
            <button class="btn-icon btn-sm" @click="openEditMfg(m)"><PencilIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" @click="doDeleteMfg(m)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <Pagination :total="mfgTotal" :page="mfgPage" :per-page="perPage" @change="p => { mfgPage = p; loadManufacturers() }" @update:per-page="s => { perPage = s; mfgPage = 1; loadManufacturers() }" />

    <Modal :title="editingMfg ? '编辑厂商' : '新增厂商'" :visible="mfgModalVisible" @close="mfgModalVisible = false">
      <div class="form-grid">
        <div class="form-group"><label>名称 *</label><input v-model="mfgForm.name" /></div>
        <div class="form-group full"><label>网站</label><input v-model="mfgForm.website" /></div>
      </div>
      <template #footer>
        <button class="btn-secondary" @click="mfgModalVisible = false">取消</button>
        <button class="btn-primary" @click="saveMfg">保存</button>
      </template>
    </Modal>
  </div>
  <!-- 供应商 -->
  <div class="card" v-show="activeTab === 'suppliers'">
    <div class="flex justify-between items-center" style="margin-bottom:12px">
      <h3 style="margin:0">供应商</h3>
      <button class="btn-primary btn-sm" @click="openAddSup">+ 新增</button>
    </div>
    <table class="data-table">
      <thead><tr><th>ID</th><th>名称</th><th>联系人</th><th>电话</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="s in suppliers" :key="s.id">
          <td>{{ s.id }}</td>
          <td>{{ s.name }}</td>
          <td>{{ s.contact || '—' }}</td>
          <td>{{ s.phone || '—' }}</td>
          <td>
            <button class="btn-icon btn-sm" @click="openEditSup(s)"><PencilIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" @click="showConfirm(() => deleteSup(s.id))"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <Pagination :total="supTotal" :page="supPage" :per-page="perPage" @change="p => { supPage = p; loadSuppliers() }" @update:per-page="s => { perPage = s; supPage = 1; loadSuppliers() }" />

    <Modal :title="editingSup ? '编辑供应商' : '新增供应商'" :visible="supModalVisible" @close="supModalVisible = false">
      <div class="form-grid">
        <div class="form-group"><label>名称 *</label><input v-model="supForm.name" /></div>
        <div class="form-group"><label>联系人</label><input v-model="supForm.contact" /></div>
        <div class="form-group"><label>电话</label><input v-model="supForm.phone" /></div>
        <div class="form-group"><label>邮箱</label><input v-model="supForm.email" /></div>
        <div class="form-group full"><label>备注</label><input v-model="supForm.notes" /></div>
      </div>
      <template #footer>
        <button class="btn-secondary" @click="supModalVisible = false">取消</button>
        <button class="btn-primary" @click="saveSup">保存</button>
      </template>
    </Modal>
  </div>
  <ConfirmDialog title="删除厂商" :message="`确定删除该厂商？`" :visible="confirmState.visible" @confirm="confirmState.action(); confirmState.visible = false" @cancel="confirmState.visible = false" />
  </template>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { PencilIcon, Trash2Icon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import Pagination from '../components/Pagination.vue'
import { fetchCommMethods, fetchCommProtocols, fetchPowerSupplies, fetchSensorMetrics, fetchManufacturers, createManufacturer, updateManufacturer, fetchSuppliers, createSupplier, updateSupplier, deleteSupplier } from '../api'
import type { Manufacturer, Supplier } from '../types'

const activeTab = ref('comm_methods')
const tabs = [
  { key: 'comm_methods', label: '通讯方式' },
  { key: 'comm_protocols', label: '通讯协议' },
  { key: 'power_supplies', label: '供电方式' },
  { key: 'sensor_metrics', label: '传感器指标' },
  { key: 'manufacturers', label: '厂商' },
  { key: 'suppliers', label: '供应商' },
]
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})
const confirmState = ref({ visible: false, action: () => {} })
function showConfirm(action: () => void) { confirmState.value = { visible: true, action } }

interface DictItem { id: number; name: string; method_type?: string; supply_category?: string; unit?: string }

const commMethods = ref<DictItem[]>([])
const commProtocols = ref<DictItem[]>([])
const powerSupplies = ref<DictItem[]>([])
const sensorMetrics = ref<DictItem[]>([])
const manufacturers = ref<Manufacturer[]>([])
const mfgPage = ref(1); const mfgTotal = ref(0); const perPage = ref(20); const dictPerPage = ref(20)
const cmPage = ref(1); const cmTotal = ref(0)
const cpPage = ref(1); const cpTotal = ref(0)
const psPage = ref(1); const psTotal = ref(0)
const smPage = ref(1); const smTotal = ref(0)

const mfgModalVisible = ref(false)
const editingMfg = ref<any>(null)
const mfgForm = ref<any>({ name: '', website: '' })

function openAddMfg() {
  editingMfg.value = null
  mfgForm.value = { name: '', website: '' }
  mfgModalVisible.value = true
}

function openEditMfg(m: any) {
  editingMfg.value = m
  mfgForm.value = { name: m.name, website: m.website || '' }
  mfgModalVisible.value = true
}

async function saveMfg() {
  try {
    if (editingMfg.value) {
      await updateManufacturer(editingMfg.value.id, mfgForm.value)
      showToast('厂商已更新', 'success')
    } else {
      await createManufacturer(mfgForm.value)
      showToast('厂商已创建', 'success')
    }
    mfgModalVisible.value = false
    await loadManufacturers()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function doDeleteMfg(m: any) {
  showConfirm(async () => {
    try {
      // No delete API yet, but would call deleteManufacturer(m.id)
      showToast('删除功能待实现', 'error')
    } catch (e: any) { showToast(e.detail || e.message, 'error') }
  })
}

const loading = ref(false)
const loadError = ref('')

async function loadManufacturers() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await fetchManufacturers(mfgPage.value, perPage.value)
    manufacturers.value = res.manufacturers
    mfgTotal.value = res.total || 0
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  }
  loading.value = false
}

async function loadCommMethods() { const res = await fetchCommMethods(cmPage.value, dictPerPage.value); commMethods.value = res.comm_methods; cmTotal.value = res.total }
async function loadCommProtocols() { const res = await fetchCommProtocols(cpPage.value, dictPerPage.value); commProtocols.value = res.comm_protocols; cpTotal.value = res.total }
async function loadPowerSupplies() { const res = await fetchPowerSupplies(psPage.value, dictPerPage.value); powerSupplies.value = res.power_supplies; psTotal.value = res.total }
async function loadSensorMetrics() { const res = await fetchSensorMetrics(smPage.value, dictPerPage.value); sensorMetrics.value = res.sensor_metrics; smTotal.value = res.total }

async function loadAll() {
  loading.value = true
  loadError.value = ''
  try {
    const [cm, cp, ps, sm, mfg, sup] = await Promise.all([
      fetchCommMethods(cmPage.value, dictPerPage.value),
      fetchCommProtocols(cpPage.value, dictPerPage.value),
      fetchPowerSupplies(psPage.value, dictPerPage.value),
      fetchSensorMetrics(smPage.value, dictPerPage.value),
      fetchManufacturers(mfgPage.value, perPage.value),
      fetchSuppliers(`page=1&per_page=${perPage.value}`),
    ])
    commMethods.value = cm.comm_methods; cmTotal.value = cm.total
    commProtocols.value = cp.comm_protocols; cpTotal.value = cp.total
    powerSupplies.value = ps.power_supplies; psTotal.value = ps.total
    sensorMetrics.value = sm.sensor_metrics; smTotal.value = sm.total
    manufacturers.value = mfg.manufacturers; mfgTotal.value = mfg.total || 0
    suppliers.value = (sup as any).suppliers; supTotal.value = (sup as any).total || 0
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  }
  loading.value = false
}

// Suppliers
const suppliers = ref<Supplier[]>([])
const supTotal = ref(0)
const supPage = ref(1)
const supModalVisible = ref(false)
const editingSup = ref<Supplier | null>(null)
const supForm = ref({ name: '', contact: '', phone: '', email: '', notes: '' })

async function loadSuppliers() {
  const res = await fetchSuppliers(`page=${supPage.value}&per_page=${perPage.value}`) as any
  suppliers.value = res.suppliers; supTotal.value = res.total
}
function openAddSup() { editingSup.value = null; supForm.value = { name: '', contact: '', phone: '', email: '', notes: '' }; supModalVisible.value = true }
function openEditSup(s: Supplier) { editingSup.value = s; supForm.value = { name: s.name, contact: s.contact || '', phone: s.phone || '', email: s.email || '', notes: s.notes || '' }; supModalVisible.value = true }
async function saveSup() {
  try { editingSup.value ? await updateSupplier(editingSup.value.id, supForm.value) : await createSupplier(supForm.value); supModalVisible.value = false; await loadSuppliers(); showToast('已保存', 'success') }
  catch (e: any) { showToast(e.detail || e.message, 'error') }
}
async function deleteSup(id: number) { await deleteSupplier(id); showToast('已删除', 'success'); await loadSuppliers() }

onMounted(loadAll)
</script>

<style scoped>
.dict-tabs { display: flex; gap: 4px; }
.dict-tab {
  padding: 6px 16px; border: none; background: transparent;
  font-size: 13px; cursor: pointer; border-radius: 6px;
  color: var(--color-text-secondary); transition: all .15s;
}
.dict-tab:hover { background: var(--color-hover); color: var(--color-text); }
.dict-tab.active { background: var(--color-accent); color: #fff; }
</style>
