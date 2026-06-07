<template>
  <div class="dependency-editor">
    <div class="flex justify-between items-center" style="margin-bottom:12px">
      <h3 style="margin:0">依赖关系</h3>
      <button class="btn-primary btn-sm" @click="showAdd = true">+ 添加</button>
    </div>

    <table v-if="deps.length" class="data-table">
      <thead><tr><th>类型</th><th>目标</th><th>描述</th><th></th></tr></thead>
      <tbody>
        <tr v-for="d in deps" :key="d.id">
          <td>
            <select v-model="d.dependency_type" @change="updateDep(d)" class="inline-select">
              <option value="required">必须</option>
              <option value="recommended">推荐</option>
              <option value="optional">可选</option>
            </select>
          </td>
          <td>
            <span v-if="d.depends_on_product_id">{{ getProductName(d.depends_on_product_id) || '产品 #' + d.depends_on_product_id }}</span>
            <span v-else-if="d.depends_on_category_id">{{ getCategoryName(d.depends_on_category_id) || '品类 #' + d.depends_on_category_id }}</span>
          </td>
          <td>
            <input v-model="d.description" style="width:200px;font-size:12px" @change="updateDep(d)" />
          </td>
          <td><button class="btn-icon btn-sm" @click="deleteDep(d.id)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button></td>
        </tr>
      </tbody>
    </table>
    <div v-else class="text-sm text-muted">暂无依赖</div>
    <div style="border-bottom:1px solid var(--color-border);margin:12px 0"></div>

    <!-- Add form -->
    <div v-if="showAdd" class="card" style="padding:12px;margin-top:8px">
      <div class="form-grid" style="gap:8px">
        <div>
          <label class="text-sm text-muted">类型</label>
          <select v-model="newDep.dependency_type" class="inline-select">
            <option value="required">必须</option>
            <option value="recommended">推荐</option>
            <option value="optional">可选</option>
          </select>
        </div>
        <div>
          <label class="text-sm text-muted">依赖目标</label>
          <select v-model="depTargetType" style="margin-right:4px">
            <option value="category">品类</option>
            <option value="product">产品</option>
          </select>
          <select v-if="depTargetType === 'category'" v-model="newDep.depends_on_category_id">
            <option :value="null">选择品类...</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
          <select v-else v-model="newDep.depends_on_product_id">
            <option :value="null">选择产品...</option>
            <option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }} ({{ p.model }})</option>
          </select>
        </div>
        <div>
          <label class="text-sm text-muted">描述</label>
          <input v-model="newDep.description" style="width:200px" placeholder="如: 需要LoRaWAN网关" />
        </div>
      </div>
      <div class="flex gap-8 mt-8">
        <button class="btn-primary btn-sm" @click="addDep" :disabled="!canAdd">确认</button>
        <button class="btn-secondary btn-sm" @click="showAdd = false">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, inject } from 'vue'
import { Trash2Icon } from 'lucide-vue-next'
import { fetchCategories, fetchProducts, fetchDependencies, createDependency, updateDependency, deleteDependency } from '../api'

const props = defineProps<{ productId: number }>()
const emit = defineEmits<{ change: [] }>()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

const deps = ref<any[]>([])
const categories = ref<any[]>([])
const products = ref<any[]>([])
const showAdd = ref(false)
const depTargetType = ref<'category' | 'product'>('category')

const newDep = ref<{
  dependency_type: string
  depends_on_product_id: number | null
  depends_on_category_id: number | null
  description: string
}>({
  dependency_type: 'required',
  depends_on_product_id: null,
  depends_on_category_id: null,
  description: '',
})

function getCategoryName(id: number): string {
  return categories.value.find((c: any) => c.id === id)?.name || ''
}
function getProductName(id: number): string {
  const p = products.value.find((p: any) => p.id === id)
  return p ? `${p.name} (${p.model || ''})` : ''
}

const canAdd = computed(() => {
  if (depTargetType.value === 'category') return !!newDep.value.depends_on_category_id
  return !!newDep.value.depends_on_product_id
})

function resetNewDep() {
  newDep.value = { dependency_type: 'required', depends_on_product_id: null, depends_on_category_id: null, description: '' }
  depTargetType.value = 'category'
}

async function loadDeps() {
  try {
    const res = await fetchDependencies(props.productId)
    deps.value = res.dependencies || []
  } catch { deps.value = [] }
}

async function loadOptions() {
  const [catRes, prodRes] = await Promise.all([fetchCategories(), fetchProducts('per_page=500')])
  categories.value = catRes.categories
  products.value = prodRes.products
}

async function addDep() {
  if (!props.productId) { showToast('请先保存产品', 'error'); return }
  const data: any = {
    dependency_type: newDep.value.dependency_type,
    description: newDep.value.description,
  }
  if (depTargetType.value === 'category') {
    data.depends_on_category_id = newDep.value.depends_on_category_id
  } else {
    data.depends_on_product_id = newDep.value.depends_on_product_id
  }
  try {
    await createDependency(props.productId, data)
    showToast('依赖已添加', 'success')
    showAdd.value = false
    resetNewDep()
    await loadDeps()
    emit('change')
  } catch (e: any) {
    showToast('添加失败', 'error')
  }
}

async function updateDep(d: any) {
  try {
    await updateDependency(props.productId, d.id, {
      dependency_type: d.dependency_type,
      description: d.description,
    })
    emit('change')
  } catch (e: any) {
    showToast('更新失败', 'error')
  }
}

async function deleteDep(depId: number) {
  try {
    await deleteDependency(props.productId, depId)
    showToast('已删除', 'success')
    await loadDeps()
    emit('change')
  } catch (e: any) {
    showToast('删除失败', 'error')
  }
}

onMounted(async () => {
  await loadOptions()
  if (props.productId > 0) await loadDeps()
})
</script>

<style scoped>
.inline-select {
  font-size: 12px;
  padding: 2px 4px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
}
.form-grid {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
}
.form-grid > div {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
</style>
