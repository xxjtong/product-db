const API_BASE = '/api'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text)
  }
  if (res.status === 204) return {} as T
  return res.json()
}

// --- Dictionaries ---
export const fetchCommMethods = () => api<{ comm_methods: any[] }>('/dicts/comm-methods')
export const fetchCommProtocols = () => api<{ comm_protocols: any[] }>('/dicts/comm-protocols')
export const fetchPowerSupplies = () => api<{ power_supplies: any[] }>('/dicts/power-supplies')
export const fetchSensorMetrics = () => api<{ sensor_metrics: any[] }>('/dicts/sensor-metrics')
export const fetchManufacturers = () => api<{ manufacturers: any[] }>('/dicts/manufacturers')
export const createManufacturer = (data: any) => api('/dicts/manufacturers', { method: 'POST', body: JSON.stringify(data) })
export const updateManufacturer = (id: number, data: any) => api(`/dicts/manufacturers/${id}`, { method: 'PUT', body: JSON.stringify(data) })

// --- Categories ---
export const fetchCategories = () => api<{ categories: any[] }>('/categories?per_page=1000')
export const fetchCategoryTree = () => api<{ tree: any[] }>('/categories/tree')
export const createCategory = (data: any) => api('/categories', { method: 'POST', body: JSON.stringify(data) })
export const updateCategory = (id: number, data: any) => api(`/categories/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteCategory = (id: number) => api(`/categories/${id}`, { method: 'DELETE' })

export const fetchSpecDefinitions = (catId: number) =>
  api<{ spec_definitions: any[] }>(`/categories/${catId}/spec-definitions`)
export const createSpecDefinition = (catId: number, data: any) =>
  api(`/categories/${catId}/spec-definitions`, { method: 'POST', body: JSON.stringify(data) })
export const updateSpecDefinition = (catId: number, specId: number, data: any) =>
  api(`/categories/${catId}/spec-definitions/${specId}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSpecDefinition = (catId: number, specId: number) =>
  api(`/categories/${catId}/spec-definitions/${specId}`, { method: 'DELETE' })

// --- Products ---
export const fetchProducts = (params: string = '') =>
  api<{ products: any[]; total: number; page: number; per_page: number }>(`/products${params ? '?' + params : ''}`)
export const fetchProduct = (id: number) => api<{ product: any }>(`/products/${id}`)
export const createProduct = (data: any) => api('/products', { method: 'POST', body: JSON.stringify(data) })
export const updateProduct = (id: number, data: any) => api(`/products/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteProduct = (id: number) => api(`/products/${id}`, { method: 'DELETE' })
export const compareProducts = (ids: string) =>
  api<{ products: Record<number, any>; matrix: Record<string, Record<number, any>>; display_names: Record<string, string> }>(`/products/compare?product_ids=${ids}`)
export const exportProducts = (params = '') => `${API_BASE}/products/export${params ? '?' + params : ''}`
export const specSheetUrl = (id: number) => `${API_BASE}/products/${id}/spec-sheet`
export const uploadProductImage = (formData: FormData) =>
  fetch(`${API_BASE}/products/upload-image`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
    body: formData,
  }).then(r => r.json())
export const downloadProductImage = (url: string) =>
  api<{ url: string }>('/products/download-image', { method: 'POST', body: JSON.stringify({ url }) })

// --- Suppliers ---
export const fetchSuppliers = (search = '', all = false) =>
  api<{ suppliers: any[]; total: number }>(`/suppliers${search ? '?search=' + encodeURIComponent(search) + '&all=' + all : '?all=' + all}`)

export const fetchSuppliersPaginated = (params: string = '') =>
  api<{ suppliers: any[]; total: number }>(`/suppliers${params ? '?' + params : ''}`)
export const createSupplier = (data: any) => api('/suppliers', { method: 'POST', body: JSON.stringify(data) })
export const updateSupplier = (id: number, data: any) => api(`/suppliers/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSupplier = (id: number) => api(`/suppliers/${id}`, { method: 'DELETE' })

// --- Solutions ---
export const fetchSolutions = (params: string = '') =>
  api<{ solutions: any[]; total: number; page: number; per_page: number }>(`/solutions${params ? '?' + params : ''}`)
export const fetchSolution = (id: number) => api<{ solution: any }>(`/solutions/${id}`)
export const createSolution = (data: any) => api('/solutions', { method: 'POST', body: JSON.stringify(data) })
export const updateSolution = (id: number, data: any) => api(`/solutions/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSolution = (id: number) => api(`/solutions/${id}`, { method: 'DELETE' })
export const addSolutionItem = (solId: number, data: any) =>
  api(`/solutions/${solId}/items`, { method: 'POST', body: JSON.stringify(data) })
export const updateSolutionItem = (solId: number, itemId: number, data: any) =>
  api(`/solutions/${solId}/items/${itemId}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSolutionItem = (solId: number, itemId: number) =>
  api(`/solutions/${solId}/items/${itemId}`, { method: 'DELETE' })
export const checkSolution = (solId: number) => api<{ warnings: any[]; ok: boolean }>(`/solutions/${solId}/check`)
export const suggestSolution = (solId: number) => api<{ suggestions: any[] }>(`/solutions/${solId}/suggest`)
export const fetchBomSnapshot = (solId: number) => api<{ bom_snapshot: any }>(`/solutions/${solId}/bom-snapshot`)
export const saveBomSnapshot = (solId: number, data: any) =>
  api(`/solutions/${solId}/bom-snapshot`, { method: 'PUT', body: JSON.stringify(data) })
export const bomExportUrl = (solId: number) => `${API_BASE}/solutions/${solId}/bom-snapshot/export-xlsx`

// --- Quotations ---
export const fetchQuotations = (params: string = '') =>
  api<{ quotations: any[]; total: number; page: number; per_page: number }>(`/quotations${params ? '?' + params : ''}`)
export const fetchQuotation = (id: number) => api<{ quotation: any }>(`/quotations/${id}`)
export const createQuotation = (data: any) => api('/quotations', { method: 'POST', body: JSON.stringify(data) })
export const updateQuotation = (id: number, data: any) => api(`/quotations/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteQuotation = (id: number) => api(`/quotations/${id}`, { method: 'DELETE' })
export const addQuotationItem = (qtId: number, data: any) =>
  api(`/quotations/${qtId}/items`, { method: 'POST', body: JSON.stringify(data) })
export const updateQuotationItem = (qtId: number, itemId: number, data: any) =>
  api(`/quotations/${qtId}/items/${itemId}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteQuotationItem = (qtId: number, itemId: number) =>
  api(`/quotations/${qtId}/items/${itemId}`, { method: 'DELETE' })
export const quotationExportUrl = (qtId: number) => `${API_BASE}/quotations/${qtId}/export-xlsx`

// --- AI ---
export async function* streamAiChat(input: string, conversationId?: number | null) {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_BASE}/ai/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ input, conversation_id: conversationId }),
  })
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim()
        if (data === '[DONE]') return
        try {
          const parsed = JSON.parse(data)
          if (parsed.event === 'conversation_id') {
            yield `[CONVERSATION:${parsed.conversation_id}]` as any
          } else if (parsed.event === 'component') {
            yield `[COMPONENT:${JSON.stringify(parsed)}]` as any
          } else if (parsed.text || parsed.event === 'text') {
            yield (parsed.text || '') as any
          }
        } catch { /* skip */ }
      }
    }
  }
}
