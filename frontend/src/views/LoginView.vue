<template>
  <div class="login-page">
    <div class="login-card">
      <h1>产品数据库</h1>
      <p class="text-muted">{{ isRegister ? '注册新账号' : '登录以继续' }}</p>
      <div v-if="isRegister" class="form-group"><input v-model="email" placeholder="邮箱（选填）" /></div>
      <div class="form-group"><input v-model="username" placeholder="用户名" @keyup.enter="submit" /></div>
      <div class="form-group"><input v-model="password" type="password" placeholder="密码" @keyup.enter="submit" /></div>
      <p v-if="error" class="text-sm" style="color:var(--color-danger)">{{ error }}</p>
      <button class="btn-primary" style="width:100%;margin-top:16px;justify-content:center" @click="submit" :disabled="loading">{{ loading ? '提交中...' : isRegister ? '注册' : '登录' }}</button>
      <p class="text-sm" style="text-align:center;margin-top:16px;color:var(--color-text-secondary)">
        {{ isRegister ? '已有账号？' : '没有账号？' }}
        <a href="#" @click.prevent="isRegister = !isRegister; error = ''">{{ isRegister ? '去登录' : '注册新账号' }}</a>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const email = ref('')
const error = ref('')
const loading = ref(false)
const isRegister = ref(false)
const regOpen = ref(false)

onMounted(async () => {
  try {
    const res = await fetch('/api/auth/registration-status')
    const data = await res.json()
    regOpen.value = data.open
  } catch { /* ignore */ }
})

async function submit() {
  if (!username.value || !password.value) { error.value = '请输入用户名和密码'; return }
  loading.value = true; error.value = ''
  try {
    const endpoint = isRegister.value ? '/api/auth/register' : '/api/auth/login'
    const body: any = { username: username.value, password: password.value }
    if (isRegister.value) body.email = email.value
    const res = await fetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) { const d = await res.json(); throw new Error(d.detail || '操作失败') }
    const data = await res.json()
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify(data.user))
    router.push('/products')
  } catch (e: any) { error.value = e.message }
  loading.value = false
}
</script>

<style scoped>
.login-page { display:flex; align-items:center; justify-content:center; min-height:100vh; margin-top:-40px; background:var(--color-bg); }
.login-card { background:var(--color-card); padding:48px; border-radius:var(--radius-lg); box-shadow:var(--shadow-lg); width:400px; max-width:90vw; }
.login-card h1 { text-align:center; margin-bottom:8px; font-size:24px; }
.login-card p { text-align:center; margin-bottom:28px; }
.form-group { margin-bottom:16px; }
.form-group input { width:100%; padding:10px 12px; font-size:14px; }
</style>
