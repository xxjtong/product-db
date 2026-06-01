<template>
  <div class="flex items-center justify-between mb-16">
    <h1>{{ title }}</h1>
    <div class="flex gap-8">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string }>()
</script>
