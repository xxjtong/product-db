<template>
  <span :class="['tag', tagClass]">{{ label }}</span>
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

const tagClass = computed(() => tagMap[props.label] || 'tag-default')
</script>
