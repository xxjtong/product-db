<template>
  <div class="toast-container">
    <div v-if="toast" :class="['toast', toast.type === 'success' ? 'toast-success' : toast.type === 'error' ? 'toast-error' : '']">
      <span v-if="toast.type === 'success'">✅</span><span v-else-if="toast.type === 'error'">❌</span><span v-else>ℹ️</span> {{ toast.message }}
    </div>
  </div>
  <div class="app-layout">
    <aside v-if="$route.path !== '/login'" class="app-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-logo" @click="sidebarCollapsed = !sidebarCollapsed">{{ sidebarCollapsed ? 'PD' : '产品数据库' }}</div>
      <div v-show="!sidebarCollapsed" class="sidebar-search">
        <input v-model="globalSearch" placeholder="搜索产品..." @keyup.enter="doGlobalSearch" />
      </div>
      <nav class="sidebar-nav">
        <router-link to="/products" class="sidebar-link" :title="sidebarCollapsed ? '产品' : ''"><PackageIcon /><span v-show="!sidebarCollapsed">产品</span></router-link>
        <router-link to="/solutions" class="sidebar-link" :title="sidebarCollapsed ? '方案' : ''"><ClipboardListIcon /><span v-show="!sidebarCollapsed">方案</span></router-link>
        <router-link to="/quotations" class="sidebar-link" :title="sidebarCollapsed ? '报价单' : ''"><FileTextIcon /><span v-show="!sidebarCollapsed">报价单</span></router-link>

        <router-link to="/dictionaries" class="sidebar-link" :title="sidebarCollapsed ? '字典' : ''"><BookIcon /><span v-show="!sidebarCollapsed">字典</span></router-link>
        <router-link v-if="currentUser?.role === 'admin'" to="/admin" class="sidebar-link" :title="sidebarCollapsed ? '管理' : ''"><ShieldIcon /><span v-show="!sidebarCollapsed">管理</span></router-link>
      </nav>
      <!-- AI stats -->
      <div v-if="aiStats" class="sidebar-stats" :class="{ collapsed: sidebarCollapsed }">
        <div class="sidebar-stats-row">
          <span class="sidebar-stats-num">{{ aiStats.user_count.toLocaleString() }}</span>
          <span class="sidebar-stats-label">次AI</span>
        </div>
        <div class="sidebar-stats-row">
          <span class="sidebar-stats-num">{{ formatTokens(aiStats.user_tokens_in + (aiStats.user_tokens_out ?? 0)) }}</span>
          <span class="sidebar-stats-label">Token</span>
        </div>
      </div>
      <div v-show="!sidebarCollapsed" class="sidebar-version">v2.0</div>
      <!-- User section -->
      <div v-if="currentUser" class="sidebar-user" ref="userMenuRef">
        <button class="sidebar-user-btn" @click="showUserMenu = !showUserMenu">
          <UserIcon :size="14" color="rgba(255, 255, 255, 0.85)" style="flex-shrink:0" />
          <span v-show="!sidebarCollapsed" class="sidebar-username">{{ currentUser.username }}</span>
        </button>
        <div v-if="showUserMenu" class="user-dropdown">
          <button class="user-dropdown-item" @click="showUserMenu = false; openProfile()"><UserCircleIcon :size="14" />个人信息</button>
          <button class="user-dropdown-item user-dropdown-item--danger" @click="showUserMenu = false; showLogout = true"><LogOutIcon :size="14" />退出</button>
        </div>
      </div>
    </aside>
    <main class="app-content">
      <router-view />
    </main>
  </div>
  <AiChat v-if="$route.path !== '/login'" />

  <!-- Profile modal -->
  <Teleport to="body">
    <div v-if="showProfile" class="modal-overlay" @click.self="showProfile = false">
      <div class="modal-card" style="width:400px">
        <div class="modal-header">
          <h3 style="margin:0">个人信息</h3>
          <button class="btn-icon" @click="showProfile = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group"><label>用户名</label><input :value="currentUser?.username || ''" disabled /></div>
          <div class="form-group"><label>角色</label><input :value="currentUser?.role === 'admin' ? '管理员' : '普通用户'" disabled /></div>
          <div class="form-group"><label>邮箱</label><input v-model="profileEmail" placeholder="选填" /></div>
          <hr style="margin:12px 0;border:none;border-top:1px solid var(--color-border)" />
          <div class="form-group"><label>当前密码 <span style="color:var(--color-danger)">*</span></label><input v-model="profileCurPw" type="password" placeholder="修改邮箱或密码需验证" /></div>
          <div class="form-group"><label>新密码 <span class="text-muted">（留空不修改）</span></label><input v-model="profileNewPw" type="password" placeholder="至少6位" /></div>
          <p v-if="profileError" style="color:var(--color-danger);font-size:12px;margin:8px 0 0">{{ profileError }}</p>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="showProfile = false">取消</button>
          <button class="btn-primary" @click="saveProfile">保存</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Logout modal -->
  <Teleport to="body">
    <div v-if="showLogout" class="modal-overlay" @click.self="showLogout = false">
      <div class="modal-card" style="width:320px;text-align:center;padding:32px 24px 24px">
        <h3 style="margin:0 0 8px">确认退出</h3>
        <p class="text-muted text-sm" style="margin-bottom:32px">确定要退出登录吗？</p>
        <div class="flex gap-8" style="justify-content:center;padding-bottom:0">
          <button class="btn-secondary" @click="showLogout = false">取消</button>
          <button class="btn-primary" style="background:var(--color-danger)" @click="logout">退出</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, provide, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { PackageIcon, BookIcon, ClipboardListIcon, FileTextIcon, ShieldIcon, UserIcon, UserCircleIcon, LogOutIcon } from 'lucide-vue-next'
import AiChat from './components/AiChat.vue'

const router = useRouter()
const route = useRoute()

interface ToastMsg { message: string; type: string }
const sidebarCollapsed = ref(false)
const toast = ref<ToastMsg | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null
const showUserMenu = ref(false)
const userMenuRef = ref<HTMLElement | null>(null)
const showProfile = ref(false)
const showLogout = ref(false)

const globalSearch = ref('')
function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function doGlobalSearch() {
  if (globalSearch.value.trim()) {
    router.push(`/products?search=${encodeURIComponent(globalSearch.value.trim())}`)
    globalSearch.value = ''
  }
}

function onOutsideClick(e: MouseEvent) {
  if (userMenuRef.value && !userMenuRef.value.contains(e.target as Node)) {
    showUserMenu.value = false
  }
}
onMounted(() => document.addEventListener('click', onOutsideClick))
onBeforeUnmount(() => document.removeEventListener('click', onOutsideClick))
const profileEmail = ref('')
const profileCurPw = ref('')
const profileNewPw = ref('')
const profileError = ref('')

function showToast(message: string, type = 'info') {
  toast.value = { message, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 3000)
}

provide('toast', showToast)

// Load session data on mount
const currentUser = ref<any>(null)
const aiStats = ref<{ total: number; user_count: number; total_tokens_in: number; user_tokens_in: number; user_tokens_out?: number } | null>(null)
provide('currentUser', currentUser)


async function loadAiStats() {
  try {
    const token = localStorage.getItem('token')
    const res = await fetch('/product-db/api/ai/stats', { headers: { 'Authorization': `Bearer ${token}` } })
    if (res.ok) {
      const data = await res.json()
      aiStats.value = data
    }
  } catch { /* ignore */ }
}

async function loadSession() {
  try {
    const token = localStorage.getItem('token')
    if (!token) return
    const res = await fetch('/product-db/api/auth/session', {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        router.push('/login')
      }
      return
    }
    const data = await res.json()
    currentUser.value = data.user
  } catch { /* ignore */ }
}

function openProfile() {
  profileEmail.value = currentUser.value?.email || ''
  profileCurPw.value = ''
  profileNewPw.value = ''
  profileError.value = ''
  showProfile.value = true
}

function logout() {
  showLogout.value = false
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  currentUser.value = null
  router.push('/login')
}

async function saveProfile() {
  profileError.value = ''
  if (profileNewPw.value && !profileCurPw.value) {
    profileError.value = '修改密码需要输入当前密码'
    return
  }
  try {
    const token = localStorage.getItem('token')
    const body: any = {}
    if (profileEmail.value !== (currentUser.value?.email || '')) {
      body.email = profileEmail.value
    }
    if (profileNewPw.value) {
      body.password = profileNewPw.value
      body.current_password = profileCurPw.value
    }
    if (Object.keys(body).length === 0) { showProfile.value = false; return }
    const res = await fetch('/product-db/api/auth/profile', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(body),
    })
    if (!res.ok) { const d = await res.json(); throw new Error(d.detail || '保存失败') }
    const data = await res.json()
    currentUser.value = data.user
    showToast('已保存', 'success')
    showProfile.value = false
  } catch (e: any) { profileError.value = e.message }
}

onMounted(() => { loadSession(); loadAiStats() })

watch(() => route.path, (to, from) => {
  if (from === '/login' && to !== '/login' && localStorage.getItem('token')) {
    loadSession()
    loadAiStats()
  }
})
</script>

<style scoped>
.sidebar-user {
  margin-top: auto;
  border-top: 1px solid rgba(255,255,255,.1);
  padding: 6px 10px 6px 14px;
  position: relative;
}
.sidebar-user-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: rgba(255,255,255,.85);
  font-size: 13.5px;
  cursor: pointer;
  text-align: left;
  line-height: 1.3;
}
.sidebar-user-btn:hover { background: rgba(255,255,255,.1); color: #fff; }
.sidebar-search {
  padding: 8px 12px;
}
.sidebar-search input {
  width: 100%;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,.15);
  background: rgba(255,255,255,.08);
  color: rgba(255,255,255,.85);
  font-size: 12px;
}
.sidebar-search input::placeholder { color: rgba(255,255,255,.35); }
.sidebar-search input:focus { outline: none; border-color: var(--color-accent); }
.sidebar-stats {
  padding: 4px 16px 4px 22px;
  border-top: 1px solid rgba(255,255,255,.1);
}
.sidebar-stats-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
}
.sidebar-stats-label {
  font-size: 14px;
  color: rgba(255,255,255,.55);
}
.sidebar-stats-num {
  width: auto;
  text-align: left;
  font-size: 14px;
  font-weight: 700;
  color: rgba(255,255,255,.9);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.sidebar-stats.collapsed {
  padding: 4px 6px;
}
.sidebar-stats.collapsed .sidebar-stats-label { display: none; }
.sidebar-stats.collapsed .sidebar-stats-row { justify-content: center; gap: 2px; }
.sidebar-stats.collapsed .sidebar-stats-num { width: auto; text-align: center; font-size: 11px; }
.sidebar-version {
  padding: 4px 16px 4px 22px;
  font-size: 10px;
  color: rgba(255,255,255,.25);
  text-align: left;
}
.sidebar-username {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.user-dropdown {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 100%;
  margin-bottom: 4px;
  background: var(--color-secondary);
  border: 1px solid rgba(255,255,255,.1);
  border-radius: 8px;
  padding: 4px;
  box-shadow: 0 8px 24px rgba(0,0,0,.4);
  z-index: 100;
}
.user-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: rgba(255,255,255,.85);
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.user-dropdown-item:hover { background: rgba(255,255,255,.1); color: #fff; }
.user-dropdown-item--danger { color: var(--color-danger); }
.user-dropdown-item--danger:hover { background: rgba(233,69,96,.15); color: var(--color-danger); }

/* Modal */
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
  background: var(--color-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 0;
}
.modal-body { padding: 16px 20px; }
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 0 20px 16px;
}
</style>
