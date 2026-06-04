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

    <div
      class="drop-zone"
      :class="{ 'drop-active': dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="onDrop"
    >拖拽文件到此处上传</div>

    <table v-if="files.length" class="data-table" style="margin-top:8px">
      <thead><tr><th>文件</th><th>大小</th><th>类型</th><th style="width:80px">操作</th></tr></thead>
      <tbody>
        <tr v-for="f in files" :key="f.id">
          <td><span class="text-sm" style="cursor:pointer" @click="preview(f)">{{ f.label || f.filename }}</span></td>
          <td class="text-sm text-muted">{{ formatSize(f.file_size) }}</td>
          <td class="text-sm text-muted">{{ f.file_type || '—' }}</td>
          <td style="white-space:nowrap">
            <button class="btn-icon btn-sm" @click="preview(f)" title="预览"><EyeIcon style="width:14px;height:14px" /></button>
            <a :href="downloadUrl(f.id)" class="btn-icon btn-sm" title="下载"><DownloadIcon style="width:14px;height:14px" /></a>
            <button class="btn-icon btn-sm" @click="doDelete(f.id)" title="删除"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="text-sm text-muted" style="padding:8px 0">暂无文件</div>

    <!-- Preview modal -->
    <div v-if="previewFile" class="preview-overlay" @click.self="previewFile = null">
      <div class="preview-modal">
        <div class="flex justify-between items-center" style="margin-bottom:8px">
          <strong>{{ previewFile.label || previewFile.filename }}</strong>
          <button class="btn-icon btn-sm" @click="previewFile = null">✕</button>
        </div>
        <iframe v-if="previewFile.file_type === 'pdf'" :src="previewUrl(previewFile.id)" width="100%" height="600" style="border:none;border-radius:4px" />
        <img v-else-if="isImage(previewFile.file_type)" :src="previewUrl(previewFile.id)" style="max-width:100%;max-height:600px;object-fit:contain" />
        <pre v-else-if="previewFile.file_type === 'txt' || previewFile.file_type === 'csv'" style="max-height:500px;overflow:auto;background:var(--color-hover);padding:12px;border-radius:4px;font-size:12px;white-space:pre-wrap">{{ previewText }}</pre>
        <div v-else class="text-sm text-muted" style="text-align:center;padding:60px 0">该格式不支持在线预览<br /><a :href="downloadUrl(previewFile.id)">下载查看</a></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { Trash2Icon, UploadIcon, EyeIcon, DownloadIcon } from 'lucide-vue-next'

const props = defineProps<{ productId: number; hideEmpty?: boolean }>()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

interface FileItem { id: number; filename: string; file_url: string; file_size: number; file_type: string; label: string; sort_order: number; created_at: string }
const files = ref<FileItem[]>([])
const fileLabel = ref('')
const uploading = ref(false)
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const previewFile = ref<FileItem | null>(null)
const previewText = ref('')

function triggerUpload() { fileInput.value?.click() }

async function onDrop(e: DragEvent) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  await uploadFile(file)
}
function isImage(t: string) { return ['jpg','jpeg','png','gif','webp','bmp'].includes(t) }

function previewUrl(fileId: number) { return downloadUrl(fileId) }

async function preview(f: FileItem) {
  previewFile.value = f
  previewText.value = ''
  if (f.file_type === 'txt' || f.file_type === 'csv') {
    try {
      const resp = await fetch(previewUrl(f.id))
      previewText.value = await resp.text()
    } catch { previewText.value = '加载失败' }
  }
}

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

async function uploadFile(file: File) {
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
}

async function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await uploadFile(file)
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

<style scoped>
.preview-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 3000;
  display: flex; align-items: center; justify-content: center;
}
.preview-modal {
  background: #fff; border-radius: 12px; padding: 20px;
  width: 90vw; max-width: 900px; max-height: 90vh; overflow: auto;
  box-shadow: 0 8px 40px rgba(0,0,0,.2);
}
.drop-zone {
  border: 2px dashed var(--color-border); border-radius: 8px;
  padding: 20px; text-align: center; color: var(--color-text-secondary);
  font-size: 13px; transition: all .2s; margin-top: 8px;
}
.drop-zone.drop-active {
  border-color: var(--color-accent); background: #eff6ff; color: var(--color-accent);
}
</style>
