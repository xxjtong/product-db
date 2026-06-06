<template>
  <div v-if="loading" class="empty-state"><p>加载中...</p></div>
  <div v-else-if="error" class="empty-state">
    <p style="color:var(--color-danger)">{{ error }}</p>
    <button v-if="retry" class="btn-secondary btn-sm" style="margin-top:8px" @click="$emit('retry')">重试</button>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
defineProps<{ loading?: boolean; error?: string; retry?: boolean }>()
defineEmits(['retry'])
</script>
