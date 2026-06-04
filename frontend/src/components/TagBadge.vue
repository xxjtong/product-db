<template>
  <span class="tag" :style="tagStyle">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ label: string }>()

const palette = [
  '#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899',
  '#06b6d4','#84cc16','#f97316','#6366f1','#14b8a6','#e11d48',
  '#7c3aed','#0891b2','#a3e635','#d946ef','#0ea5e9','#22c55e',
  '#eab308','#f43f5e','#a855f7','#d946ef','#14b8a6','#e11d48',
]

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

const tagStyle = computed(() => {
  const color = palette[hash(props.label) % palette.length]
  return { background: color + '20', color, borderColor: color + '40' }
})
</script>
