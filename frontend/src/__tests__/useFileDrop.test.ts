import { describe, it, expect, vi } from 'vitest'
import { useFileDrop } from '../composables/useFileDrop'

function makeFile(name: string, content = 'x', type = 'text/plain') {
  return new File([content], name, { type })
}

/** 等 FileReader 的 onload 跑完。
 *  jsdom 里 FileReader 的完成时机在不同用例间会漂，固定等一个 setTimeout(0) 会偶发失败
 *  → 轮询到条件成立为止（最多 ~200ms）。 */
async function waitFor(cond: () => boolean, ms = 200) {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    if (cond()) return
    await new Promise(r => setTimeout(r, 5))
  }
}

describe('useFileDrop 附件去重', () => {
  it('同一个文件添加两次只挂一个 chip', () => {
    const { attachedFiles, addFile } = useFileDrop()
    const f = makeFile('a.txt')

    addFile(f)
    addFile(f)

    expect(attachedFiles.value).toHaveLength(1)
  })

  it('同等大小的同名文件（不同 File 实例）也只挂一个', () => {
    const { attachedFiles, addFile } = useFileDrop()

    addFile(makeFile('a.txt', 'same'))
    addFile(makeFile('a.txt', 'same'))

    expect(attachedFiles.value).toHaveLength(1)
  })

  it('change 与 drop 同时给同一个文件也只挂一个', () => {
    // 这就是生产上"一次上传出两个 chip"的复现路径
    const { attachedFiles, addFile } = useFileDrop()
    const f = makeFile('dup.txt')

    addFile(f)   // change 分支
    addFile(f)   // drop 分支

    expect(attachedFiles.value.map(a => a.name)).toEqual(['dup.txt'])
  })

  it('不同文件各挂一个', () => {
    const { attachedFiles, addFile } = useFileDrop()

    addFile(makeFile('a.txt'))
    addFile(makeFile('b.txt', 'y'))
    addFile(makeFile('a.txt', 'longer'))   // 同名但大小不同 → 视为不同文件

    expect(attachedFiles.value.map(a => a.name)).toEqual(['a.txt', 'b.txt', 'a.txt'])
  })

  it('异步读取期间重复添加也挡得住（不等 onload 就先入列）', async () => {
    const { attachedFiles, addFile } = useFileDrop()
    const f = makeFile('race.txt')

    addFile(f)
    addFile(f)                             // onload 还没回来
    expect(attachedFiles.value).toHaveLength(1)

    await waitFor(() => attachedFiles.value.length > 0)
    expect(attachedFiles.value).toHaveLength(1)
  })
})

describe('useFileDrop 选择文件', () => {
  it('onFileSelect 读取后清空 input.value（否则再选同一文件不触发 change）', () => {
    const { attachedFiles, onFileSelect } = useFileDrop()
    const input: any = { files: [makeFile('a.txt')], value: 'C:\\fakepath\\a.txt' }

    onFileSelect({ target: input } as unknown as Event)

    expect(attachedFiles.value).toHaveLength(1)
    expect(input.value).toBe('')
  })

  it('连点两次上传按钮（同一文件选两次）仍然只有一个 chip', () => {
    const { attachedFiles, onFileSelect } = useFileDrop()
    const f = makeFile('a.txt')

    onFileSelect({ target: { files: [f], value: 'a.txt' } } as unknown as Event)
    onFileSelect({ target: { files: [f], value: 'a.txt' } } as unknown as Event)

    expect(attachedFiles.value).toHaveLength(1)
  })
})

describe('useFileDrop 读取内容', () => {
  it('文本文件填 textContent', async () => {
    const { attachedFiles, addFile } = useFileDrop()

    addFile(makeFile('note.txt', 'hello 内容'))
    await waitFor(() => attachedFiles.value[0]?.textContent === 'hello 内容')

    expect(attachedFiles.value[0].textContent).toBe('hello 内容')
  })

  it('图片文件填 dataUrl 并设置预览', async () => {
    const { attachedFiles, imagePreview, addFile } = useFileDrop()
    const png = new File([new Uint8Array([1, 2, 3])], 'p.png', { type: 'image/png' })

    addFile(png)
    await waitFor(() => !!attachedFiles.value[0]?.dataUrl)

    expect(attachedFiles.value[0].dataUrl.startsWith('data:image/png')).toBe(true)
    expect(imagePreview.value).toBe(attachedFiles.value[0].dataUrl)
  })

  it('二进制文件只登记名字', async () => {
    const { attachedFiles, addFile } = useFileDrop()

    addFile(new File([new Uint8Array([1])], 'x.pdf', { type: 'application/pdf' }))

    expect(attachedFiles.value[0].name).toBe('x.pdf')
    expect(attachedFiles.value[0].textContent).toBe('')
  })

  it('onFileAdded 回调每个文件只触发一次', () => {
    const spy = vi.fn()
    const { addFile } = useFileDrop(spy)
    const f = makeFile('a.txt')

    addFile(f)
    addFile(f)

    expect(spy).toHaveBeenCalledTimes(1)
  })
})

describe('useFileDrop 拖拽与粘贴', () => {
  it('拖入一个文件 → 挂一个 chip，并复位 dragOver', () => {
    const { attachedFiles, dragOver, onDrop } = useFileDrop()
    dragOver.value = true

    onDrop({ dataTransfer: { files: [makeFile('dropped.txt')] } } as unknown as DragEvent)

    expect(attachedFiles.value.map(a => a.name)).toEqual(['dropped.txt'])
    expect(dragOver.value).toBe(false)
  })

  it('拖入多个文件目前只取第一个', () => {
    const { attachedFiles, onDrop } = useFileDrop()

    onDrop({ dataTransfer: { files: [makeFile('a.txt'), makeFile('b.txt', 'y')] } } as unknown as DragEvent)

    expect(attachedFiles.value.map(a => a.name)).toEqual(['a.txt'])
  })

  it('拖入已挂过的同一个文件不会重复', () => {
    const { attachedFiles, addFile, onDrop } = useFileDrop()
    const f = makeFile('same.txt')

    addFile(f)
    onDrop({ dataTransfer: { files: [f] } } as unknown as DragEvent)

    expect(attachedFiles.value).toHaveLength(1)
  })

  it('粘贴图片 → 挂一个图片 chip 并阻止默认行为', () => {
    const { attachedFiles, onPaste } = useFileDrop()
    const preventDefault = vi.fn()
    const img = new File([new Uint8Array([1, 2])], 'paste.png', { type: 'image/png' })

    onPaste({
      target: { tagName: 'DIV' },
      preventDefault,
      clipboardData: { items: [{ type: 'image/png', getAsFile: () => img }] },
    } as unknown as ClipboardEvent)

    expect(attachedFiles.value).toHaveLength(1)
    expect(attachedFiles.value[0].type).toBe('image/png')
    expect(preventDefault).toHaveBeenCalled()
  })

  it('连粘两张同尺寸图片 → 两个 chip 且名字不同', () => {
    // 都叫 paste.png 时：chip 难分辨，且"同名同尺寸"会被去重误判成重复
    const { attachedFiles, onPaste } = useFileDrop()
    const paste = () => onPaste({
      target: { tagName: 'DIV' },
      preventDefault: vi.fn(),
      clipboardData: {
        items: [{ type: 'image/png', getAsFile: () => new File([new Uint8Array([1, 2])], 'x.png', { type: 'image/png' }) }],
      },
    } as unknown as ClipboardEvent)

    paste()
    paste()

    expect(attachedFiles.value.map(a => a.name)).toEqual(['paste-1.png', 'paste-2.png'])
  })

  it('粘贴非图片不产生 chip（现状：只支持粘贴图片）', () => {
    const { attachedFiles, onPaste } = useFileDrop()

    onPaste({
      target: { tagName: 'DIV' },
      preventDefault: vi.fn(),
      clipboardData: { items: [{ type: 'application/pdf', getAsFile: () => makeFile('x.pdf') }] },
    } as unknown as ClipboardEvent)

    expect(attachedFiles.value).toHaveLength(0)
  })

  it('在 textarea 里粘贴不拦截（现状：需点到输入框外再粘贴）', () => {
    const { attachedFiles, onPaste } = useFileDrop()
    const preventDefault = vi.fn()
    const img = new File([new Uint8Array([1])], 'paste.png', { type: 'image/png' })

    onPaste({
      target: { tagName: 'TEXTAREA' },
      preventDefault,
      clipboardData: { items: [{ type: 'image/png', getAsFile: () => img }] },
    } as unknown as ClipboardEvent)

    expect(attachedFiles.value).toHaveLength(0)
    expect(preventDefault).not.toHaveBeenCalled()
  })
})

describe('useFileDrop 移除与清空', () => {
  it('removeFile 只删指定项', () => {
    const { attachedFiles, addFile, removeFile } = useFileDrop()

    addFile(makeFile('a.txt'))
    addFile(makeFile('b.txt', 'y'))
    removeFile(0)

    expect(attachedFiles.value.map(a => a.name)).toEqual(['b.txt'])
  })

  it('clearFiles 清空列表与预览', () => {
    const { attachedFiles, imagePreview, addFile, clearFiles } = useFileDrop()
    imagePreview.value = 'data:image/png;base64,xx'
    addFile(makeFile('a.txt'))

    clearFiles()

    expect(attachedFiles.value).toEqual([])
    expect(imagePreview.value).toBe('')
  })
})
