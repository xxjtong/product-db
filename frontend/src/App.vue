<template>
  <div class="toast-container">
    <div v-if="toast" :class="['toast', toast.type === 'success' ? 'toast-success' : toast.type === 'error' ? 'toast-error' : '']">
      {{ toast.message }}
    </div>
  </div>
  <div class="app-layout">
    <aside v-if="$route.path !== '/login'" class="app-sidebar" :class="{ collapsed: sidebarCollapsed }">
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
      <!-- User section -->
      <div v-if="currentUser" class="sidebar-user" v-show="!sidebarCollapsed">
        <div class="sidebar-user-info">
          <span class="sidebar-username">{{ currentUser.username }}</span>
          <span class="sidebar-email">{{ currentUser.email || '未设置邮箱' }}</span>
        </div>
        <div class="sidebar-user-actions">
          <button class="btn-icon btn-sm" title="修改密码" @click="showPwdModal = true"><KeyIcon style="width:14px;height:14px" /></button>
          <button class="btn-icon btn-sm" title="登出" @click="logout"><LogOutIcon style="width:14px;height:14px" /></button>
        </div>
      </div>
    </aside>
    <main class="app-content">
      <router-view />
    </main>
  </div>
  <AiChat v-if="$route.path !== '/login'" />

  <!-- Password change modal -->
  <div v-if="showPwdModal" class="modal-overlay" @click.self="showPwdModal = false">
    <div class="modal-card" style="width:360px">
      <h3 style="margin:0 0 12px">修改密码</h3>
      <div class="form-group"><label>新密码</label><input v-model="newPassword" type="password" /></div>
      <div class="form-group"><label>确认密码</label><input v-model="newPassword2" type="password" /></div>
      <p v-if="pwdError" style="color:var(--color-danger);font-size:12px">{{ pwdError }}</p>
      <div class="flex gap-8 mt-8" style="justify-content:flex-end">
        <button class="btn-secondary btn-sm" @click="showPwdModal = false">取消</button>
        <button class="btn-primary btn-sm" @click="changePassword">确认</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, provide, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PackageIcon, GridIcon, BookIcon, TruckIcon, ClipboardListIcon, FileTextIcon, ShieldIcon, KeyIcon, LogOutIcon } from 'lucide-vue-next'
import AiChat from './components/AiChat.vue'

const router = useRouter()

interface ToastMsg { message: string; type: string }
const sidebarCollapsed = ref(false)
const toast = ref<ToastMsg | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null
const showPwdModal = ref(false)
const newPassword = ref('')
const newPassword2 = ref('')
const pwdError = ref('')

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

async function loadSession() {
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
}

function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  currentUser.value = null
  router.push('/login')
}

async function changePassword() {
  pwdError.value = ''
  if (!newPassword.value || newPassword.value.length < 6) { pwdError.value = '密码至少6位'; return }
  if (newPassword.value !== newPassword2.value) { pwdError.value = '两次密码不一致'; return }
  try {
    const token = localStorage.getItem('token')
    const res = await fetch('/api/auth/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ password: newPassword.value }),
    })
    if (!res.ok) throw new Error('修改失败')
    showToast('密码已修改', 'success')
    showPwdModal.value = false
    newPassword.value = ''
    newPassword2.value = ''
  } catch (e: any) { pwdError.value = e.message }
}

onMounted(loadSession)
</script>

<style scoped>
.sidebar-user {
  margin-top: auto;
  border-top: 1px solid rgba(255,255,255,.15);
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.sidebar-user-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-username {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sidebar-email {
  font-size: 11px;
  opacity: .6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sidebar-user-actions {
  display: flex;
  gap: 4px;
}
.sidebar-user-actions button {
  color: rgba(255,255,255,.6);
}
.sidebar-user-actions button:hover {
  color: #fff;
}

/* Password modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.5);
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-card {
  background: #fff;
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: var(--shadow-lg);
}
</style>
