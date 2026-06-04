<template>
  <span :class="['tag', tagClass]" :style="tagStyle">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ label: string }>()

const tagMap: Record<string, string> = {
  'LoRaWAN': 'tag-lorawan', 'WiFi': 'tag-wifi', '4G': 'tag-4g', '5G': 'tag-5g',
  'Ethernet': 'tag-ethernet', 'RS485': 'tag-rs485', 'Battery': 'tag-battery',
  'PoE': 'tag-poe', 'MQTT': 'tag-mqtt', 'MQTTS': 'tag-mqtt',
  'ModbusRTU': 'tag-modbus', 'ModbusTCP': 'tag-modbus', 'NFC': 'tag-nfc',
}

const palette = ['#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6','#ec4899','#06b6d4','#84cc16','#f97316','#6366f1','#14b8a6','#e11d48','#7c3aed','#0891b2','#a3e635','#d946ef']

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

const tagClass = computed(() => tagMap[props.label] || '')
const tagStyle = computed(() => {
  if (tagMap[props.label]) return {}
  const color = palette[hash(props.label) % palette.length]
  return { background: color + '20', color, borderColor: color + '40' }
})
</script>
