<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-box">
      <div class="modal-header">{{ title }}</div>
      <div class="modal-body"><slot /></div>
      <div v-if="$slots.footer" class="modal-footer"><slot name="footer" /></div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; visible: boolean }>()
defineEmits<{ close: [] }>()
</script>
