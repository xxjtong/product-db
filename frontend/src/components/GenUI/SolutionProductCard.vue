<template>
  <div class="genui-card">
    <div class="genui-header">AI 推荐产品</div>
    <div v-for="p in products" :key="p.id" class="genui-row" @click="toggle(p)">
      <input type="checkbox" :checked="isChecked(p)" @click.stop style="pointer-events:none" />
      <span class="genui-name">{{ p.name }}<span v-if="p.model" class="text-muted text-sm"> {{ p.model }}</span></span>
      <span class="genui-price" v-if="p.price">¥{{ p.price }}</span>
      <span class="genui-qty">
        数量 <input v-model.number="qtys[p.id]" type="number" min="1" max="999" style="width:50px" @click.stop />
      </span>
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
  border-left: 3px solid var(--color-accent);
  background: var(--color-card);
  border-radius: 6px;
  padding: 8px;
  margin-top: 8px;
}
.genui-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-accent);
  margin-bottom: 6px;
}
.genui-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  font-size: 13px;
}
.genui-row:last-child { border-bottom: none; }
.genui-row:hover { background: var(--color-hover); }
.genui-name { flex: 1; font-weight: 500; }
.genui-price { font-weight: 600; white-space: nowrap; }
.genui-qty { font-size: 12px; display: flex; align-items: center; gap: 4px; }
.genui-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px solid var(--color-border);
}
</style>
