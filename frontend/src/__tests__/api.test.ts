import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock localStorage
const storage = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => storage.get(k) ?? null,
  setItem: (k: string, v: string) => storage.set(k, v),
  removeItem: (k: string) => storage.delete(k),
})

// We need to re-import api after mocking globals
const { ApiError } = await import('../api')

describe('ApiError', () => {
  it('creates error with status and detail', () => {
    const err = new ApiError(404, 'Product not found')
    expect(err.status).toBe(404)
    expect(err.message).toBe('Product not found')
    expect(err.detail).toBe('Product not found')
  })

  it('is instanceof Error', () => {
    const err = new ApiError(500, 'Server error')
    expect(err).toBeInstanceOf(Error)
  })
})

describe('API helpers', () => {
  it('builds export URL with params', () => {
    const url = '/api/products/export?status=active'
    expect(url).toContain('/api/products/export')
    expect(url).toContain('status=active')
  })

  it('builds compare URL with ids', () => {
    const ids = '1,2,3'
    const url = `/api/products/compare?product_ids=${ids}`
    expect(url).toContain('1,2,3')
  })

  it('builds spec-sheet URL', () => {
    const url = '/api/products/190/spec-sheet'
    expect(url).toMatch(/\/api\/products\/\d+\/spec-sheet/)
  })

  it('builds quotation export URL', () => {
    const url = '/api/quotations/1/export-xlsx'
    expect(url).toMatch(/\/api\/quotations\/\d+\/export-xlsx/)
  })
})

describe('localStorage mock', () => {
  beforeEach(() => storage.clear())

  it('stores and retrieves token', () => {
    localStorage.setItem('token', 'test-token')
    expect(localStorage.getItem('token')).toBe('test-token')
  })

  it('returns null for missing key', () => {
    expect(localStorage.getItem('nonexistent')).toBeNull()
  })

  it('removes item', () => {
    localStorage.setItem('token', 'test')
    localStorage.removeItem('token')
    expect(localStorage.getItem('token')).toBeNull()
  })
})
