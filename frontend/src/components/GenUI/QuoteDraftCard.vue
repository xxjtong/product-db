<template>
  <div class="quote-card">
    <div class="quote-header">📋 报价单已生成</div>
    <div class="quote-title">{{ title }}</div>
    <div v-for="(item, i) in items" :key="i" class="quote-row">
      <span class="quote-name">{{ item.product_name }}</span>
      <span class="text-muted text-sm">×{{ item.quantity }}</span>
      <span class="quote-price" v-if="item.unit_price">¥{{ (item.quantity * item.unit_price).toFixed(0) }}</span>
    </div>
    <div class="quote-total">合计 <strong>¥{{ total?.toFixed(0) || 0 }}</strong></div>
    <div class="quote-actions">
      <button class="btn-primary btn-sm" @click="$emit('viewQuote', id)">查看报价单</button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ id?: number; title?: string; total?: number; items?: any[] }>()
defineEmits(['viewQuote'])
</script>

<style scoped>
.quote-card {
  border: 2px solid var(--color-success);
  background: #f0fdf4;
  border-radius: 8px;
  padding: 10px;
  margin-top: 8px;
}
.quote-header { font-size: 13px; font-weight: 600; color: var(--color-success); margin-bottom: 4px; }
.quote-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.quote-row { display: flex; align-items: center; gap: 8px; padding: 2px 0; font-size: 13px; }
.quote-name { flex: 1; }
.quote-price { font-weight: 600; white-space: nowrap; }
.quote-total { text-align: right; padding-top: 8px; margin-top: 8px; border-top: 2px solid var(--color-success); font-size: 14px; }
.quote-actions { display: flex; gap: 8px; margin-top: 8px; }
</style>
