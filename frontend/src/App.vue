<template>
  <div v-if="toast" :class="['toast', toast.type === 'success' ? 'toast-success' : toast.type === 'error' ? 'toast-error' : '']">
    {{ toast.message }}
  </div>
  <div class="app-layout">
    <aside class="app-sidebar">
      <div class="sidebar-logo">产品数据库</div>
      <nav class="sidebar-nav">
        <router-link to="/products" class="sidebar-link"><PackageIcon />产品</router-link>
        <router-link to="/categories" class="sidebar-link"><GridIcon />品类</router-link>
        <router-link to="/dictionaries" class="sidebar-link"><BookIcon />字典</router-link>
        <router-link to="/suppliers" class="sidebar-link"><TruckIcon />供应商</router-link>
        <router-link to="/solutions" class="sidebar-link"><ClipboardListIcon />方案</router-link>
        <router-link to="/quotations" class="sidebar-link"><FileTextIcon />报价单</router-link>
      </nav>
    </aside>
    <main class="app-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, provide } from 'vue'
import { PackageIcon, GridIcon, BookIcon, TruckIcon, ClipboardListIcon, FileTextIcon } from 'lucide-vue-next'

interface ToastMsg { message: string; type: string }
const toast = ref<ToastMsg | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(message: string, type = 'info') {
  toast.value = { message, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 3000)
}

provide('toast', showToast)
</script>
