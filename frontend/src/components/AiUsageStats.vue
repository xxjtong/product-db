<template>
  <div class="card mb-16">
    <h3>AI 用量统计</h3>
    <div class="flex gap-16 mb-8" v-if="usage">
      <div class="stat"><span class="stat-num">{{ usage.summary?.total || 0 }}</span><span class="stat-label">总次数</span></div>
      <div class="stat"><span class="stat-num">{{ formatNum(usage.summary?.total_tokens_in || 0) }}</span><span class="stat-label">总输入Token</span></div>
      <div class="stat"><span class="stat-num">{{ formatNum(usage.summary?.total_tokens_out || 0) }}</span><span class="stat-label">总输出Token</span></div>
      <div class="stat"><span class="stat-num" style="color:var(--color-success)">{{ usage.summary?.success || 0 }}</span><span class="stat-label">成功</span></div>
      <div class="stat"><span class="stat-num">{{ usage.by_op?.length || 0 }}</span><span class="stat-label">操作类型</span></div>
    </div>
    <!-- Operation breakdown -->
    <div v-if="usage?.by_op?.length" class="mb-8">
      <span class="text-sm text-muted">按操作: </span>
      <span v-for="(op, i) in usage.by_op" :key="op.operation" class="tag" style="font-size:11px">
        {{ opLabels[op.operation] || op.operation }} {{ op.count }}
      </span>
    </div>
    <div class="text-sm text-muted mb-4">最近使用记录</div>
    <div v-if="usage?.recent?.length" style="max-height:200px;overflow-y:auto">
      <table class="data-table">
        <thead><tr><th>用户</th><th>操作</th><th>输入Token</th><th>输出Token</th><th>耗时</th><th>状态</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="r in usage.recent" :key="r.id">
            <td>{{ r.username || r.user_id }}</td>
            <td><span class="text-xs">{{ opLabels[r.operation] || r.operation }}</span></td>
            <td class="font-mono">{{ r.tokens_in || 0 }}</td>
            <td class="font-mono">{{ r.tokens_out || 0 }}</td>
            <td class="font-mono">{{ r.duration_ms }}ms</td>
            <td :style="{color: r.success ? 'var(--color-success)' : 'var(--color-danger)'}">{{ r.success ? '✓' : '✗' }}</td>
            <td class="text-xs">{{ formatTime(r.created_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="text-sm text-muted">暂无使用记录</p>
    <div v-if="(usage?.summary?.total || 0) > 10" class="mt-8">
      <button class="btn-secondary btn-sm" @click="$emit('refresh')">刷新</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { formatTime } from '../utils/time'
defineProps<{ usage: any }>()
defineEmits(['refresh'])

const opLabels: Record<string,string> = {
  chat: 'AI 对话', ai_fetch: 'URL 提取', ai_fetch_text: '文本提取',
  ai_fetch_file: '文件提取', ai_ocr: '图片 OCR',
}

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}
</script>
