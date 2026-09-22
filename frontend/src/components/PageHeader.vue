<template>
  <div class="page-header mb-16">
    <div v-if="breadcrumb" class="breadcrumb">
      <router-link v-for="(item, idx) in breadcrumb" :key="idx" :to="item.to" class="breadcrumb-link">
        {{ item.label }}
        <span v-if="idx < breadcrumb.length - 1" class="breadcrumb-sep">›</span>
      </router-link>
    </div>
    <div class="page-header-row flex items-center justify-between">
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

/* main.css 的 ≤480 规则只作用在 .page-header 自身（标题换行），管不到这一层 flex 行 ——
   结果是「标题 + 操作区」仍被挤在一行里，操作按钮被压到 1~2 字宽、中文逐字竖排。
   真正的收尾要落在这一层：标题独占一行，操作区另起一行并允许换行（375px 实机走查） */
@media (max-width: 480px) {
  .page-header-row { flex-wrap: wrap; gap: 8px; }
  .page-header-row h1 { width: 100%; margin-bottom: 0; }
  .page-header-row .actions { width: 100%; flex-wrap: wrap; }
}
</style>
