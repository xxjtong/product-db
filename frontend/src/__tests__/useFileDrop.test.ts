import { describe, it, expect, vi } from 'vitest'
import { useFileDrop } from '../composables/useFileDrop'

function makeFile(name: string, content = 'x', type = 'text/plain') {
  return new File([content], name, { type })
}

/** 等 FileReader 的 onload 跑完（jsdom 里是宏任务） */
const flush = () => new Promise(r => setTimeout(r, 0))

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

  it('异步读取期间重复添加也挡得住（不等 onload 就先入列）', () => {
    const { attachedFiles, addFile } = useFileDrop()
    const f = makeFile('race.txt')

    addFile(f)
    addFile(f)                             // onload 还没回来
    expect(attachedFiles.value).toHaveLength(1)

    return flush().then(() => expect(attachedFiles.value).toHaveLength(1))
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
    await flush()

    expect(attachedFiles.value[0].textContent).toBe('hello 内容')
  })

  it('图片文件填 dataUrl 并设置预览', async () => {
    const { attachedFiles, imagePreview, addFile } = useFileDrop()
    const png = new File([new Uint8Array([1, 2, 3])], 'p.png', { type: 'image/png' })

    addFile(png)
    await flush()

    expect(attachedFiles.value[0].dataUrl.startsWith('data:image/png')).toBe(true)
    expect(imagePreview.value).toBe(attachedFiles.value[0].dataUrl)
  })

  it('二进制文件只登记名字', async () => {
    const { attachedFiles, addFile } = useFileDrop()

    addFile(new File([new Uint8Array([1])], 'x.pdf', { type: 'application/pdf' }))
    await flush()

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
