<template>
  <div class="pagination" v-if="total > perPage">
    <span>共 {{ total }} 条</span>
    <button :disabled="page <= 1" @click="$emit('change', page - 1)">上一页</button>
    <span class="page-nav">
      <input
        v-model="jumpPage"
        type="text"
        inputmode="numeric"
        @keyup.enter="doJump"
        class="page-input"
      />
      <span class="page-sep">/ {{ totalPages }}</span>
      <button class="btn-sm btn-go" @click="doJump">跳转</button>
    </span>
    <button :disabled="page >= totalPages" @click="$emit('change', page + 1)">下一页</button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{ total: number; page: number; perPage: number }>()
const emit = defineEmits<{ change: [page: number] }>()

const totalPages = computed(() => Math.ceil(props.total / props.perPage))
const jumpPage = ref(String(props.page))

watch(() => props.page, (p) => {
  jumpPage.value = String(p)
})

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
  gap: 4px;
}
.page-input {
  width: 44px;
  height: 28px;
  text-align: center;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 13px;
  padding: 0 6px;
}
.page-sep {
  font-size: 13px;
}
.btn-go {
  width: 36px;
  height: 28px;
  padding: 0;
  font-size: 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-surface);
  cursor: pointer;
}
.btn-go:hover {
  background: var(--color-border);
}
</style>