<template>
  <PageHeader title="管理面板" />

  <div v-if="loading" class="empty-state"><p>加载中...</p></div>
  <div v-else-if="loadError" class="empty-state"><p style="color:var(--color-danger)">{{ loadError }}</p><button class="btn-secondary btn-sm" style="margin-top:8px" @click="load">重试</button></div>
  <template v-else>

  <!-- Field Visibility -->
  <div class="card mb-16">
    <h3>字段可见性 <span class="text-sm text-muted">（普通用户视图）</span></h3>
    <p class="text-sm text-muted mb-8">控制以下字段是否对非管理员用户可见</p>
    <div class="flex flex-wrap gap-12">
      <label class="toggle-row" v-for="fv in fieldList" :key="fv.key">
        <input type="checkbox" :checked="fv.visible" @change="toggleField(fv.key)" />
        <span>{{ fv.label }}</span>
      </label>
    </div>
  </div>

  <!-- AI System Prompt -->
  <div class="card mb-16">
    <h3>AI 系统提示词 <span class="text-sm text-muted" :style="{color: aiPromptIsDefault ? 'var(--color-text-secondary)' : 'var(--color-danger)'}">{{ aiPromptIsDefault ? '（默认）' : '（自定义）' }}</span></h3>
    <textarea v-model="aiPrompt" rows="6" style="width:100%;font-family:monospace;font-size:12px"></textarea>
    <div class="flex gap-8 mt-8">
      <button class="btn-primary btn-sm" @click="saveAiPrompt" :disabled="aiPromptSaving">{{ aiPromptSaving ? '保存中...' : '保存' }}</button>
      <button v-if="!aiPromptIsDefault" class="btn-secondary btn-sm" @click="resetAiPrompt">恢复默认</button>
      <span class="text-sm text-muted">{{ aiPrompt?.length || 0 }} 字符</span>
    </div>
  </div>

  <!-- Registration Control -->
  <div class="card mb-16">
    <h3>注册控制</h3>
    <label class="toggle-row">
      <input type="checkbox" :checked="regOpen" @change="toggleReg" />
      <span>{{ regOpen ? '开放注册（任何人可注册账号）' : '关闭注册（仅管理员可创建用户）' }}</span>
    </label>
  </div>

  <!-- User Management -->
  <div class="card mb-16">
    <h3>用户管理</h3>
    <button class="btn-primary btn-sm" @click="openAdd" style="margin-bottom:12px">+ 新增用户</button>
    <table class="data-table" v-if="users.length">
      <thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>邮箱</th><th>AI次数</th><th>AI Token</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="u in users" :key="u.id">
          <td>{{ u.id }}</td><td>{{ u.username }}</td><td>{{ u.role }}</td><td>{{ u.email || '—' }}</td>
          <td class="font-mono">{{ u.ai_count || 0 }}</td>
          <td class="font-mono">{{ formatNum(u.ai_tokens || 0) }}</td>
          <td>{{ u.is_active ? '启用' : '停用' }}</td>
          <td>
            <button class="btn-icon btn-sm" @click="openEdit(u)"><PencilIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" @click="resetPwd(u)"><KeyIcon style="width:14px;height:14px" /></button>
            <button class="btn-icon btn-sm" @click="doDelete(u)"><Trash2Icon style="w:14px;h:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- AI Usage Stats -->
  <div class="card mb-16">
    <h3>AI 用量统计</h3>
    <div class="flex gap-16 mb-8" v-if="aiUsage">
      <div class="stat"><span class="stat-num">{{ aiUsage.summary?.total || 0 }}</span><span class="stat-label">总次数</span></div>
      <div class="stat"><span class="stat-num">{{ formatNum(aiUsage.summary?.total_tokens_in || 0) }}</span><span class="stat-label">总输入Token</span></div>
      <div class="stat"><span class="stat-num">{{ formatNum(aiUsage.summary?.total_tokens_out || 0) }}</span><span class="stat-label">总输出Token</span></div>
      <div class="stat"><span class="stat-num" style="color:var(--color-success)">{{ aiUsage.summary?.success || 0 }}</span><span class="stat-label">成功</span></div>
    </div>
    <div v-if="aiUsage?.recent?.length" style="max-height:200px;overflow-y:auto">
      <table class="data-table">
        <thead><tr><th>用户</th><th>操作</th><th>模型</th><th>耗时</th><th>状态</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="r in aiUsage.recent" :key="r.id">
            <td>{{ r.user_id }}</td><td>{{ r.operation }}</td><td>{{ r.model }}</td><td>{{ r.duration_ms }}ms</td><td>{{ r.success ? '✓' : '✕' }}</td><td>{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Download Logs -->
  <div class="card mb-16">
    <h3>下载审计（最近50条）</h3>
    <table class="data-table" v-if="dlogs.length">
      <thead><tr><th>用户ID</th><th>类型</th><th>实体ID</th><th>IP</th><th>时间</th></tr></thead>
      <tbody>
        <tr v-for="l in dlogs" :key="l.id">
          <td>{{ l.user_id }}</td><td>{{ l.file_type }}</td><td>{{ l.entity_id }}</td><td>{{ l.ip_address || '—' }}</td><td>{{ l.created_at }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="text-sm text-muted">暂无下载记录</p>
  </div>

  <!-- Login Logs -->
  <div class="card mb-16">
    <h3>登录日志（最近50条）</h3>
    <table class="data-table" v-if="logs.length">
      <thead><tr><th>用户ID</th><th>IP</th><th>地区</th><th>状态</th><th>时间</th></tr></thead>
      <tbody>
        <tr v-for="l in logs" :key="l.id">
          <td>{{ l.user_id }}</td><td>{{ l.ip_address }}</td><td>{{ l.region || '—' }}</td>
          <td>{{ l.success ? '✓' : '✕' }}</td><td>{{ l.created_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- User modal -->
  <Modal :title="editing ? '编辑用户' : '新增用户'" :visible="modalVisible" @close="modalVisible = false">
    <div class="form-grid">
      <div class="form-group"><label>用户名 *</label><input v-model="form.username" /></div>
      <div class="form-group"><label>密码 {{ editing ? '(留空不修改)' : '*' }}</label><input v-model="form.password" type="password" /></div>
      <div class="form-group"><label>角色</label><select v-model="form.role"><option value="user">user</option><option value="admin">admin</option></select></div>
      <div class="form-group"><label>邮箱</label><input v-model="form.email" /></div>
      <div class="form-group" v-if="editing"><label>状态</label><select v-model="form.is_active"><option :value="true">启用</option><option :value="false">停用</option></select></div>
    </div>
    <template #footer>
      <button class="btn-secondary" @click="modalVisible = false">取消</button><button class="btn-primary" @click="saveUser">保存</button>
    </template>
  </Modal>

  <!-- Reset password modal -->
  <Modal title="重置密码" :visible="pwdModalVisible" @close="pwdModalVisible = false">
    <div class="form-group"><label>新密码（至少8位）</label><input v-model="newPwd" type="password" /></div>
    <template #footer>
      <button class="btn-secondary" @click="pwdModalVisible = false">取消</button><button class="btn-primary" @click="doResetPwd">确认</button>
    </template>
  </Modal>
  <ConfirmDialog :title="confirmState.title" :message="confirmState.message" :visible="confirmState.visible" @confirm="confirmState.action(); confirmState.visible = false" @cancel="confirmState.visible = false" />
  </template>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { PencilIcon, Trash2Icon, KeyIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})
const token = () => localStorage.getItem('token') || ''
const h = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` })

interface AdminUser { id: number; username: string; role: string; email: string; is_active: boolean; created_at: string; last_login: string }
interface LogEntry { id: number; user_id: number | null; ip_address: string; region: string; success: boolean; created_at: string }
interface DownloadLog { id: number; user_id: number; file_type: string; entity_id: number; ip_address: string; created_at: string }

const users = ref<AdminUser[]>([])
const logs = ref<LogEntry[]>([])
const dlogs = ref<DownloadLog[]>([])
const modalVisible = ref(false)
const editing = ref<AdminUser | null>(null)
const form = ref({ username: '', password: '', role: 'user', email: '', is_active: true })
const pwdModalVisible = ref(false)
const pwdTarget = ref<AdminUser | null>(null)
const newPwd = ref('')
const regOpen = ref(false)
const confirmState = ref({ visible: false, title: '', message: '', action: () => {} })

function formatNum(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function showConfirm(title: string, message: string, action: () => void) {
  confirmState.value = { visible: true, title, message, action }
}

// Field visibility
const fieldList = ref([
  { key: 'cost_price', label: '成本价', visible: true },
  { key: 'manufacturer_name', label: '厂商名称', visible: true },
  { key: 'supplier_name', label: '供应商名称', visible: true },
  { key: 'product_url', label: '产品URL', visible: true },
])

// AI prompt
const aiPrompt = ref('')
const aiPromptSaving = ref(false)
const aiPromptIsDefault = ref(true)

// AI usage
const aiUsage = ref<any>(null)

async function adminApi(url: string, opts?: any) {
  const res = await fetch(url, { headers: h(), ...opts })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || '请求失败')
  return res.json()
}

const loading = ref(false)
const loadError = ref('')

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const [uRes, lRes, fRes, pRes, aRes, dRes, rRes] = await Promise.all([
      adminApi('/api/admin/users'),
      adminApi('/api/admin/login-logs'),
      adminApi('/api/admin/fields'),
      adminApi('/api/admin/prompt'),
      adminApi('/api/admin/ai-usage'),
      adminApi('/api/admin/download-logs'),
      fetch('/api/auth/registration-status').then(r => r.json()),
    ])
    users.value = uRes.users || []
    logs.value = lRes.logs || []
    dlogs.value = dRes.logs || []
    const fields = fRes.fields || {}
    for (const fv of fieldList.value) { if (fv.key in fields) fv.visible = fields[fv.key] }
    aiPrompt.value = pRes.prompt || ''
    aiPromptIsDefault.value = pRes.is_default !== false
    aiUsage.value = aRes
    regOpen.value = rRes.open || false
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  }
  loading.value = false
}

// Field visibility
async function toggleField(key: string) {
  const fv = fieldList.value.find(f => f.key === key)
  if (!fv) return; fv.visible = !fv.visible
  try {
    await fetch('/api/admin/fields', { method: 'PUT', headers: h(), body: JSON.stringify({ [key]: fv.visible }) })
  } catch { fv.visible = !fv.visible; showToast('保存失败', 'error') }
}

// AI prompt
async function saveAiPrompt() {
  aiPromptSaving.value = true
  try {
    await fetch('/api/admin/prompt', { method: 'PUT', headers: h(), body: JSON.stringify({ prompt: aiPrompt.value }) })
    aiPromptIsDefault.value = false; showToast('已保存', 'success')
  } catch (e: any) { showToast(e.message, 'error') }
  aiPromptSaving.value = false
}

async function resetAiPrompt() {
  showConfirm('恢复默认提示词', '确定恢复默认提示词？所有AI对话将被清除。', async () => {
    const res = await fetch('/api/admin/prompt', { method: 'DELETE', headers: h() })
    const data = await res.json()
    aiPrompt.value = data.prompt
    aiPromptIsDefault.value = true; showToast('已恢复默认', 'success')
  })
}

// Registration
async function toggleReg() {
  regOpen.value = !regOpen.value
  try {
    await fetch('/api/settings/registration_open', { method: 'PUT', headers: h(), body: JSON.stringify({ value: regOpen.value ? 'true' : 'false' }) })
    showToast(regOpen.value ? '注册已开放' : '注册已关闭', 'success')
  } catch { regOpen.value = !regOpen.value; showToast('保存失败', 'error') }
}

// Users
function openAdd() { editing.value = null; form.value = { username: '', password: '', role: 'user', email: '', is_active: true }; modalVisible.value = true }
function openEdit(u: any) { editing.value = u; form.value = { username: u.username, password: '', role: u.role, email: u.email || '', is_active: u.is_active }; modalVisible.value = true }

async function saveUser() {
  try {
    const url = editing.value ? `/api/admin/users/${editing.value.id}` : '/api/admin/users'
    await fetch(url, { method: editing.value ? 'PUT' : 'POST', headers: h(), body: JSON.stringify(form.value) })
    modalVisible.value = false; showToast('已保存', 'success'); load()
  } catch (e: any) { showToast(e.message, 'error') }
}

function resetPwd(u: any) { pwdTarget.value = u; newPwd.value = ''; pwdModalVisible.value = true }

async function doResetPwd() {
  if (!newPwd.value || newPwd.value.length < 8) { showToast('密码至少8位', 'error'); return }
  if (!pwdTarget.value) return
  try {
    await fetch(`/api/admin/users/${pwdTarget.value.id}/password`, { method: 'PUT', headers: h(), body: JSON.stringify({ password: newPwd.value }) })
    pwdModalVisible.value = false; showToast('密码已重置', 'success')
  } catch (e: any) { showToast('重置失败', 'error') }
}

async function doDelete(u: any) {
  showConfirm('删除用户', `确定删除用户「${u.username}」？`, async () => {
    try {
      await fetch(`/api/admin/users/${u.id}`, { method: 'DELETE', headers: h() })
      showToast('已删除', 'success'); load()
    } catch (e: any) { showToast('删除失败', 'error') }
  })
}

onMounted(load)
</script>

<style scoped>
.toggle-row { display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.toggle-row input { margin: 0; }
.stat { text-align: center; min-width: 80px; }
.stat-num { display: block; font-size: 20px; font-weight: 700; }
.stat-label { font-size: 11px; color: var(--color-text-secondary); }
</style>
