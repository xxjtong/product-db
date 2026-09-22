<template>
  <div class="quote-card">
    <div class="quote-header">
      📋 报价单预览<span class="quote-hint">（尚未生成）</span>
    </div>
    <div class="quote-title">{{ title || '未命名方案' }}</div>
    <div v-if="client_name" class="quote-client">客户：{{ client_name }}</div>
    <div v-for="(item, i) in items" :key="i" class="quote-row">
      <span class="quote-name">
        {{ item.name }}<span v-if="item.model" class="quote-model">（{{ item.model }}）</span>
      </span>
      <span class="text-muted text-sm">×{{ item.quantity }}</span>
      <span class="quote-price">¥{{ money(item.amount) }}</span>
    </div>
    <div v-if="newItems.length" class="quote-new">
      同时并入方案：{{ newItems.map(n => n.name).join('、') }}
    </div>
    <div class="quote-total">
      合计 <strong>¥{{ money(total) }}</strong>
      <span class="text-muted text-sm">（{{ items?.length || 0 }} 项）</span>
    </div>
    <div class="quote-actions">
      <button class="btn-primary btn-sm" :disabled="busy || doneId !== null" @click="onConfirm">
        {{ busy ? '生成中...' : (doneId !== null ? `已生成 #${doneId}` : '确认生成') }}
      </button>
      <span v-if="error" class="quote-error">{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { createQuotation } from '../../api'

// 这是**预览**卡，不是"已生成"卡：后端只算不写（R71），用户在卡上点确认才落库。
// 以前后端直接建单、这里只展示结果，用户还没表态方案就先被改了。
const props = defineProps<{
  solution_id?: number
  title?: string
  client_name?: string
  items?: any[]
  new_items?: any[]
  total?: number
  count?: number
}>()

const emit = defineEmits(['created'])

const busy = ref(false)
const error = ref('')
const doneId = ref<number | null>(null)
const newItems = computed(() => props.new_items || [])

function money(v: any): string {
  return Math.round(Number(v) || 0).toLocaleString()
}

async function onConfirm() {
  if (busy.value || doneId.value !== null) return
  if (!props.solution_id) {
    error.value = '缺少方案信息，请在方案详情页操作'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const res = await createQuotation({
      solution_id: props.solution_id,
      // 预览里展示过、尚未进方案的产品，确认时一并并入（后端会跳过方案里已有的）
      extra_items: newItems.value.map(n => ({ product_id: n.product_id, quantity: n.quantity })),
    }) as any
    doneId.value = res?.quotation?.id ?? null
    emit('created', doneId.value)
  } catch (e: any) {
    error.value = e?.detail || e?.message || '生成失败'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.quote-card {
  border: 2px dashed var(--color-warning, #d97706);
  background: #fffbeb;
  border-radius: 8px;
  padding: 10px;
  margin-top: 8px;
}
.quote-header { font-size: 13px; font-weight: 600; color: var(--color-warning, #b45309); margin-bottom: 4px; }
.quote-hint { font-weight: 400; color: var(--color-text-secondary); margin-left: 4px; }
.quote-title { font-size: 14px; font-weight: 600; margin-bottom: 2px; }
.quote-client { font-size: 12px; color: var(--color-text-secondary); margin-bottom: 6px; }
.quote-row { display: flex; align-items: center; gap: 8px; padding: 2px 0; font-size: 13px; }
.quote-name { flex: 1; }
.quote-model { color: var(--color-text-secondary); font-size: 12px; }
.quote-price { font-weight: 600; white-space: nowrap; }
.quote-new {
  font-size: 12px; color: var(--color-warning, #b45309);
  background: rgba(217, 119, 6, 0.08); border-radius: 4px;
  padding: 4px 6px; margin-top: 6px;
}
.quote-total { text-align: right; padding-top: 8px; margin-top: 8px; border-top: 2px solid var(--color-warning, #d97706); font-size: 14px; }
.quote-actions { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.quote-error { font-size: 12px; color: var(--color-danger); }
</style>
