<template>
  <div class="page-header flex items-center justify-between mb-16">
    <h1>{{ title }}</h1>
    <div class="flex gap-8 actions">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string }>()
</script>
