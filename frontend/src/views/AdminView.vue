<template>
  <PageHeader title="管理面板" />

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
      <thead><tr><th>ID</th><th>用户名</th><th>角色</th><th>邮箱</th><th>状态</th><th>最后登录</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="u in users" :key="u.id">
          <td>{{ u.id }}</td><td>{{ u.username }}</td><td>{{ u.role }}</td><td>{{ u.email || '—' }}</td>
          <td>{{ u.is_active ? '启用' : '停用' }}</td><td>{{ u.last_login || '—' }}</td>
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
      <div class="stat"><span class="stat-num">{{ aiUsage.summary?.total || 0 }}</span><span class="stat-label">总请求</span></div>
      <div class="stat"><span class="stat-num" style="color:var(--color-success)">{{ aiUsage.summary?.success || 0 }}</span><span class="stat-label">成功</span></div>
      <div class="stat"><span class="stat-num">{{ aiUsage.summary?.avg_duration_ms || 0 }}ms</span><span class="stat-label">平均耗时</span></div>
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
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { PencilIcon, Trash2Icon, KeyIcon } from 'lucide-vue-next'
import PageHeader from '../components/PageHeader.vue'
import Modal from '../components/Modal.vue'

const showToast = inject<(msg: string, type?: string) => void>('toast')!
const token = () => localStorage.getItem('token') || ''
const h = () => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${token()}` })

const users = ref<any[]>([])
const logs = ref<any[]>([])
const dlogs = ref<any[]>([])
const modalVisible = ref(false)
const editing = ref<any>(null)
const form = ref({ username: '', password: '', role: 'user', email: '', is_active: true })
const pwdModalVisible = ref(false)
const pwdTarget = ref<any>(null)
const newPwd = ref('')
const regOpen = ref(false)

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

async function api(url: string, opts?: any) {
  const res = await fetch(url, { headers: h(), ...opts })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || '请求失败')
  return res.json()
}

async function load() {
  try {
    const [uRes, lRes, fRes, pRes, aRes, dRes, rRes] = await Promise.all([
      api('/api/admin/users'),
      api('/api/admin/login-logs'),
      api('/api/admin/fields'),
      api('/api/admin/prompt'),
      api('/api/admin/ai-usage'),
      api('/api/admin/download-logs'),
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
  } catch { /* ignore */ }
}

// Field visibility
async function toggleField(key: string) {
  const fv = fieldList.value.find(f => f.key === key)
  if (!fv) return; fv.visible = !fv.visible
  await fetch('/api/admin/fields', { method: 'PUT', headers: h(), body: JSON.stringify({ [key]: fv.visible }) })
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
  if (!confirm('确定恢复默认提示词？所有AI对话将被清除。')) return
  const res = await fetch('/api/admin/prompt', { method: 'DELETE', headers: h() })
  const data = await res.json()
  aiPrompt.value = data.prompt
  aiPromptIsDefault.value = true; showToast('已恢复默认', 'success')
}

// Registration
async function toggleReg() {
  regOpen.value = !regOpen.value
  await fetch('/api/settings/registration_open', { method: 'PUT', headers: h(), body: JSON.stringify({ value: regOpen.value ? 'true' : 'false' }) })
  showToast(regOpen.value ? '注册已开放' : '注册已关闭', 'success')
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
  await fetch(`/api/admin/users/${pwdTarget.value.id}/password`, { method: 'PUT', headers: h(), body: JSON.stringify({ password: newPwd.value }) })
  pwdModalVisible.value = false; showToast('密码已重置', 'success')
}

async function doDelete(u: any) {
  if (!confirm(`确定删除用户「${u.username}」？`)) return
  await fetch(`/api/admin/users/${u.id}`, { method: 'DELETE', headers: h() })
  showToast('已删除', 'success'); load()
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
