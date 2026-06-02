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
        <button class="sidebar-user-btn" @click="openProfile">
          <UserIcon style="width:14px;height:14px;flex-shrink:0" />
          <span class="sidebar-username">{{ currentUser.username }}</span>
        </button>
        <button class="sidebar-logout" title="退出登录" @click="showLogout = true">
          <LogOutIcon style="width:14px;height:14px" />
        </button>
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
import { ref, provide, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PackageIcon, GridIcon, BookIcon, TruckIcon, ClipboardListIcon, FileTextIcon, ShieldIcon, UserIcon, LogOutIcon } from 'lucide-vue-next'
import AiChat from './components/AiChat.vue'

const router = useRouter()

interface ToastMsg { message: string; type: string }
const sidebarCollapsed = ref(false)
const toast = ref<ToastMsg | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null
const showProfile = ref(false)
const showLogout = ref(false)
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
    const res = await fetch('/api/auth/profile', {
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

onMounted(loadSession)
</script>

<style scoped>
.sidebar-user {
  margin-top: auto;
  border-top: 1px solid rgba(255,255,255,.1);
  padding: 8px 10px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.sidebar-user-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: rgba(255,255,255,.85);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
}
.sidebar-user-btn:hover { background: rgba(255,255,255,.1); color: #fff; }
.sidebar-username {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.sidebar-logout {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px; height: 28px;
  border: none; border-radius: 6px;
  background: transparent;
  color: rgba(255,255,255,.7);
  cursor: pointer;
  flex-shrink: 0;
}
.sidebar-logout:hover { background: rgba(255,255,255,.15); color: #fff; }

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
  background: #fff;
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
