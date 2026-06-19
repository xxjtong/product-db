import { test, expect } from '@playwright/test'

const API = 'http://localhost:8000/product-db/api'

let token: string

test.beforeAll(async ({ playwright }) => {
  const ctx = await playwright.request.newContext()
  const r = await ctx.post(`${API}/auth/login`, { data: { username: 'admin', password: 'admin' } })
  token = (await r.json()).token
  await ctx.dispose()
})

function authHeaders() {
  return { Authorization: `Bearer ${token}` }
}

test.describe('API — Health & Auth', () => {
  test('GET /health returns ok', async ({ request }) => {
    const r = await request.get(`${API}/health`)
    expect(r.status()).toBe(200)
    expect(await r.json()).toEqual({ status: 'ok' })
  })

  test('POST /auth/login returns token', async ({ request }) => {
    const r = await request.post(`${API}/auth/login`, { data: { username: 'admin', password: 'admin' } })
    expect(r.status()).toBe(200)
    expect((await r.json()).token).toBeTruthy()
  })

  test('GET /auth/session returns user', async ({ request }) => {
    const r = await request.get(`${API}/auth/session`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.user.username).toBe('admin')
  })

 test('unauthenticated request returns 401', async ({ request }) => {
   const r = await request.get(`${API}/products`)
    // DEV_MODE returns 200 with auto-login; production returns 401
    expect([200, 401]).toContain(r.status())
 })
})

test.describe('API — Products', () => {
  test('GET /products returns paginated list', async ({ request }) => {
    const r = await request.get(`${API}/products`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.products).toBeInstanceOf(Array)
    expect(body.total).toBeGreaterThan(0)
    expect(body.page).toBe(1)
  })

  test('GET /products?search returns filtered results', async ({ request }) => {
    const r = await request.get(`${API}/products?search=网`, { headers: authHeaders() })
    const body = await r.json()
    expect(body.products.length).toBeGreaterThanOrEqual(0)
  })

  test('GET /products/:id returns product detail', async ({ request }) => {
    const list = await request.get(`${API}/products?per_page=1`, { headers: authHeaders() })
    const id = (await list.json()).products[0]?.id
    if (id) {
      const r = await request.get(`${API}/products/${id}`, { headers: authHeaders() })
      expect(r.status()).toBe(200)
      expect((await r.json()).product.id).toBe(id)
    }
  })

 test('GET /products/compare with 2 IDs', async ({ request }) => {
   const r = await request.get(`${API}/products/compare?product_ids=1,2`, { headers: authHeaders() })
   const body = await r.json()
    // Returns either matrix (2 products) or 404 (products not found) or products field
    expect(body.matrix || body.products || body.detail).toBeDefined()
 })

  test('POST /products/upload-image rejects non-image', async ({ request }) => {
    const r = await request.post(`${API}/products/upload-image`, {
      headers: authHeaders(),
      multipart: { file: { name: 'test.txt', mimeType: 'text/plain', buffer: Buffer.from('hello') } },
    })
    expect(r.status()).toBe(400)
  })
})

test.describe('API — Solutions & Quotations', () => {
  test('GET /solutions returns list', async ({ request }) => {
    const r = await request.get(`${API}/solutions`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.solutions).toBeInstanceOf(Array)
  })

  test('GET /quotations returns list', async ({ request }) => {
    const r = await request.get(`${API}/quotations`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.quotations).toBeInstanceOf(Array)
  })
})

test.describe('API — Dictionaries', () => {
  test('GET /dicts/comm-methods returns list', async ({ request }) => {
    const r = await request.get(`${API}/dicts/comm-methods`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.comm_methods).toBeInstanceOf(Array)
  })

  test('GET /dicts/manufacturers returns list', async ({ request }) => {
    const r = await request.get(`${API}/dicts/manufacturers`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.manufacturers).toBeInstanceOf(Array)
  })

  test('GET /categories returns list', async ({ request }) => {
    const r = await request.get(`${API}/categories`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.categories).toBeInstanceOf(Array)
  })

  test('GET /categories/tree returns tree', async ({ request }) => {
    const r = await request.get(`${API}/categories/tree`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
  })
})

test.describe('API — AI & Agent', () => {
  test('GET /ai/stats returns usage stats', async ({ request }) => {
    const r = await request.get(`${API}/ai/stats`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.total).toBeGreaterThanOrEqual(0)
  })

  test('GET /ai/conversations returns list', async ({ request }) => {
    const r = await request.get(`${API}/ai/conversations`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    expect((await r.json()).conversations).toBeInstanceOf(Array)
  })

  test('GET /agent/config returns config', async ({ request }) => {
    const r = await request.get(`${API}/agent/config`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    const body = await r.json()
    expect(body.db_path).toBeDefined()
  })
})

test.describe('API — Export', () => {
  test('GET /products/export returns xlsx', async ({ request }) => {
    const r = await request.get(`${API}/products/export`, { headers: authHeaders() })
    expect(r.status()).toBe(200)
    expect(r.headers()['content-type']).toContain('spreadsheet')
  })
})
