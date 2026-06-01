<template>
  <div class="genui-card">
    <div class="genui-header">🤖 AI 推荐产品</div>
    <div v-for="p in products" :key="p.id" class="genui-row">
      <input type="checkbox" :checked="isChecked(p)" @change="toggle(p)" />
      <span class="genui-name">{{ p.name }}<span v-if="p.model" class="text-muted text-sm"> {{ p.model }}</span></span>
      <span class="genui-price" v-if="p.price">¥{{ p.price }}</span>
      <input v-model.number="qtys[p.id]" type="number" min="1" max="999" style="width:56px;text-align:center" @click.stop />
    </div>
    <div v-if="checkedList.length" class="genui-actions">
      <button class="btn-primary btn-sm" @click="$emit('addToBom', checkedList.map(id => ({ id, qty: qtys[id] || 1 })))">
        加入方案 ({{ checkedList.length }})
      </button>
      <button class="btn-secondary btn-sm" @click="$emit('compare', checkedList)" :disabled="checkedList.length < 2">
        对比 {{ checkedList.length >= 2 ? checkedList.length : '' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'

const props = defineProps<{ products: any[] }>()
defineEmits(['addToBom', 'compare'])

const checked = ref<number[]>([])
const qtys = reactive<Record<number, number>>({})

const checkedList = computed(() => checked.value)

for (const p of props.products) {
  if (!(p.id in qtys)) qtys[p.id] = 1
}

function toggle(p: any) {
  const idx = checked.value.indexOf(p.id)
  if (idx >= 0) checked.value.splice(idx, 1)
  else checked.value.push(p.id)
}

function isChecked(p: any) {
  return checked.value.includes(p.id)
}
</script>

<style scoped>
.genui-card {
  border: 2px solid var(--color-accent);
  background: #f0f4ff;
  border-radius: 8px;
  padding: 10px;
  margin-top: 8px;
}
.genui-header {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-accent);
  margin-bottom: 8px;
}
.genui-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 8px;
  border-bottom: 1px solid var(--color-border);
  font-size: 13px;
  background: #fff;
  border-radius: 4px;
  margin-bottom: 4px;
}
.genui-row:last-child { margin-bottom: 0; }
.genui-row input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; flex-shrink: 0; }
.genui-name { flex: 1; font-weight: 500; min-width: 0; }
.genui-price { font-weight: 600; white-space: nowrap; color: var(--color-danger); flex-shrink: 0; }
.genui-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border);
}
</style>
