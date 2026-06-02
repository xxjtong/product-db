import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, config } from '@vue/test-utils'

// Mock DOMPurify
vi.mock('dompurify', () => ({ default: { sanitize: (s: string) => s } }))

// Mock localStorage
const storage = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => storage.get(k) ?? null,
  setItem: (k: string, v: string) => storage.set(k, v),
  removeItem: (k: string) => storage.delete(k),
})

// Mock fetch
vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
  ok: true,
  json: () => Promise.resolve({ conversations: [], messages: [] }),
  body: {
    getReader: () => ({
      read: () => Promise.resolve({ done: true, value: undefined }),
    }),
  },
}))

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ path: '/', params: {}, query: {} }),
}))

// Stub router-link
config.global.stubs = { 'router-link': { template: '<a><slot /></a>' } }

// Mock TextDecoder for SSE tests
vi.stubGlobal('TextDecoder', vi.fn().mockImplementation(() => ({
  decode: () => '',
})))

// --- Markdown utils regression guards ---

describe('markdown utils (regression guards)', () => {
  it('escapeHtml strips script tags', async () => {
    const { escapeHtml } = await import('../utils/markdown')
    expect(typeof escapeHtml).toBe('function')
    expect(escapeHtml('<script>alert(1)</script>')).not.toContain('<script>')
    expect(escapeHtml('<img onerror=1>')).toContain('&lt;')
  })

  it('escapeHtml handles all dangerous characters', async () => {
    const { escapeHtml } = await import('../utils/markdown')
    expect(escapeHtml('<>&"\'')).toBe('&lt;&gt;&amp;&quot;&#039;')
  })

  it('formatAiContent returns empty for empty input', async () => {
    const { formatAiContent } = await import('../utils/markdown')
    expect(formatAiContent('', 'user')).toBe('')
    expect(formatAiContent('', 'tool')).toBe('')
  })

  it('formatAiContent escapes product data (XSS guard)', async () => {
    const { formatAiContent } = await import('../utils/markdown')
    const malicious = JSON.stringify({ products: [{ name: '<img onerror=1>', model: '<script>x</script>' }] })
    const result = formatAiContent(malicious, 'tool')
    expect(result).not.toContain('<img')
    expect(result).not.toContain('<script>')
    expect(result).toContain('&lt;img')
  })

  it('mdToHtml converts markdown to safe HTML', async () => {
    const { mdToHtml } = await import('../utils/markdown')
    expect(mdToHtml('**bold**')).toContain('<b>bold</b>')
    expect(mdToHtml('*italic*')).toContain('<i>italic</i>')
  })

  it('extractProducts parses tool results', async () => {
    const { extractProducts } = await import('../utils/markdown')
    expect(extractProducts('not json', 'user')).toEqual([])
    const prods = extractProducts(JSON.stringify({ products: [{ id: 1, name: 'Test' }] }), 'tool')
    expect(prods).toEqual([{ id: 1, name: 'Test' }])
  })
})

// --- AiChat component imports and structure ---

describe('AiChat component', () => {
  it('can import AiChat.vue without errors', async () => {
    const mod = await import('../components/AiChat.vue')
    expect(mod.default).toBeDefined()
  })

  it('GenUI component registry has required components', async () => {
    // Check GenUI cards can be imported (they are used via component :is binding)
    const SolutionCard = (await import('../components/GenUI/SolutionProductCard.vue')).default
    const QuoteCard = (await import('../components/GenUI/QuoteDraftCard.vue')).default
    expect(SolutionCard).toBeDefined()
    expect(QuoteCard).toBeDefined()
  })

  it('DOMPurify is properly importable', async () => {
    const DOMPurify = (await import('dompurify')).default
    expect(typeof DOMPurify.sanitize).toBe('function')
  })
})

// --- API functions used by AiChat ---

describe('AiChat API functions', () => {
  it('fetchConversations is exported from api.ts', async () => {
    const { fetchConversations } = await import('../api')
    expect(typeof fetchConversations).toBe('function')
  })

  it('fetchConversation is exported from api.ts', async () => {
    const { fetchConversation } = await import('../api')
    expect(typeof fetchConversation).toBe('function')
  })

  it('deleteConversation is exported from api.ts', async () => {
    const { deleteConversation } = await import('../api')
    expect(typeof deleteConversation).toBe('function')
  })

  it('streamAiChat is exported from api.ts', async () => {
    const { streamAiChat } = await import('../api')
    expect(typeof streamAiChat).toBe('function')
  })
})

// --- GenUI SolutionProductCard event contract ---

describe('SolutionProductCard events', () => {
  it('emits addToBom with checked items when button clicked', async () => {
    const SolutionCard = (await import('../components/GenUI/SolutionProductCard.vue')).default
    const wrapper = mount(SolutionCard, {
      props: { products: [{ id: 1, name: 'Test', price: 100, model: 'T1' }] },
    })
    // Check first product
    const checkbox = wrapper.find('input[type="checkbox"]')
    await checkbox.setValue(true)
    // Click 加入方案
    const btn = wrapper.find('.btn-primary')
    await btn.trigger('click')
    const events = wrapper.emitted('addToBom')
    expect(events).toBeTruthy()
    expect(events![0][0]).toEqual([{ id: 1, qty: 1 }])
  })

  it('emits compare with checked ids', async () => {
    const SolutionCard = (await import('../components/GenUI/SolutionProductCard.vue')).default
    const wrapper = mount(SolutionCard, {
      props: { products: [
        { id: 1, name: 'A', price: 100, model: '' },
        { id: 2, name: 'B', price: 200, model: '' },
      ] },
    })
    // Check both products
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    await checkboxes[1].setValue(true)
    // Click 对比
    const btn = wrapper.find('.btn-secondary')
    await btn.trigger('click')
    const events = wrapper.emitted('compare')
    expect(events).toBeTruthy()
    expect(events![0][0]).toEqual([1, 2])
  })

  it('对比 button is disabled when only 1 product checked', async () => {
    const SolutionCard = (await import('../components/GenUI/SolutionProductCard.vue')).default
    const wrapper = mount(SolutionCard, {
      props: { products: [
        { id: 1, name: 'A', price: 100, model: '' },
        { id: 2, name: 'B', price: 200, model: '' },
      ] },
    })
    // Check only 1 product
    const checkboxes = wrapper.findAll('input[type="checkbox"]')
    await checkboxes[0].setValue(true)
    // 对比 button should be disabled with only 1 selected
    const btn = wrapper.find('.btn-secondary')
    expect(btn.attributes('disabled')).toBeDefined()
  })
})
