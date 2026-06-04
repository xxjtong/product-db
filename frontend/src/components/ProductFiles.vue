<template>
  <div class="card mb-16" v-if="files.length || !hideEmpty">
    <div class="flex justify-between items-center" style="margin-bottom:12px">
      <h3 style="margin:0">产品文件 ({{ files.length }})</h3>
      <div class="flex gap-8">
        <input ref="fileInput" type="file" style="display:none" @change="onFileSelect" />
        <input v-model="fileLabel" placeholder="文件标签(可选)" style="width:140px;height:28px;font-size:12px" />
        <button class="btn-primary btn-sm" @click="triggerUpload">
          <UploadIcon style="width:14px;height:14px" />上传
        </button>
      </div>
    </div>

    <div v-if="uploading" class="text-sm text-muted" style="padding:4px 0">上传中...</div>

    <table v-if="files.length" class="data-table" style="margin-top:8px">
      <thead><tr><th>文件</th><th>大小</th><th>类型</th><th style="width:40px"></th></tr></thead>
      <tbody>
        <tr v-for="f in files" :key="f.id">
          <td>
            <a :href="downloadUrl(f.id)" class="text-sm">{{ f.label || f.filename }}</a>
          </td>
          <td class="text-sm text-muted">{{ formatSize(f.file_size) }}</td>
          <td class="text-sm text-muted">{{ f.file_type || '—' }}</td>
          <td>
            <button class="btn-icon btn-sm" @click="doDelete(f.id)"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="text-sm text-muted" style="padding:8px 0">暂无文件</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { Trash2Icon, UploadIcon } from 'lucide-vue-next'

const props = defineProps<{ productId: number; hideEmpty?: boolean }>()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

interface FileItem { id: number; filename: string; file_url: string; file_size: number; file_type: string; label: string; sort_order: number; created_at: string }
const files = ref<FileItem[]>([])
const fileLabel = ref('')
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function triggerUpload() { fileInput.value?.click() }

const API_BASE_URL = import.meta.env.BASE_URL + 'api'

function downloadUrl(fileId: number) {
  const token = localStorage.getItem('token') || ''
  return `${API_BASE_URL}/products/files/${fileId}?token=${encodeURIComponent(token)}`
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function loadFiles() {
  try {
    const token = localStorage.getItem('token')
    const res = await fetch(`${API_BASE_URL}/products/${props.productId}/files`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
    const data = await res.json()
    files.value = data.files || []
  } catch { /* ignore */ }
}

async function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const token = localStorage.getItem('token')
    const fd = new FormData()
    fd.append('file', file)
    fd.append('label', fileLabel.value || file.name)
    const res = await fetch(`${API_BASE_URL}/products/${props.productId}/files`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: fd,
    })
    if (!res.ok) throw new Error((await res.json()).detail || 'Upload failed')
    fileLabel.value = ''
    await loadFiles()
    showToast('文件已上传', 'success')
  } catch (e: any) { showToast(e.message || '上传失败', 'error') }
  uploading.value = false
  input.value = ''
}

async function doDelete(fileId: number) {
  if (!confirm('删除该文件？')) return
  try {
    const token = localStorage.getItem('token')
    await fetch(`${API_BASE_URL}/products/files/${fileId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    })
    await loadFiles()
    showToast('已删除', 'success')
  } catch { showToast('删除失败', 'error') }
}

onMounted(loadFiles)
</script>
