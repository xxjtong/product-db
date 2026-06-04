<template>
  <div class="page-header mb-16">
    <div v-if="breadcrumb" class="breadcrumb">
      <router-link v-for="(item, idx) in breadcrumb" :key="idx" :to="item.to" class="breadcrumb-link">
        {{ item.label }}
        <span v-if="idx < breadcrumb.length - 1" class="breadcrumb-sep">›</span>
      </router-link>
    </div>
    <div class="flex items-center justify-between">
      <h1>{{ title }}</h1>
      <div class="flex items-center gap-8 actions">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; breadcrumb?: { label: string; to: string }[] }>()
</script>

<style scoped>
.breadcrumb { display: flex; align-items: center; gap: 4px; margin-bottom: 4px; font-size: 13px; }
.breadcrumb-link { color: var(--color-text-secondary); text-decoration: none; }
.breadcrumb-link:hover { color: var(--color-accent); }
.breadcrumb-sep { margin: 0 4px; color: var(--color-border); }
</style>
