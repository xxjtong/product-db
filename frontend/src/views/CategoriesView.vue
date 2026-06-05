<template>
  <PageHeader v-if="!embedded" title="品类管理">
    <button class="btn-primary" @click="openAddCategory">
      <PlusIcon style="width:16px;height:16px" />新增
    </button>
  </PageHeader>

  <div class="card">
    <div v-if="embedded" class="flex justify-between items-center" style="margin-bottom:12px">
      <h3 style="margin:0">品类</h3>
      <button class="btn-primary btn-sm" @click="openAddCategory">+ 新增</button>
    </div>
    <table class="data-table" v-if="categories.length">
      <thead>
        <tr>
          <th>名称</th><th>层级</th><th>Slug</th><th>排序</th><th>状态</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in categories" :key="c.id">
          <td :style="{ paddingLeft: ((c.level - 1) * 20 + 8) + 'px', fontWeight: c.level === 1 ? '600' : '400' }">
            <span v-if="c.level > 1" style="color:var(--color-text-secondary);margin-right:4px">└</span>{{ c.name }}
          </td>
          <td>{{ c.level }}</td>
          <td class="font-mono text-sm">{{ c.slug || '—' }}</td>
          <td>{{ c.sort_order }}</td>
          <td>{{ c.is_active ? '启用' : '停用' }}</td>
          <td>
            <button class="btn-icon btn-sm" title="规格定义" @click="openSpecDefs(c)"><SettingsIcon style="width:15px;height:15px" /></button>
            <button class="btn-icon btn-sm" title="编辑" @click="openEditCategory(c)"><PencilIcon style="width:15px;height:15px" /></button>
            <button class="btn-icon btn-sm" title="删除" @click="confirmDelete(c)"><Trash2Icon style="width:15px;height:15px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state"><InboxIcon /><p>暂无品类</p></div>
    <Pagination :total="total" :page="page" :per-page="perPage" @change="p => { page = p; loadCategories() }" @update:per-page="s => { perPage = s; page = 1; loadCategories() }" />
  </div>

  <!-- Category modal -->
  <Modal :title="editingCat ? '编辑品类' : '新增'" :visible="catModalVisible" @close="catModalVisible = false">
    <div class="form-grid">
      <div class="form-group"><label>名称 *</label><input v-model="catForm.name" /></div>
      <div class="form-group"><label>Slug</label><input v-model="catForm.slug" /></div>
      <div class="form-group">
        <label>父品类</label>
        <select v-model="catForm.parent_id" @change="onParentChange"><option :value="null">— 顶级 —</option><option v-for="c in allCats" :key="c.id" :value="c.id">{{ '—'.repeat(c.level-1) }}{{ c.name }}</option></select>
      </div>
      <div class="form-group"><label>层级</label><input v-model.number="catForm.level" type="number" min="1" max="5" /></div>
      <div class="form-group"><label>排序</label><input v-model.number="catForm.sort_order" type="number" /></div>
      <div class="form-group">
        <label>状态</label>
        <select v-model="catForm.is_active"><option :value="true">启用</option><option :value="false">停用</option></select>
      </div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="catModalVisible = false">取消</button>
      <button class="btn-primary" @click="saveCategory">保存</button>
    </template>
  </Modal>

  <!-- Spec definitions modal -->
  <Modal :title="`规格定义 — ${specDefCat?.name}`" :visible="!!specDefCat" size="lg" @close="specDefCat = null">
    <div v-if="specDefCat" style="max-height:60vh;overflow-y:auto">
      <table class="data-table" v-if="specDefs.length">
        <thead><tr><th>Key</th><th>显示名</th><th>类型</th><th>单位</th><th>分组</th><th>可筛选</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="sd in specDefs" :key="sd.id">
            <td class="font-mono text-sm">{{ sd.spec_key }}</td>
            <td>{{ sd.display_name }}</td>
            <td>{{ sd.spec_type }}</td>
            <td>{{ sd.unit || '—' }}</td>
            <td>{{ sd.display_group || '—' }}</td>
            <td>{{ sd.is_filterable ? '✓' : '—' }}</td>
            <td>
              <button class="btn-icon btn-sm" @click="openEditSpecDef(sd)"><PencilIcon style="width:14px;height:14px" /></button>
              <button class="btn-icon btn-sm" @click="deleteSpecDef(sd.id)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state" style="padding:24px"><p>暂无规格定义</p></div>
      <button class="btn-secondary btn-sm" @click="openAddSpecDef" style="margin-top:8px">+ 新增规格</button>

      <!-- Spec def form -->
      <div v-if="specDefFormVisible" style="margin-top:12px;padding:12px;border:1px solid var(--color-border);border-radius:8px">
        <h4 style="margin:0 0 8px">{{ editingSpecDef ? '编辑规格' : '新增规格' }}</h4>
        <div class="form-grid">
          <div class="form-group"><label>Key *</label><input v-model="specDefForm.spec_key" placeholder="e.g. ip_rating" /></div>
          <div class="form-group"><label>显示名 *</label><input v-model="specDefForm.display_name" placeholder="e.g. 防护等级" /></div>
          <div class="form-group">
            <label>类型</label>
            <select v-model="specDefForm.spec_type"><option>string</option><option>number</option><option>boolean</option><option>enum</option></select>
          </div>
          <div class="form-group"><label>单位</label><input v-model="specDefForm.unit" placeholder="e.g. mm, kg" /></div>
          <div class="form-group"><label>分组</label><input v-model="specDefForm.display_group" placeholder="e.g. 硬件" /></div>
          <div class="form-group"><label>排序</label><input v-model.number="specDefForm.sort_order" type="number" /></div>
          <div class="form-group">
            <label>可筛选</label>
            <select v-model="specDefForm.is_filterable"><option :value="true">是</option><option :value="false">否</option></select>
          </div>
        </div>
        <button class="btn-primary btn-sm" @click="saveSpecDef">保存规格</button>
        <button class="btn-secondary btn-sm" @click="specDefFormVisible = false" style="margin-left:8px">取消</button>
      </div>
    </div>
  </Modal>

  <ConfirmDialog title="删除品类" :message="`确定删除「${deleteTarget?.name}」？`" :visible="!!deleteTarget" @confirm="doDelete" @cancel="deleteTarget = null" />
</template>

<script setup lang="ts">
defineProps<{ embedded?: boolean }>()
import { ref, reactive, onMounted, inject } from 'vue'
import { PlusIcon, PencilIcon, Trash2Icon, SettingsIcon, InboxIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import Pagination from '../components/Pagination.vue'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { fetchCategories, createCategory, updateCategory, deleteCategory, fetchSpecDefinitions, createSpecDefinition, updateSpecDefinition, deleteSpecDefinition } from '../api'
import type { Category, SpecDefinition } from '../types'

const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const categories = ref<Category[]>([])
const allCats = ref<Category[]>([])
const total = ref(0)
const page = ref(1)
const perPage = ref(25)

// Category CRUD
const catModalVisible = ref(false)
const editingCat = ref<Category | null>(null)
const catForm = reactive({ name: '', slug: '', parent_id: null as number | null, level: 1, sort_order: 0, is_active: true })

function onParentChange() {
  if (!catForm.parent_id) { catForm.level = 1; return }
  const parent = allCats.value.find(c => c.id === catForm.parent_id)
  catForm.level = parent ? parent.level + 1 : 2
}
const deleteTarget = ref<Category | null>(null)

// Spec definitions
const specDefCat = ref<Category | null>(null)
const specDefs = ref<SpecDefinition[]>([])
const specDefFormVisible = ref(false)
const editingSpecDef = ref<SpecDefinition | null>(null)
const specDefForm = reactive({ spec_key: '', display_name: '', spec_type: 'string', unit: '', display_group: '', sort_order: 0, is_filterable: true })


async function loadCategories() {
  try {
    const res = await fetchCategories(`page=${page.value}&per_page=${perPage.value}`)
    categories.value = res.categories
    total.value = res.total || 0
  } catch (e: any) { showToast(e.message || '加载失败', 'error') }
}

async function loadAllCats() {
  try {
    const res = await fetchCategories('per_page=1000')
    allCats.value = res.categories
  } catch { /* ignore */ }
}

function openAddCategory() {
  editingCat.value = null
  Object.assign(catForm, { name: '', slug: '', parent_id: null, level: 1, sort_order: 0, is_active: true })
  catModalVisible.value = true
}

function openEditCategory(c: any) {
  editingCat.value = c
  Object.assign(catForm, { name: c.name, slug: c.slug || '', parent_id: c.parent_id, level: c.level || 1, sort_order: c.sort_order || 0, is_active: c.is_active })
  catModalVisible.value = true
}

async function saveCategory() {
  try {
    if (editingCat.value) {
      await updateCategory(editingCat.value.id, catForm)
      showToast('品类已更新', 'success')
    } else {
      await createCategory(catForm)
      showToast('品类已创建', 'success')
    }
    catModalVisible.value = false
    loadCategories()
    loadAllCats()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

function confirmDelete(c: any) { deleteTarget.value = c }

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await deleteCategory(deleteTarget.value.id)
    showToast('已删除', 'success')
    deleteTarget.value = null
    loadCategories()
    loadAllCats()
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

// Spec definitions
async function openSpecDefs(c: any) {
  specDefCat.value = c
  specDefFormVisible.value = false
  try {
    const res = await fetchSpecDefinitions(c.id)
    specDefs.value = res.spec_definitions
  } catch { specDefs.value = [] }
}

function openAddSpecDef() {
  editingSpecDef.value = null
  Object.assign(specDefForm, { spec_key: '', display_name: '', spec_type: 'string', unit: '', display_group: '', sort_order: 0, is_filterable: true })
  specDefFormVisible.value = true
}

function openEditSpecDef(sd: any) {
  editingSpecDef.value = sd
  Object.assign(specDefForm, { spec_key: sd.spec_key, display_name: sd.display_name, spec_type: sd.spec_type, unit: sd.unit || '', display_group: sd.display_group || '', sort_order: sd.sort_order || 0, is_filterable: sd.is_filterable })
  specDefFormVisible.value = true
}

async function saveSpecDef() {
  if (!specDefCat.value) return
  try {
    if (editingSpecDef.value) {
      await updateSpecDefinition(specDefCat.value.id, editingSpecDef.value.id, specDefForm)
      showToast('规格已更新', 'success')
    } else {
      await createSpecDefinition(specDefCat.value.id, specDefForm)
      showToast('规格已创建', 'success')
    }
    specDefFormVisible.value = false
    const res = await fetchSpecDefinitions(specDefCat.value.id)
    specDefs.value = res.spec_definitions
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

async function deleteSpecDef(id: number) {
  if (!specDefCat.value) return
  try {
    await deleteSpecDefinition(specDefCat.value.id, id)
    showToast('已删除', 'success')
    specDefs.value = specDefs.value.filter((s: any) => s.id !== id)
  } catch (e: any) { showToast(e.detail || e.message, 'error') }
}

onMounted(() => {
  loadCategories()
  loadAllCats()
})
</script>