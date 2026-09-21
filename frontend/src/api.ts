import type { Product, Category, Supplier, Solution, Quotation, SpecDefinition, Manufacturer, ProductDependency } from './types'

const API_BASE = '/product-db/api'

export class ApiError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

/** Extract a readable message from a non-OK response body. */
export async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
  } catch {
    return await res.text().catch(() => '') || res.statusText
  }
}

/** 清理本地凭据（token / user）。登出与 401 统一处理都走这里，避免两处逻辑漂移。 */
export function clearAuthStorage() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
}

// 401 统一处理回调：由 App 层注册（跳转要用 router，这里直接 import 会和
// router → views → api 形成循环依赖，所以只在 api 里做「清理 + 通知」）
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...headers, ...(options?.headers as Record<string, string> || {}) },
  })
  if (!res.ok) {
    let message = ''
    try {
      const body = await res.json()
      message = body.detail || JSON.stringify(body)
    } catch {
      message = await res.text().catch(() => '') || res.statusText
    }
    if (res.status === 401) {
      // token 过期或被作废：清掉本地凭据并回登录页，避免用户卡在报错页面
      clearAuthStorage()
      onUnauthorized?.()
    }
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return {} as T
  return res.json()
}

// --- Auth ---
/** 登出：让服务端立刻作废该用户所有已签发的 token */
export const logout = () => api<{ ok: boolean }>('/auth/logout', { method: 'POST' })

// --- Dictionaries ---
export const fetchCommMethods = (page = 1, perPage = 500) => api<{ comm_methods: { id: number; name: string; method_type?: string; description?: string }[]; total: number }>(`/dicts/comm-methods?page=${page}&per_page=${perPage}`)
export const fetchCommProtocols = (page = 1, perPage = 500) => api<{ comm_protocols: { id: number; name: string; description?: string }[]; total: number }>(`/dicts/comm-protocols?page=${page}&per_page=${perPage}`)
export const fetchPowerSupplies = (page = 1, perPage = 500) => api<{ power_supplies: { id: number; name: string; supply_category?: string; description?: string }[]; total: number }>(`/dicts/power-supplies?page=${page}&per_page=${perPage}`)
export const fetchSensorMetrics = (page = 1, perPage = 500) => api<{ sensor_metrics: { id: number; name: string; unit?: string; accuracy?: string; resolution?: string; description?: string }[]; total: number }>(`/dicts/sensor-metrics?page=${page}&per_page=${perPage}`)

// Dict CRUD
export const createCommMethod = (data: Record<string, unknown>) => api('/dicts/comm-methods', { method: 'POST', body: JSON.stringify(data) })
export const updateCommMethod = (id: number, data: Record<string, unknown>) => api(`/dicts/comm-methods/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteCommMethod = (id: number) => api(`/dicts/comm-methods/${id}`, { method: 'DELETE' })
export const createCommProtocol = (data: Record<string, unknown>) => api('/dicts/comm-protocols', { method: 'POST', body: JSON.stringify(data) })
export const updateCommProtocol = (id: number, data: Record<string, unknown>) => api(`/dicts/comm-protocols/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteCommProtocol = (id: number) => api(`/dicts/comm-protocols/${id}`, { method: 'DELETE' })
export const createPowerSupply = (data: Record<string, unknown>) => api('/dicts/power-supplies', { method: 'POST', body: JSON.stringify(data) })
export const updatePowerSupply = (id: number, data: Record<string, unknown>) => api(`/dicts/power-supplies/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deletePowerSupply = (id: number) => api(`/dicts/power-supplies/${id}`, { method: 'DELETE' })
export const createSensorMetric = (data: Record<string, unknown>) => api('/dicts/sensor-metrics', { method: 'POST', body: JSON.stringify(data) })
export const updateSensorMetric = (id: number, data: Record<string, unknown>) => api(`/dicts/sensor-metrics/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSensorMetric = (id: number) => api(`/dicts/sensor-metrics/${id}`, { method: 'DELETE' })
export const fetchManufacturers = (page = 1, perPage = 500) => api<{ manufacturers: Manufacturer[]; total: number }>(`/dicts/manufacturers?page=${page}&per_page=${perPage}`)
export const createManufacturer = (data: Record<string, unknown>) => api('/dicts/manufacturers', { method: 'POST', body: JSON.stringify(data) })
export const updateManufacturer = (id: number, data: Record<string, unknown>) => api(`/dicts/manufacturers/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteManufacturer = (id: number) => api(`/dicts/manufacturers/${id}`, { method: 'DELETE' })

// --- Categories ---
export const fetchCategories = (params: string = 'per_page=1000') => api<{ categories: Category[]; total?: number }>(`/categories?${params}`)
export const fetchCategoryTree = () => api<{ tree: Category[] }>('/categories/tree')
export const createCategory = (data: Record<string, unknown>) => api('/categories', { method: 'POST', body: JSON.stringify(data) })
export const updateCategory = (id: number, data: Record<string, unknown>) => api(`/categories/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteCategory = (id: number) => api(`/categories/${id}`, { method: 'DELETE' })

export const fetchSpecDefinitions = (catId: number) =>
  api<{ spec_definitions: SpecDefinition[] }>(`/categories/${catId}/spec-definitions`)
export const createSpecDefinition = (catId: number, data: Record<string, unknown>) =>
  api(`/categories/${catId}/spec-definitions`, { method: 'POST', body: JSON.stringify(data) })
export const updateSpecDefinition = (catId: number, specId: number, data: Record<string, unknown>) =>
  api(`/categories/${catId}/spec-definitions/${specId}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSpecDefinition = (catId: number, specId: number) =>
  api(`/categories/${catId}/spec-definitions/${specId}`, { method: 'DELETE' })

// --- Products ---
export const fetchProducts = (params: string = '') =>
  api<{ products: Product[]; total: number; page: number; per_page: number }>(`/products${params ? '?' + params : ''}`)
export const fetchProduct = (id: number) => api<{ product: Product }>(`/products/${id}`)
export const createProduct = (data: Record<string, unknown>) => api('/products', { method: 'POST', body: JSON.stringify(data) })
export const updateProduct = (id: number, data: Record<string, unknown>) => api(`/products/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteProduct = (id: number) => api(`/products/${id}`, { method: 'DELETE' })
export const compareProducts = (ids: string) =>
  api<{ products: Record<number, any>; matrix: Record<string, Record<number, any>>; display_names: Record<string, string> }>(`/products/compare?product_ids=${ids}`)
export const exportProducts = (params = '') => `${API_BASE}/products/export${params ? '?' + params : ''}`
export const specSheetUrl = (id: number) => {
  const token = localStorage.getItem('token') || ''
  return `${API_BASE}/products/${id}/spec-sheet?token=${encodeURIComponent(token)}`
}

// --- Product Dependencies ---
export const fetchDependencies = (productId: number) =>
  api<{ dependencies: ProductDependency[] }>(`/products/${productId}/dependencies`)
export const createDependency = (productId: number, data: Record<string, unknown>) =>
  api(`/products/${productId}/dependencies`, { method: 'POST', body: JSON.stringify(data) })
export const updateDependency = (productId: number, depId: number, data: Record<string, unknown>) =>
  api(`/products/${productId}/dependencies/${depId}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteDependency = (productId: number, depId: number) =>
  api(`/products/${productId}/dependencies/${depId}`, { method: 'DELETE' })

export const uploadProductImage = async (formData: FormData) => {
  const res = await fetch(`${API_BASE}/products/upload-image`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
    body: formData,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || '上传失败')
  return data
}
export const downloadProductImage = (url: string) =>
  api<{ url: string }>('/products/download-image', { method: 'POST', body: JSON.stringify({ url }) })

// --- Suppliers ---
export const fetchSuppliers = (search = '', all = false) =>
  api<{ suppliers: Supplier[]; total: number }>(`/suppliers${search ? '?search=' + encodeURIComponent(search) + '&all=' + all : '?all=' + all}`)

export const fetchSuppliersPaginated = (params: string = '') =>
  api<{ suppliers: Supplier[]; total: number }>(`/suppliers${params ? '?' + params : ''}`)
export const createSupplier = (data: Record<string, unknown>) => api('/suppliers', { method: 'POST', body: JSON.stringify(data) })
export const updateSupplier = (id: number, data: Record<string, unknown>) => api(`/suppliers/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSupplier = (id: number) => api(`/suppliers/${id}`, { method: 'DELETE' })

// --- Solutions ---
export const fetchSolutions = (params: string = '') =>
  api<{ solutions: Solution[]; total: number; page: number; per_page: number }>(`/solutions${params ? '?' + params : ''}`)
export const fetchSolution = (id: number) => api<{ solution: Solution }>(`/solutions/${id}`)
export const createSolution = (data: Record<string, unknown>) => api<{ solution: { id: number } }>('/solutions', { method: 'POST', body: JSON.stringify(data) })
export const updateSolution = (id: number, data: Record<string, unknown>) => api(`/solutions/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSolution = (id: number) => api(`/solutions/${id}`, { method: 'DELETE' })
export const batchDeleteSolutions = (ids: number[]) => api('/solutions/batch-delete', { method: 'POST', body: JSON.stringify({ ids }) })
export const addSolutionItem = (solId: number, data: Record<string, unknown>) =>
  api(`/solutions/${solId}/items`, { method: 'POST', body: JSON.stringify(data) })
export const updateSolutionItem = (solId: number, itemId: number, data: Record<string, unknown>) =>
  api(`/solutions/${solId}/items/${itemId}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteSolutionItem = (solId: number, itemId: number) =>
  api(`/solutions/${solId}/items/${itemId}`, { method: 'DELETE' })
export const reorderSolutionItems = (solId: number, itemIds: number[]) =>
  api(`/solutions/${solId}/items/reorder`, { method: 'PUT', body: JSON.stringify({ item_ids: itemIds }) })
export const checkSolution = (solId: number) => api<{ warnings: any[]; ok: boolean }>(`/solutions/${solId}/check`)
export const suggestSolution = (solId: number) => api<{ suggestions: any[] }>(`/solutions/${solId}/suggest`)
export const fetchBomSnapshot = (solId: number) => api<{ bom_snapshot: any }>(`/solutions/${solId}/bom-snapshot`)
export const fetchQuotationBom = (qid: number) => api<{ rows: any[]; total: number }>(`/quotations/${qid}/bom`)
export const saveQuotationBom = (qid: number, data: Record<string, unknown>) =>
  api(`/quotations/${qid}/bom`, { method: 'PUT', body: JSON.stringify(data) })
export const saveBomSnapshot = (solId: number, data: Record<string, unknown>) =>
  api(`/solutions/${solId}/bom-snapshot`, { method: 'PUT', body: JSON.stringify(data) })
export const bomExportUrl = (solId: number) => {
  const token = localStorage.getItem('token') || ''
  return `${API_BASE}/solutions/${solId}/bom-snapshot/export-xlsx?token=${encodeURIComponent(token)}`
}

// --- Quotations ---
export const fetchQuotations = (params: string = '') =>
  api<{ quotations: Quotation[]; total: number; page: number; per_page: number }>(`/quotations${params ? '?' + params : ''}`)
export const fetchQuotation = (id: number) => api<{ quotation: Quotation }>(`/quotations/${id}`)
export const createQuotation = (data: Record<string, unknown>) => api('/quotations', { method: 'POST', body: JSON.stringify(data) })
export const updateQuotation = (id: number, data: Record<string, unknown>) => api(`/quotations/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteQuotation = (id: number) => api(`/quotations/${id}`, { method: 'DELETE' })
export const batchDeleteQuotations = (ids: number[]) => api('/quotations/batch-delete', { method: 'POST', body: JSON.stringify({ ids }) })
export const addQuotationItem = (qtId: number, data: Record<string, unknown>) =>
  api(`/quotations/${qtId}/items`, { method: 'POST', body: JSON.stringify(data) })
export const updateQuotationItem = (qtId: number, itemId: number, data: Record<string, unknown>) =>
  api(`/quotations/${qtId}/items/${itemId}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteQuotationItem = (qtId: number, itemId: number) =>
  api(`/quotations/${qtId}/items/${itemId}`, { method: 'DELETE' })
export const quotationExportUrl = (qtId: number) => {
  const token = localStorage.getItem('token') || ''
  return `${API_BASE}/quotations/${qtId}/export-xlsx?token=${encodeURIComponent(token)}`
}

// --- AI ---
export async function* streamAiChat(input: string, conversationId?: number | null): AsyncGenerator<string> {
  const token = localStorage.getItem('token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  let conversationCaptured = !!conversationId
  const res = await fetch(`${API_BASE}/ai/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ input, conversation_id: conversationId }),
  })
  if (!res.ok) {
    // Non-SSE error response (e.g. 422 validation) — surface it instead of
    // silently ending the generator with no output.
    throw new ApiError(res.status, await readErrorDetail(res))
  }
  if (!res.body) throw new ApiError(res.status, 'Response body is empty')
  const reader = res.body.getReader()
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
          if (parsed.conversation_id && !conversationCaptured) {
            conversationCaptured = true
            yield `[CONVERSATION:${parsed.conversation_id}]`
          } else if (parsed.event === 'component') {
            yield `[COMPONENT:${JSON.stringify(parsed)}]`
          } else if (parsed.event === 'products' && parsed.data) {
            if (parsed.solution_name) {
              yield `[SOLUTION:${JSON.stringify({name: parsed.solution_name, desc: parsed.solution_desc || '', products: parsed.data})}]`
            } else {
              yield `[PRODUCTS:${JSON.stringify(parsed.data)}]`
            }
          } else if (parsed.event === 'tool') {
            yield `[TOOL:${parsed.text || ''}]`
          } else if (parsed.event === 'warning') {
            yield `[WARNING:${parsed.text || ''}]`
          } else if (parsed.text || parsed.event === 'text') {
            yield (parsed.text || '') as string
          }
        } catch { /* skip */ }
      }
    }
  }
}

// --- AI Conversations ---
export const fetchConversations = () => api<{ conversations: any[] }>('/ai/conversations')
export const fetchConversation = (id: number) => api<{ conversation: { id: number; title: string; messages?: { role: string; content: string; tool_calls?: string }[] } }>(`/ai/conversations/${id}`)
export const deleteConversation = (id: number) => api(`/ai/conversations/${id}`, { method: 'DELETE' })

// --- Settings ---
export const updateSetting = (key: string, value: string) =>
  api('/settings/' + key, { method: 'PUT', body: JSON.stringify({ value }) })

