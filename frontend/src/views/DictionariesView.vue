<template>
  <PageHeader title="字典管理" />

  <div class="card" style="margin-bottom:16px">
    <h3 style="margin-bottom:12px">通讯方式</h3>
    <table class="data-table">
      <thead><tr><th>ID</th><th>类型</th><th>名称</th></tr></thead>
      <tbody>
        <tr v-for="m in commMethods" :key="m.id">
          <td>{{ m.id }}</td>
          <td>{{ m.method_type === 'wired' ? '有线' : '无线' }}</td>
          <td>{{ m.name }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card" style="margin-bottom:16px">
    <h3 style="margin-bottom:12px">通讯协议</h3>
    <table class="data-table">
      <thead><tr><th>ID</th><th>名称</th></tr></thead>
      <tbody>
        <tr v-for="p in commProtocols" :key="p.id">
          <td>{{ p.id }}</td>
          <td>{{ p.name }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card" style="margin-bottom:16px">
    <h3 style="margin-bottom:12px">供电方式</h3>
    <table class="data-table">
      <thead><tr><th>ID</th><th>类别</th><th>名称</th></tr></thead>
      <tbody>
        <tr v-for="p in powerSupplies" :key="p.id">
          <td>{{ p.id }}</td>
          <td>{{ p.supply_category }}</td>
          <td>{{ p.name }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card" style="margin-bottom:16px">
    <h3 style="margin-bottom:12px">传感器指标</h3>
    <table class="data-table">
      <thead><tr><th>ID</th><th>名称</th><th>单位</th></tr></thead>
      <tbody>
        <tr v-for="m in sensorMetrics" :key="m.id">
          <td>{{ m.id }}</td>
          <td>{{ m.name }}</td>
          <td>{{ m.unit || '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="card">
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
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { PencilIcon, Trash2Icon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'
import { fetchCommMethods, fetchCommProtocols, fetchPowerSupplies, fetchSensorMetrics, fetchManufacturers, createManufacturer, updateManufacturer } from '../api'

const showToast = inject<(msg: string, type?: string) => void>('toast')!

const commMethods = ref<any[]>([])
const commProtocols = ref<any[]>([])
const powerSupplies = ref<any[]>([])
const sensorMetrics = ref<any[]>([])
const manufacturers = ref<any[]>([])

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
  if (!confirm(`删除厂商「${m.name}」？`)) return
  try {
    // No delete API yet, but would call deleteManufacturer(m.id)
    showToast('删除功能待实现', 'error')
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function loadManufacturers() {
  const res = await fetchManufacturers()
  manufacturers.value = res.manufacturers
}

onMounted(async () => {
  const [cm, cp, ps, sm, mfg] = await Promise.all([
    fetchCommMethods(), fetchCommProtocols(), fetchPowerSupplies(), fetchSensorMetrics(), fetchManufacturers(),
  ])
  commMethods.value = cm.comm_methods
  commProtocols.value = cp.comm_protocols
  powerSupplies.value = ps.power_supplies
  sensorMetrics.value = sm.sensor_metrics
  manufacturers.value = mfg.manufacturers
})
</script>
