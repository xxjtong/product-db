import { ref } from 'vue'

export interface FileAttachment {
  name: string
  type: string      // MIME type
  dataUrl: string   // base64 data URL (images) or empty (non-images)
  file?: File
}

export function useFileDrop(onFileAdded?: (file: File) => void) {
  const attachedFiles = ref<FileAttachment[]>([])
  const dragOver = ref(false)
  const imagePreview = ref('')

  function addFile(file: File) {
    const isImage = file.type.startsWith('image/')
    if (isImage) {
      const reader = new FileReader()
      reader.onload = () => {
        const dataUrl = reader.result as string
        attachedFiles.value.push({ name: file.name, type: file.type, dataUrl, file })
        if (!imagePreview.value) imagePreview.value = dataUrl
      }
      reader.readAsDataURL(file)
    } else {
      attachedFiles.value.push({ name: file.name, type: file.type, dataUrl: '', file })
    }
    // Notify callback for custom handling (e.g. AI extraction)
    if (onFileAdded) onFileAdded(file)
  }

  function onFileSelect(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) addFile(file)
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
        addFile(new File([blob], 'paste.' + (item.type.split('/')[1] || 'png'), { type: item.type }))
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
