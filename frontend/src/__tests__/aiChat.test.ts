import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock DOMPurify
vi.mock('dompurify', () => ({ default: { sanitize: (s: string) => s } }))

// Mock localStorage
const storage = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => storage.get(k) ?? null,
  setItem: (k: string, v: string) => storage.set(k, v),
  removeItem: (k: string) => storage.delete(k),
})

// Mock fetch for SSE
vi.stubGlobal('fetch', vi.fn())

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ path: '/', params: {}, query: {} }),
}))

describe('AiChat imports resolve correctly', () => {
  it('imports escapeHtml from markdown utils (regression guard)', async () => {
    const { escapeHtml } = await import('../utils/markdown')
    expect(typeof escapeHtml).toBe('function')
    expect(escapeHtml('<script>alert(1)</script>')).not.toContain('<script>')
  })

  it('imports formatAiContent from markdown utils', async () => {
    const { formatAiContent } = await import('../utils/markdown')
    expect(typeof formatAiContent).toBe('function')
  })

  it('imports mdToHtml from markdown utils', async () => {
    const { mdToHtml } = await import('../utils/markdown')
    expect(typeof mdToHtml).toBe('function')
    expect(mdToHtml('**bold**')).toContain('<b>bold</b>')
  })

  it('imports extractProducts from markdown utils', async () => {
    const { extractProducts } = await import('../utils/markdown')
    expect(typeof extractProducts).toBe('function')
    const products = extractProducts(JSON.stringify({ products: [{ id: 1 }] }), 'tool')
    expect(products).toEqual([{ id: 1 }])
  })
})

describe('AiChat component imports resolve', () => {
  it('can import AiChat.vue without errors', async () => {
    // This test catches missing imports in AiChat.vue
    const mod = await import('../components/AiChat.vue')
    expect(mod.default).toBeDefined()
  })
})
