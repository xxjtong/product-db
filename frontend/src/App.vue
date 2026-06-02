<template>
  <div class="toast-container">
    <div v-if="toast" :class="['toast', toast.type === 'success' ? 'toast-success' : toast.type === 'error' ? 'toast-error' : '']">
      {{ toast.message }}
    </div>
  </div>
  <div class="app-layout">
    <aside class="app-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-logo" @click="sidebarCollapsed = !sidebarCollapsed" style="cursor:pointer">{{ sidebarCollapsed ? 'PD' : '产品数据库' }}</div>
      <nav class="sidebar-nav">
        <router-link to="/products" class="sidebar-link" :title="sidebarCollapsed ? '产品' : ''"><PackageIcon /><span v-show="!sidebarCollapsed">产品</span></router-link>
        <router-link to="/categories" class="sidebar-link" :title="sidebarCollapsed ? '品类' : ''"><GridIcon /><span v-show="!sidebarCollapsed">品类</span></router-link>
        <router-link to="/dictionaries" class="sidebar-link" :title="sidebarCollapsed ? '字典' : ''"><BookIcon /><span v-show="!sidebarCollapsed">字典</span></router-link>
        <router-link to="/suppliers" class="sidebar-link" :title="sidebarCollapsed ? '供应商' : ''"><TruckIcon /><span v-show="!sidebarCollapsed">供应商</span></router-link>
        <router-link to="/solutions" class="sidebar-link" :title="sidebarCollapsed ? '方案' : ''"><ClipboardListIcon /><span v-show="!sidebarCollapsed">方案</span></router-link>
        <router-link to="/quotations" class="sidebar-link" :title="sidebarCollapsed ? '报价单' : ''"><FileTextIcon /><span v-show="!sidebarCollapsed">报价单</span></router-link>
        <router-link to="/admin" class="sidebar-link" :title="sidebarCollapsed ? '管理' : ''"><ShieldIcon /><span v-show="!sidebarCollapsed">管理</span></router-link>
      </nav>
    </aside>
    <main class="app-content">
      <router-view />
    </main>
  </div>
  <AiChat />
</template>

<script setup lang="ts">
import { ref, provide, onMounted } from 'vue'
import { PackageIcon, GridIcon, BookIcon, TruckIcon, ClipboardListIcon, FileTextIcon, ShieldIcon } from 'lucide-vue-next'
import AiChat from './components/AiChat.vue'

interface ToastMsg { message: string; type: string }
const sidebarCollapsed = ref(false)
const toast = ref<ToastMsg | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(message: string, type = 'info') {
  toast.value = { message, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 3000)
}

provide('toast', showToast)

// Load session data on mount
const currentUser = ref<any>(null)
const fieldVisibility = ref<Record<string, boolean>>({})
provide('currentUser', currentUser)
provide('fieldVisibility', fieldVisibility)

onMounted(async () => {
  try {
    const token = localStorage.getItem('token')
    if (!token) return
    const res = await fetch('/api/auth/session', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    if (!res.ok) return
    const data = await res.json()
    currentUser.value = data.user
    fieldVisibility.value = data.field_visibility || {}
  } catch { /* ignore */ }
})
</script>
