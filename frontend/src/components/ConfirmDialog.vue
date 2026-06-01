<template>
  <div v-if="visible" class="modal-overlay" @click.self="$emit('cancel')">
    <div class="modal-box" style="max-width:400px">
      <div class="modal-header">{{ title }}</div>
      <div class="modal-body">
        <p>{{ message }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn-secondary" @click="$emit('cancel')">取消</button>
        <button class="btn-danger" @click="$emit('confirm')">删除</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; message: string; visible: boolean }>()
defineEmits<{ confirm: []; cancel: [] }>()
</script>
