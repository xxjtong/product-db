<template>
  <div class="search-input">
    <SearchIcon />
    <input
      ref="inputRef"
      type="text"
      :value="modelValue"
      :placeholder="placeholder"
      @input="onInput"
      @compositionstart="composing = true"
      @compositionend="onCompositionEnd"
    />
    <button v-if="modelValue" class="search-clear" @click="clear">✕</button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { SearchIcon } from 'lucide-vue-next'

const props = defineProps<{ modelValue: string; placeholder?: string; autofocus?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const composing = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

onMounted(() => {
  if (props.autofocus) inputRef.value?.focus()
})
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

function clear() {
  if (timer) clearTimeout(timer)
  emit('update:modelValue', '')
}
</script>

<style scoped>
.search-clear {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  background: var(--color-border);
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.search-clear:hover {
  background: var(--color-text-secondary);
  color: #fff;
}
</style>
