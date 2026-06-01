<template>
  <PageHeader title="品类管理">
    <button class="btn-primary" @click="openAddCategory">
      <PlusIcon style="width:16px;height:16px;display:inline;vertical-align:middle;margin-right:4px" />新增品类
    </button>
  </PageHeader>

  <div class="card">
    <table class="data-table" v-if="flatList.length">
      <thead>
        <tr>
          <th>名称</th><th>层级</th><th>Slug</th><th>排序</th><th>状态</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in flatList" :key="c.id">
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
    <div v-else class="empty-state">
      <InboxIcon /><p>暂无品类</p>
    </div>
  </div>

  <!-- Category Modal -->
  <Modal :title="editingCat ? '编辑品类' : '新增品类'" :visible="catModalVisible" @close="catModalVisible = false">
    <div class="form-grid">
      <div class="form-group">
        <label>名称</label>
        <input v-model="catForm.name" placeholder="品类名称" />
      </div>
      <div class="form-group">
        <label>Slug</label>
        <input v-model="catForm.slug" placeholder="auto-generated" />
      </div>
      <div class="form-group">
        <label>上级品类</label>
        <select v-model="catForm.parent_id">
          <option :value="null">无 (顶级品类)</option>
          <option v-for="c in level1Categories" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>层级</label>
        <select v-model="catForm.level">
          <option :value="1">1 - 大类</option>
          <option :value="2">2 - 子类</option>
          <option :value="3">3 - 孙类</option>
        </select>
      </div>
      <div class="form-group">
        <label>排序</label>
        <input v-model.number="catForm.sort_order" type="number" />
      </div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="catModalVisible = false">取消</button>
      <button class="btn-primary" @click="saveCategory">保存</button>
    </template>
  </Modal>

  <!-- Confirm delete -->
  <ConfirmDialog title="删除品类" :message="`确定删除「${deleteTarget?.name}」？关联的规格定义也会被删除。`" :visible="!!deleteTarget" @confirm="doDeleteCategory" @cancel="deleteTarget = null" />

  <!-- Spec Definitions Modal -->
  <Modal :title="`规格定义 — ${specCat?.name || ''}`" :visible="specModalVisible" @close="specModalVisible = false">
    <div class="flex justify-between mb-16">
      <span class="text-sm text-muted">管理品类特有参数</span>
      <button class="btn-primary btn-sm" @click="openAddSpecDef">+ 新增</button>
    </div>
    <table class="data-table" v-if="specDefs.length">
      <thead>
        <tr><th>Key</th><th>显示名</th><th>类型</th><th>单位</th><th>可筛选</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="s in specDefs" :key="s.id">
          <td class="font-mono text-sm">{{ s.spec_key }}</td>
          <td>{{ s.display_name }}</td>
          <td>{{ s.spec_type }}</td>
          <td>{{ s.unit || '—' }}</td>
          <td>{{ s.is_filterable ? '✓' : '—' }}</td>
          <td>
            <button class="btn-icon btn-sm" @click="openEditSpecDef(s)"><PencilIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" @click="doDeleteSpecDef(s)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state" style="padding:24px"><p>暂无规格定义</p></div>
    <template #footer>
      <button class="btn-secondary" @click="specModalVisible = false">关闭</button>
    </template>
  </Modal>

  <!-- Spec Def Edit Modal -->
  <Modal :title="editingSpec ? '编辑规格' : '新增规格'" :visible="specEditVisible" @close="specEditVisible = false">
    <div class="form-grid">
      <div class="form-group">
        <label>spec_key</label>
        <input v-model="specForm.spec_key" placeholder="e.g. ip_rating" />
      </div>
      <div class="form-group">
        <label>显示名</label>
        <input v-model="specForm.display_name" placeholder="e.g. IP等级" />
      </div>
      <div class="form-group">
        <label>类型</label>
        <select v-model="specForm.spec_type">
          <option value="string">string</option>
          <option value="number">number</option>
          <option value="enum">enum</option>
          <option value="boolean">boolean</option>
          <option value="range">range</option>
        </select>
      </div>
      <div class="form-group">
        <label>单位</label>
        <input v-model="specForm.unit" placeholder="e.g. °C" />
      </div>
      <div class="form-group">
        <label>分组</label>
        <input v-model="specForm.display_group" placeholder="e.g. 硬件" />
      </div>
      <div class="form-group">
        <label>排序</label>
        <input v-model.number="specForm.sort_order" type="number" />
      </div>
      <div class="form-group full">
        <label>选项 (enum 可选值, JSON 数组)</label>
        <textarea v-model="specForm.options_json" rows="2" placeholder='["IP30","IP65","IP67"]' />
      </div>
      <div class="form-group">
        <label>可筛选</label>
        <input type="checkbox" v-model="specForm.is_filterable" />
      </div>
      <div class="form-group">
        <label>可对比</label>
        <input type="checkbox" v-model="specForm.is_comparable" />
      </div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="specEditVisible = false">取消</button>
      <button class="btn-primary" @click="saveSpecDef">保存</button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, inject } from 'vue'
import { PlusIcon, PencilIcon, Trash2Icon, SettingsIcon, InboxIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { fetchCategories, createCategory, updateCategory, deleteCategory, fetchSpecDefinitions, createSpecDefinition, updateSpecDefinition, deleteSpecDefinition } from '../api'

const showToast = inject<(msg: string, type?: string) => void>('toast')!

const categories = ref<any[]>([])

const level1Categories = computed(() => categories.value.filter(c => !c.parent_id))

const flatList = computed(() => {
  const result: any[] = []
  function walk(nodes: any[]) {
    for (const n of nodes) {
      result.push(n)
      if (n.children?.length) walk(n.children)
    }
  }
  // Build tree from flat list
  const map = new Map(categories.value.map(c => [c.id, { ...c, children: [] as any[] }]))
  const roots: any[] = []
  for (const c of map.values()) {
    if (c.parent_id && map.has(c.parent_id)) {
      map.get(c.parent_id)!.children.push(c)
    } else {
      roots.push(c)
    }
  }
  walk(roots)
  return result
})
const catModalVisible = ref(false)
const editingCat = ref<any>(null)
const catForm = ref<any>({ name: '', slug: '', parent_id: null, level: 1, sort_order: 0, is_active: true })
const deleteTarget = ref<any>(null)

// Spec definitions
const specCat = ref<any>(null)
const specModalVisible = ref(false)
const specDefs = ref<any[]>([])
const specEditVisible = ref(false)
const editingSpec = ref<any>(null)
const specForm = ref<any>({ spec_key: '', display_name: '', spec_type: 'string', unit: '', display_group: '', sort_order: 0, options_json: '', is_filterable: true, is_comparable: true })

async function loadCategories() {
  const res = await fetchCategories()
  categories.value = res.categories
}

function openAddCategory() {
  editingCat.value = null
  catForm.value = { name: '', slug: '', parent_id: null, level: 1, sort_order: 0, is_active: true }
  catModalVisible.value = true
}

function openEditCategory(c: any) {
  editingCat.value = c
  catForm.value = { name: c.name, slug: c.slug, parent_id: c.parent_id, level: c.level, sort_order: c.sort_order, is_active: c.is_active }
  catModalVisible.value = true
}

async function saveCategory() {
  try {
    const data = { ...catForm.value }
    if (!data.slug && data.name) data.slug = data.name.toLowerCase().replace(/\s+/g, '-')
    if (editingCat.value) {
      await updateCategory(editingCat.value.id, data)
      showToast('品类已更新', 'success')
    } else {
      await createCategory(data)
      showToast('品类已创建', 'success')
    }
    catModalVisible.value = false
    await loadCategories()
  } catch (e: any) {
    showToast(e.detail || e.message, 'error')
  }
}

function confirmDelete(c: any) { deleteTarget.value = c }

async function doDeleteCategory() {
  if (!deleteTarget.value) return
  try {
    await deleteCategory(deleteTarget.value.id)
    showToast('已删除', 'success')
    deleteTarget.value = null
    await loadCategories()
  } catch (e: any) {
    showToast(e.detail || e.message, 'error')
  }
}

// --- Spec Definitions ---
async function openSpecDefs(c: any) {
  specCat.value = c
  specModalVisible.value = true
  await loadSpecDefs(c.id)
}

async function loadSpecDefs(catId: number) {
  const res = await fetchSpecDefinitions(catId)
  specDefs.value = res.spec_definitions
}

function openAddSpecDef() {
  editingSpec.value = null
  specForm.value = { spec_key: '', display_name: '', spec_type: 'string', unit: '', display_group: '', sort_order: 0, options_json: '', is_filterable: true, is_comparable: true }
  specEditVisible.value = true
}

function openEditSpecDef(s: any) {
  editingSpec.value = s
  specForm.value = {
    spec_key: s.spec_key, display_name: s.display_name, spec_type: s.spec_type,
    unit: s.unit || '', display_group: s.display_group || '', sort_order: s.sort_order,
    options_json: s.options ? JSON.stringify(s.options) : '',
    is_filterable: s.is_filterable, is_comparable: s.is_comparable,
  }
  specEditVisible.value = true
}

async function saveSpecDef() {
  try {
    const data: any = { ...specForm.value }
    if (data.options_json) {
      try { data.options = JSON.parse(data.options_json) } catch { data.options = null }
    } else { data.options = null }
    delete data.options_json

    if (editingSpec.value) {
      await updateSpecDefinition(specCat.value.id, editingSpec.value.id, data)
      showToast('规格已更新', 'success')
    } else {
      await createSpecDefinition(specCat.value.id, data)
      showToast('规格已创建', 'success')
    }
    specEditVisible.value = false
    await loadSpecDefs(specCat.value.id)
  } catch (e: any) {
    showToast(e.detail || e.message, 'error')
  }
}

async function doDeleteSpecDef(s: any) {
  if (!confirm(`删除规格「${s.display_name}」？`)) return
  try {
    await deleteSpecDefinition(specCat.value!.id, s.id)
    showToast('已删除', 'success')
    await loadSpecDefs(specCat.value!.id)
  } catch (e: any) {
    showToast(e.detail || e.message, 'error')
  }
}

onMounted(loadCategories)
</script>
