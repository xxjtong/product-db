<template>
  <span :class="['tag', tagClass]" :style="tagStyle">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ label: string }>()

const categoryColors: Record<string,string> = {
  '网关/基站':'tag-lorawan','LoRaWAN网关':'tag-lorawan','蜂窝路由器':'tag-4g','边缘计算网关':'tag-ethernet','多协议网关':'tag-rs485','IoT通用':'tag-default',
  '传感器':'tag-battery','温度传感器':'tag-wifi','湿度传感器':'tag-wifi','空气质量传感器':'tag-mqtt','光照传感器':'tag-nfc','水浸/液位传感器':'tag-5g','门磁/开关传感器':'tag-modbus',
  '执行器/控制器':'tag-poe','阀门/执行器':'tag-poe','开关/继电器':'tag-4g','空调/暖通控制':'tag-wifi',
  '节点/终端':'tag-ethernet','安防':'tag-modbus','视频监控':'tag-ethernet','门禁/访客':'tag-rs485','报警设备':'tag-5g',
  '通信设备':'tag-lorawan','蜂窝模组':'tag-4g','短距通信':'tag-wifi',
  '能耗':'tag-battery','电力监测':'tag-poe','智能照明':'tag-nfc','电源/UPS':'tag-mqtt',
  '会议':'tag-4g','工位':'tag-wifi','信发':'tag-ethernet','智能柜':'tag-modbus','IBMS':'tag-rs485','FM':'tag-default','MTR':'tag-poe',
  '厕位':'tag-5g','厕卫':'tag-5g','环境':'tag-nfc',
  '访客/门禁':'tag-rs485','门禁':'tag-rs485','环境感应器':'tag-wifi','运动传感器':'tag-4g','占用传感器':'tag-mqtt','工业传感器':'tag-poe','安防传感器':'tag-5g',
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
