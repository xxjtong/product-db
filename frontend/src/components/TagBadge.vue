<template>
  <span :class="['tag', tagClass]" :style="tagStyle">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ label: string }>()

const categoryColors: Record<string,string> = {
  '网关/基站':'tag-cat-gateway','LoRaWAN网关':'tag-cat-gateway','蜂窝路由器':'tag-cat-gateway','边缘计算网关':'tag-cat-gateway','多协议网关':'tag-cat-gateway',
  '传感器':'tag-cat-sensor','温度传感器':'tag-cat-sensor','湿度传感器':'tag-cat-sensor','空气质量传感器':'tag-cat-sensor','光照传感器':'tag-cat-sensor','水浸/液位传感器':'tag-cat-sensor','门磁/开关传感器':'tag-cat-sensor','环境感应器':'tag-cat-sensor','运动传感器':'tag-cat-sensor','占用传感器':'tag-cat-sensor','工业传感器':'tag-cat-sensor','安防传感器':'tag-cat-sensor',
  '执行器/控制器':'tag-cat-controller','阀门/执行器':'tag-cat-controller','开关/继电器':'tag-cat-controller','空调/暖通控制':'tag-cat-controller',
  '节点/终端':'tag-cat-node',
  '安防':'tag-cat-security','视频监控':'tag-cat-security','门禁/访客':'tag-cat-security','报警设备':'tag-cat-security',
  '通信设备':'tag-cat-comm','蜂窝模组':'tag-cat-comm','短距通信':'tag-cat-comm',
  '能耗':'tag-cat-energy','电力监测':'tag-cat-energy','智能照明':'tag-cat-energy','电源/UPS':'tag-cat-energy',
  '会议':'tag-cat-meeting','工位':'tag-cat-workspace','信发':'tag-cat-display','智能柜':'tag-cat-workspace',
  'IBMS':'tag-cat-other','FM':'tag-cat-other','MTR':'tag-cat-other','IoT通用':'tag-cat-other',
  '厕位':'tag-cat-toilet','厕卫':'tag-cat-toilet','环境':'tag-cat-env','访客/门禁':'tag-cat-security','门禁':'tag-cat-security',
}
const tagMap: Record<string, string> = {
  'LoRaWAN': 'tag-lorawan', 'WiFi': 'tag-wifi', '4G': 'tag-4g', '5G': 'tag-5g',
  'Ethernet': 'tag-ethernet', 'RS485': 'tag-rs485', 'Battery': 'tag-battery',
  'PoE': 'tag-poe', 'MQTT': 'tag-mqtt', 'MQTTS': 'tag-mqtt',
  'ModbusRTU': 'tag-modbus', 'ModbusTCP': 'tag-modbus', 'NFC': 'tag-nfc',
  ...categoryColors,
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
