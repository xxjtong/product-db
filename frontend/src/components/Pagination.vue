<template>
  <div class="pagination" v-if="total > perPage">
    <span>共 {{ total }} 条</span>
    <button :disabled="page <= 1" @click="$emit('change', page - 1)">上一页</button>
    <span>{{ page }} / {{ totalPages }}</span>
    <button :disabled="page >= totalPages" @click="$emit('change', page + 1)">下一页</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ total: number; page: number; perPage: number }>()
defineEmits<{ change: [page: number] }>()

const totalPages = computed(() => Math.ceil(props.total / props.perPage))
</script>
