<template>
  <div class="search-input">
    <SearchIcon />
    <input
      type="text"
      :value="modelValue"
      :placeholder="placeholder"
      @input="onInput"
      @compositionstart="composing = true"
      @compositionend="onCompositionEnd"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { SearchIcon } from 'lucide-vue-next'

const props = defineProps<{ modelValue: string; placeholder?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const composing = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

function onInput(e: Event) {
  if (composing.value) return
  emitDebounced((e.target as HTMLInputElement).value)
}

function onCompositionEnd(e: Event) {
  composing.value = false
  emitDebounced((e.target as HTMLInputElement).value)
}

function emitDebounced(val: string) {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => emit('update:modelValue', val), 500)
}
</script>
