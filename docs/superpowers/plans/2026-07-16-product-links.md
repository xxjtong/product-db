# Product Links — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add URL link support to product files card, mixed display with existing files.

**Architecture:** Extend ProductFile model with `is_link` + `link_url` columns. New POST endpoint for link creation, PATCH for editing. Frontend adds "添加链接" button + dialog, table rows adapt to show links.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite + Vue3 + TypeScript

---

### Task 1: Extend ProductFile model

**Files:**
- Modify: `backend/app/models/product_file.py`

- [ ] **Step 1: Add `is_link` and `link_url` columns + to_dict()**

```python
from app.database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, func


class ProductFile(Base):
    __tablename__ = "product_files"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_url = Column(String(500), nullable=False)
    file_size = Column(Integer, default=0)
    file_type = Column(String(50), default="")
    label = Column(String(100), default="")
    sort_order = Column(Integer, default=0)
    is_link = Column(Boolean, default=False)
    link_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "product_id": self.product_id,
            "filename": self.filename,
            "file_url": self.file_url,
            "file_size": self.file_size,
            "file_type": self.file_type or "",
            "label": self.label or "",
            "sort_order": self.sort_order or 0,
            "is_link": bool(self.is_link),
            "link_url": self.link_url or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
        }
```

- [ ] **Step 2: Generate migration**

```bash
cd backend && source venv/bin/activate && alembic revision --autogenerate -m "add_product_file_links"
```

- [ ] **Step 3: Run migration**

```bash
cd backend && source venv/bin/activate && alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/product_file.py backend/alembic/versions/*add_product_file_links*.py
git commit -m "feat(product_files): add is_link + link_url columns to ProductFile model"
```

---

### Task 2: Add link CRUD API endpoints

**Files:**
- Modify: `backend/app/routers/product_files.py`

- [ ] **Step 1: Add POST /products/{product_id}/links endpoint**

Insert after the `upload_file` endpoint (after line 53), before `download_file`:

```python
from pydantic import BaseModel


class LinkCreate(BaseModel):
    label: str = ""
    link_url: str = ""


class LinkUpdate(BaseModel):
    label: str | None = None
    link_url: str | None = None


@router.post("/products/{product_id}/links")
def create_link(
    product_id: int,
    body: LinkCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    prod = get_or_404(db, Product, product_id, "Product not found")
    check_ownership(prod, user, strict=True)
    if not body.link_url.strip():
        raise HTTPException(400, "URL不能为空")
    pf = ProductFile(
        product_id=product_id,
        filename=body.label or body.link_url,
        file_url="",
        is_link=True,
        link_url=body.link_url.strip(),
        label=body.label or "",
        file_type="link",
    )
    db.add(pf)
    db.commit()
    db.refresh(pf)
    return {"file": pf.to_dict()}
```

- [ ] **Step 2: Add PATCH /products/files/{file_id} endpoint**

Insert after the `create_link` endpoint, before `download_file`:

```python
@router.patch("/products/files/{file_id}")
def update_file_link(
    file_id: int,
    body: LinkUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    pf = get_or_404(db, ProductFile, file_id, "File not found")
    prod = get_or_404(db, Product, pf.product_id, "Product not found")
    check_ownership(prod, user, strict=True)
    if body.label is not None:
        pf.label = body.label.strip()
        if pf.is_link and not pf.label:
            pf.label = pf.link_url or ""
    if pf.is_link and body.link_url is not None:
        if not body.link_url.strip():
            raise HTTPException(400, "URL不能为空")
        pf.link_url = body.link_url.strip()
        if not pf.label:
            pf.filename = body.link_url.strip()
    db.commit()
    db.refresh(pf)
    return {"file": pf.to_dict()}
```

- [ ] **Step 3: Update DELETE endpoint — skip file delete for links**

Replace the delete endpoint (lines 89-100):

```python
@router.delete("/products/files/{file_id}")
def delete_product_file(file_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    pf = get_or_404(db, ProductFile, file_id, "File not found")
    prod = get_or_404(db, Product, pf.product_id, "Product not found")
    check_ownership(prod, user, strict=True)
    if not pf.is_link:
        try:
            delete_file(pf.file_url)
        except Exception:
            logging.getLogger("uvicorn").debug("File cleanup failed for %s (may already be gone)", pf.file_url)
    db.delete(pf)
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Verify — start backend and test with curl**

```bash
# Start backend in background
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
```

Test link creation:
```bash
# First login to get token
TOKEN=$(curl -s -X POST http://localhost:8000/product-db/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Create link
curl -s -X POST "http://localhost:8000/product-db/api/products/256/links" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"label":"产品 datasheet","link_url":"https://example.com/datasheet.pdf"}'

# List files (should include link)
curl -s "http://localhost:8000/product-db/api/products/256/files" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# PATCH update
curl -s -X PATCH "http://localhost:8000/product-db/api/products/files/<file_id>" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"label":"updated label"}'

# DELETE link
curl -s -X DELETE "http://localhost:8000/product-db/api/products/files/<file_id>" \
  -H "Authorization: Bearer $TOKEN"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/product_files.py
git commit -m "feat(product_files): add link CRUD endpoints (POST + PATCH + DELETE)"
```

---

### Task 3: Update ProductFiles.vue — link support

**Files:**
- Modify: `frontend/src/components/ProductFiles.vue`

- [ ] **Step 1: Update template — add "添加链接" button, dialog, adapt table**

Replace entire `<template>` block:

```vue
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
        <button class="btn-secondary btn-sm" @click="showLinkDialog = true">
          <LinkIcon style="width:14px;height:14px" />添加链接
        </button>
      </div>
    </div>

    <div v-if="uploading" class="text-sm text-muted" style="padding:4px 0">上传中...</div>

    <table v-if="files.length" class="data-table" style="margin-top:8px">
      <thead><tr><th>文件</th><th>大小</th><th>类型</th><th style="width:100px">操作</th></tr></thead>
      <tbody>
        <tr v-for="f in files" :key="f.id">
          <td>
            <span v-if="f.is_link" style="cursor:pointer" class="text-sm" @click="openLink(f)">
              🔗 {{ f.label || f.link_url }}
            </span>
            <span v-else style="cursor:pointer" class="text-sm" @click="preview(f)">{{ f.label || f.filename }}</span>
          </td>
          <td class="text-sm text-muted">{{ f.is_link ? '—' : formatSize(f.file_size) }}</td>
          <td class="text-sm text-muted">{{ f.is_link ? '链接' : (f.file_type || '—') }}</td>
          <td style="white-space:nowrap">
            <template v-if="f.is_link">
              <button class="btn-icon btn-sm" @click="openLink(f)" title="打开"><ExternalLinkIcon style="width:14px;height:14px" /></button>
              <button class="btn-icon btn-sm" @click="editLink(f)" title="编辑"><PencilIcon style="width:14px;height:14px" /></button>
              <button class="btn-icon btn-sm" @click="doDelete(f.id)" title="删除"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
            </template>
            <template v-else>
              <button class="btn-icon btn-sm" @click="preview(f)" title="预览"><EyeIcon style="width:14px;height:14px" /></button>
              <a :href="downloadUrl(f.id)" class="btn-icon btn-sm" title="下载"><DownloadIcon style="width:14px;height:14px" /></a>
              <button class="btn-icon btn-sm" @click="doDelete(f.id)" title="删除"><Trash2Icon style="width:14px;height:14px;color:var(--color-danger)" /></button>
            </template>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="text-sm text-muted" style="padding:8px 0">暂无文件</div>

    <div
      class="drop-zone"
      :class="{ 'drop-active': dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="onDrop"
    >拖拽文件到此处上传</div>

    <!-- Link dialog -->
    <div v-if="showLinkDialog" class="preview-overlay" @click.self="cancelLinkDialog">
      <div class="preview-modal" style="max-width:480px">
        <div class="flex justify-between items-center" style="margin-bottom:12px">
          <strong>{{ editingLink ? '编辑链接' : '添加链接' }}</strong>
          <button class="btn-icon btn-sm" @click="cancelLinkDialog">✕</button>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px">
          <div>
            <label class="text-sm" style="display:block;margin-bottom:4px">URL <span style="color:var(--color-danger)">*</span></label>
            <input v-model="linkForm.url" placeholder="https://..." style="width:100%;height:32px;font-size:13px" @keyup.enter="saveLink" />
          </div>
          <div>
            <label class="text-sm" style="display:block;margin-bottom:4px">标题</label>
            <input v-model="linkForm.label" placeholder="产品手册、规格书..." style="width:100%;height:32px;font-size:13px" @keyup.enter="saveLink" />
          </div>
          <div class="flex justify-end gap-8" style="margin-top:4px">
            <button class="btn-secondary btn-sm" @click="cancelLinkDialog">取消</button>
            <button class="btn-primary btn-sm" @click="saveLink" :disabled="savingLink">{{ savingLink ? '保存中...' : '保存' }}</button>
          </div>
        </div>
      </div>
    </div>

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
```

- [ ] **Step 2: Update script — add link logic**

Replace the `<script setup>` block (lines 57-161):

```vue
<script setup lang="ts">
import { ref, reactive, onMounted, inject } from 'vue'
import { Trash2Icon, UploadIcon, EyeIcon, DownloadIcon, LinkIcon, ExternalLinkIcon, PencilIcon } from 'lucide-vue-next'

const props = defineProps<{ productId: number; hideEmpty?: boolean }>()
const showToast = inject<(msg: string, type?: string) => void>('toast', () => {})

interface FileItem {
  id: number; filename: string; file_url: string; file_size: number;
  file_type: string; label: string; sort_order: number; created_at: string;
  is_link?: boolean; link_url?: string;
}
const files = ref<FileItem[]>([])
const fileLabel = ref('')
const uploading = ref(false)
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const previewFile = ref<FileItem | null>(null)
const previewText = ref('')
const showLinkDialog = ref(false)
const savingLink = ref(false)
const editingLink = ref<FileItem | null>(null)
const linkForm = reactive({ url: '', label: '' })

function triggerUpload() { fileInput.value?.click() }

async function onDrop(e: DragEvent) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  await uploadFile(file)
}
function isImage(t: string) { return ['jpg','jpeg','png','gif','webp','bmp'].includes(t) }

function previewUrl(fileId: number) { return downloadUrl(fileId) + '&inline=1' }

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

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('token') || ''
  return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
}

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

// --- Link operations ---

function openLink(f: FileItem) {
  if (f.link_url) window.open(f.link_url, '_blank')
}

function editLink(f: FileItem) {
  editingLink.value = f
  linkForm.url = f.link_url || ''
  linkForm.label = f.label || ''
  showLinkDialog.value = true
}

function cancelLinkDialog() {
  showLinkDialog.value = false
  editingLink.value = null
  linkForm.url = ''
  linkForm.label = ''
}

async function saveLink() {
  const url = linkForm.url.trim()
  if (!url) { showToast('请输入URL', 'error'); return }
  savingLink.value = true
  try {
    if (editingLink.value) {
      const res = await fetch(`${API_BASE_URL}/products/files/${editingLink.value.id}`, {
        method: 'PATCH',
        headers: authHeaders(),
        body: JSON.stringify({ label: linkForm.label.trim(), link_url: url }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '更新失败')
      showToast('链接已更新', 'success')
    } else {
      const res = await fetch(`${API_BASE_URL}/products/${props.productId}/links`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ label: linkForm.label.trim(), link_url: url }),
      })
      if (!res.ok) throw new Error((await res.json()).detail || '添加失败')
      showToast('链接已添加', 'success')
    }
    cancelLinkDialog()
    await loadFiles()
  } catch (e: any) { showToast(e.message || '操作失败', 'error') }
  savingLink.value = false
}

async function doDelete(fileId: number) {
  if (!confirm('确定删除？')) return
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
```

- [ ] **Step 3: Style unchanged — verify no new CSS needed**

Existing `.preview-overlay`, `.preview-modal`, `.drop-zone` styles cover the link dialog too. No style changes needed.

- [ ] **Step 4: Verify frontend builds**

```bash
cd frontend && npx vue-tsc --noEmit && npx vitest run
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProductFiles.vue
git commit -m "feat(frontend): add link support to ProductFiles — create/edit/delete links, mixed display"
```
