import { describe, it, expect } from 'vitest'

describe('API utilities', () => {
  it('builds export URL correctly', () => {
    const url = '/api/products/export?status=active'
    expect(url).toContain('/api/products/export')
    expect(url).toContain('status=active')
  })

  it('builds compare URL with ids', () => {
    const ids = '1,2,3'
    const url = `/api/products/compare?product_ids=${ids}`
    expect(url).toContain('1,2,3')
  })
})
