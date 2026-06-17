<template>
  <Teleport to="body">
    <div v-if="visible" class="approval-overlay" @click.self="dismiss">
      <div class="approval-card">
        <div class="approval-header">
          <span class="approval-icon">&#9888;&#65039;</span>
          <div>
            <h3>Hermes Agent 申请执行操作</h3>
            <p class="approval-label">{{ task?.tool_label }}</p>
          </div>
        </div>

        <div class="approval-body">
          <p class="approval-summary">{{ task?.summary }}</p>
          <div v-if="task?.tool_input && Object.keys(task.tool_input).length" class="approval-params">
            <div v-for="(v, k) in task.tool_input" :key="k" class="approval-param">
              <span class="approval-key">{{ k }}</span>
              <span class="approval-val">{{ typeof v === 'object' ? JSON.stringify(v) : v }}</span>
            </div>
          </div>
        </div>

        <div class="approval-footer">
          <div v-if="status === 'pending'">
            <button class="btn-danger" style="margin-right:12px" @click="decide(false)" :disabled="loading">拒绝</button>
            <button class="btn-primary" @click="decide(true)" :disabled="loading">
              {{ loading ? '处理中...' : '授权执行' }}
            </button>
          </div>
          <div v-else-if="status === 'approved'" class="approval-done">
            <span class="approval-check">&#10003;</span> 已授权
          </div>
          <div v-else-if="status === 'rejected'" class="approval-done rejected">
            <span>&#10007;</span> 已拒绝
          </div>
          <div v-else-if="status === 'timeout'" class="approval-done timeout">
            <span>&#9202;</span> 审批超时
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

export interface ApprovalTask {
  task_id: string
  tool_name: string
  tool_label: string
  summary: string
  details?: Record<string, any>
  tool_input: Record<string, any>
}

const visible = ref(false)
const task = ref<ApprovalTask | null>(null)
const status = ref<'pending' | 'approved' | 'rejected' | 'timeout'>('pending')
const loading = ref(false)

let resolvePromise: ((value: boolean) => void) | null = null

function show(t: ApprovalTask): Promise<boolean> {
  task.value = t
  status.value = 'pending'
  visible.value = true
  return new Promise((resolve) => {
    resolvePromise = resolve
  })
}

async function decide(approved: boolean) {
  if (!task.value) return
  loading.value = true
  try {
    const token = localStorage.getItem('token')
    const res = await fetch(`/product-db/api/agent/approval/${task.value.task_id}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ approved, reason: approved ? '' : '用户手动拒绝' }),
    })
    if (res.ok) {
      status.value = approved ? 'approved' : 'rejected'
    }
  } catch {
    status.value = 'timeout'
  } finally {
    loading.value = false
    setTimeout(() => {
      visible.value = false
      if (resolvePromise) {
        resolvePromise(approved)
        resolvePromise = null
      }
    }, 800)
  }
}

function dismiss() {
  // Don't close by clicking overlay — must decide
}

defineExpose({ show })
</script>

<style scoped>
.approval-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.5);
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn .15s ease;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.approval-card {
  background: var(--color-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 440px;
  max-width: 90vw;
  overflow: hidden;
  animation: slideUp .2s ease;
}
@keyframes slideUp { from { transform: translateY(16px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

.approval-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 24px 16px;
  background: var(--color-blue-50);
  border-bottom: 1px solid var(--color-border);
}
.approval-icon { font-size: 24px; }
.approval-header h3 { margin: 0; font-size: 15px; color: var(--color-blue-700); }
.approval-label { margin: 2px 0 0; font-size: 13px; color: var(--color-text-secondary); }

.approval-body { padding: 16px 24px; }
.approval-summary { font-size: 14px; color: var(--color-text); margin: 0 0 12px; line-height: 1.5; }
.approval-params { background: var(--color-bg); border-radius: var(--radius-sm); padding: 10px 14px; }
.approval-param { display: flex; gap: 8px; padding: 4px 0; font-size: 12px; }
.approval-key { color: var(--color-text-secondary); min-width: 80px; font-weight: 500; flex-shrink: 0; }
.approval-val { color: var(--color-text); word-break: break-all; }

.approval-footer { padding: 16px 24px; border-top: 1px solid var(--color-border); text-align: right; }
.approval-done { font-size: 14px; color: var(--color-success); display: flex; align-items: center; gap: 6px; justify-content: flex-end; }
.approval-done.rejected { color: var(--color-danger); }
.approval-done.timeout { color: var(--color-warning); }
.approval-check { font-weight: 700; font-size: 18px; }
</style>
