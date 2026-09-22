import { reactive, ref } from 'vue'

export interface FileAttachment {
  name: string
  type: string       // MIME type
  dataUrl: string    // base64 data URL (images only)
  textContent: string // text content (deprecated, use url)
  url: string        // public URL after upload
  uploaded: boolean  // true after successful upload
  file?: File
}

const TEXT_TYPES = ['text/', 'application/json', 'application/xml', 'text/csv']
const TEXT_EXT = /\.(csv|txt|json|xml|md|log|yaml|yml|tsv)$/i

function isTextFile(file: File) {
  return TEXT_TYPES.some(t => file.type.startsWith(t)) || TEXT_EXT.test(file.name)
}

function fileKey(file: File) {
  return `${file.name}::${file.size}`
}

export function useFileDrop(onFileAdded?: (file: File) => void) {
  const attachedFiles = ref<FileAttachment[]>([])
  const dragOver = ref(false)
  const imagePreview = ref('')
  let pasteSeq = 0   // 粘贴图片的命名序号

  function addFile(file: File) {
    // 同一个文件只挂一次：双击上传按钮、change 与 drop 同时触发、或先后选中同一个文件，
    // 都不该出现两个一模一样的 chip（那会让消息里出现两份文件路径）。
    const key = fileKey(file)
    if (attachedFiles.value.some(a => a.file && fileKey(a.file) === key)) return

    // 先同步入列再异步读内容：FileReader 是异步的，若等 onload 才 push，
    // 读取期间重复触发的同一次上传会各自 push 一条（异步窗口里的重复挡不住）。
    const item = reactive<FileAttachment>({
      name: file.name, type: file.type, dataUrl: '', textContent: '', url: '', uploaded: false, file,
    })
    attachedFiles.value.push(item)

    if (file.type.startsWith('image/')) {
      const reader = new FileReader()
      reader.onload = () => {
        item.dataUrl = reader.result as string
        if (!imagePreview.value) imagePreview.value = item.dataUrl
      }
      reader.readAsDataURL(file)
    } else if (isTextFile(file)) {
      const reader = new FileReader()
      reader.onload = () => {
        item.textContent = reader.result as string
      }
      reader.readAsText(file)
    }
    // 二进制文件（xlsx/pdf 等）只需登记名字，内容由后端读取

    // Notify callback for custom handling (e.g. AI extraction)
    if (onFileAdded) onFileAdded(file)
  }

  function onFileSelect(e: Event) {
    const input = e.target as HTMLInputElement
    const file = input.files?.[0]
    if (file) addFile(file)
    // 清空 value：否则再次选中同一个文件不会触发 change（用户会以为上传坏了）
    input.value = ''
  }

  function onDrop(e: DragEvent) {
    dragOver.value = false
    const file = e.dataTransfer?.files?.[0]
    if (file) addFile(file)
  }

  function onPaste(e: ClipboardEvent) {
    if ((e.target as HTMLElement)?.tagName === 'TEXTAREA') return
    const items = e.clipboardData?.items
    if (!items) return
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        const blob = item.getAsFile()
        if (!blob) continue
        // 每张粘贴图片给个递增名字：都叫 paste.png 时 chip 难分辨，
        // 而且同名同尺寸会被上面的去重规则误判成重复
        const ext = item.type.split('/')[1] || 'png'
        addFile(new File([blob], `paste-${++pasteSeq}.${ext}`, { type: item.type }))
        break
      }
    }
  }

  function removeFile(i: number) {
    attachedFiles.value.splice(i, 1)
    if (!attachedFiles.value.length) imagePreview.value = ''
  }

  function clearFiles() {
    attachedFiles.value = []
    imagePreview.value = ''
  }

  return {
    attachedFiles, dragOver, imagePreview,
    addFile, onFileSelect, onDrop, onPaste, removeFile, clearFiles,
  }
}
