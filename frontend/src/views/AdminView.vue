<template>
  <PageHeader title="管理面板" />

  <div v-if="loading" class="empty-state"><p>加载中...</p></div>
  <div v-else-if="loadError" class="empty-state"><p style="color:var(--color-danger)">{{ loadError }}</p><button class="btn-secondary btn-sm" style="margin-top:8px" @click="load">重试</button></div>
  <template v-else>

  <!-- AI Usage Stats -->
  <div class="card mb-16">
    <h3>AI 用量统计</h3>
    <div class="flex gap-16 mb-8" v-if="aiUsage">
      <div class="stat"><span class="stat-num">{{ aiUsage.summary?.total || 0 }}</span><span class="stat-label">总次数</span></div>
      <div class="stat"><span class="stat-num">{{ formatNum(aiUsage.summary?.total_tokens_in || 0) }}</span><span class="stat-label">总输入Token</span></div>
      <div class="stat"><span class="stat-num">{{ formatNum(aiUsage.summary?.total_tokens_out || 0) }}</span><span class="stat-label">总输出Token</span></div>
      <div class="stat"><span class="stat-num" style="color:var(--color-success)">{{ aiUsage.summary?.success || 0 }}</span><span class="stat-label">成功</span></div>
    </div>
    <div class="text-sm text-muted mb-4">最近使用记录</div>
    <div v-if="aiUsage?.recent?.length" style="max-height:200px;overflow-y:auto">
      <table class="data-table">
        <thead><tr><th>用户</th><th>输入Token</th><th>输出Token</th><th>耗时</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="r in aiUsage.recent" :key="r.id">
            <td>{{ r.user_id }}</td><td>{{ r.tokens_in }}</td><td>{{ r.tokens_out }}</td><td>{{ r.duration_ms }}ms</td><td>{{ r.created_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- AI Settings: Prompts + Models -->
  <div class="card mb-16">
    <h3>AI 设置</h3>
    <div class="mb-8">
      <h4 style="margin:8px 0 4px">模型选择</h4>
      <div class="form-grid" style="gap:8px">
        <div class="form-group" v-for="(defVal, key) in aiSettings?.model_defaults || {}" :key="key">
          <label style="font-size:12px">{{ modelLabels[key] || key }}</label>
          <select v-model="aiModels[key]" style="font-size:12px">
            <option value="deepseek-v4-pro">V4 Pro</option>
            <option value="deepseek-v4-flash">V4 Flash</option>
          </select>
        </div>
      </div>
    </div>
    <div>
      <h4 style="margin:8px 0 4px">提示词</h4>
      <div v-for="(defPrompt, key) in aiSettings?.prompt_defaults || {}" :key="key" class="mb-8">
        <label style="font-size:12px;font-weight:600">{{ promptLabels[key] || key }}</label>
        <textarea v-model="aiPrompts[key]" rows="3" style="width:100%;font-family:monospace;font-size:13px;margin-top:2px"></textarea>
      </div>
      <button class="btn-primary btn-sm" @click="saveAiSettings" :disabled="aiSaving">{{ aiSaving ? '保存中...' : '保存 AI 设置' }}</button>
    </div>
  </div>

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
    <Pagination v-if="dlogsTotal > 20" :total="dlogsTotal" :page="dlogsPage" :per-page="20" @change="p => { dlogsPage = p; load() }" />
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
    <Pagination v-if="loginLogsTotal > 20" :total="loginLogsTotal" :page="loginLogsPage" :per-page="20" @change="p => { loginLogsPage = p; load() }" />
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
import Pagination from '../components/Pagination.vue'

const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})
const token = () => localStorage.getItem('token') || ''
const h = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` })

interface AdminUser { id: number; username: string; role: string; email: string; is_active: boolean; created_at: string; last_login: string }
interface LogEntry { id: number; user_id: number | null; ip_address: string; region: string; success: boolean; created_at: string }
interface DownloadLog { id: number; user_id: number; file_type: string; entity_id: number; ip_address: string; created_at: string }

const users = ref<AdminUser[]>([])
const logs = ref<LogEntry[]>([])
const dlogs = ref<DownloadLog[]>([])
const loginLogsPage = ref(1); const loginLogsTotal = ref(0)
const dlogsPage = ref(1); const dlogsTotal = ref(0)
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

// AI settings
const aiSettings = ref<any>(null)
const aiPrompts = ref<Record<string,string>>({})
const aiModels = ref<Record<string,string>>({})
const aiSaving = ref(false)
const promptLabels: Record<string,string> = { ai_system_prompt: '系统提示词', ai_keyword_prompt: '关键词提取提示词', ai_extract_prompt: '产品提取提示词' }
const modelLabels: Record<string,string> = { ai_chat_model: 'AI 对话', ai_keyword_model: '关键词提取', ai_extract_model: '产品提取' }

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
      adminApi(`/api/admin/login-logs?page=${loginLogsPage.value}&per_page=20`),
      adminApi('/api/admin/fields'),
      adminApi('/api/admin/ai-settings'),
      adminApi('/api/admin/ai-usage'),
      adminApi(`/api/admin/download-logs?page=${dlogsPage.value}&per_page=20`),
      fetch('/api/auth/registration-status').then(r => r.json()),
    ])
    users.value = uRes.users || []
    logs.value = lRes.logs || []; loginLogsTotal.value = lRes.total || 0
    dlogs.value = dRes.logs || []; dlogsTotal.value = dRes.total || 0
    const fields = fRes.fields || {}
    for (const fv of fieldList.value) { if (fv.key in fields) fv.visible = fields[fv.key] }
    aiSettings.value = pRes
    aiPrompts.value = { ...(pRes.prompt_defaults || {}), ...(pRes.prompts || {}) }
    aiModels.value = { ...(pRes.model_defaults || {}), ...(pRes.models || {}) }
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
async function saveAiSettings() {
  aiSaving.value = true
  try {
    await fetch('/api/admin/ai-settings', {
      method: 'PUT', headers: h(),
      body: JSON.stringify({ prompts: aiPrompts.value, models: aiModels.value }),
    })
    showToast('已保存', 'success')
  } catch (e: any) { showToast(e.message, 'error') }
  aiSaving.value = false
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
