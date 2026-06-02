<template>
  <div class="pagination" v-if="total > perPage">
    <span>共 {{ total }} 条</span>
    <button :disabled="page <= 1" @click="$emit('change', page - 1)">上一页</button>
    <span class="page-nav">
      <span class="page-info">{{ page }} / {{ totalPages }}</span>
      <input v-model="jumpPage" type="text" inputmode="numeric" @keyup.enter="doJump" class="page-input" placeholder="页码" />
      <button @click="doJump">跳转</button>
    </span>
    <button :disabled="page >= totalPages" @click="$emit('change', page + 1)">下一页</button>
    <select v-model="localPerPage" @change="onPerPageChange" class="page-size-select">
      <option v-for="n in pageSizes" :key="n" :value="n">{{ n === 0 ? '全部' : n }}</option>
    </select>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{ total: number; page: number; perPage: number }>()
const emit = defineEmits<{ change: [page: number]; 'update:perPage': [perPage: number] }>()

const pageSizes = [10, 20, 50, 100, 0]
const totalPages = computed(() => props.perPage > 0 ? Math.ceil(props.total / props.perPage) : 1)
const jumpPage = ref(String(props.page))
const localPerPage = ref(props.perPage)

watch(() => props.page, (p) => { jumpPage.value = String(p) })
watch(() => props.perPage, (p) => { localPerPage.value = p })

function onPerPageChange() {
  emit('update:perPage', localPerPage.value)
}

function doJump() {
  const n = parseInt(jumpPage.value)
  if (!isNaN(n) && n >= 1 && n <= totalPages.value && n !== props.page) {
    emit('change', n)
  } else {
    jumpPage.value = String(props.page)
  }
}
</script>

<style scoped>
.page-nav {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.page-info {
  font-size: 13px;
  color: var(--color-text-secondary);
}
.page-input {
  width: 44px;
  height: 28px;
  text-align: center;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 13px;
  padding: 0 6px;
  line-height: 28px;
}
.page-size-select {
  height: 28px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 12px;
  padding: 0 4px;
  background: var(--color-card);
  color: var(--color-text);
}
</style>
