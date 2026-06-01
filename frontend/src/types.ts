export interface Category {
  id: number
  name: string
  slug: string
  parent_id: number | null
  level: number
  sort_order: number
  is_active: boolean
  children?: Category[]
}

export interface SpecDefinition {
  id: number
  category_id: number
  spec_key: string
  display_name: string
  spec_type: 'string' | 'number' | 'enum' | 'boolean' | 'range'
  unit: string
  sort_order: number
  is_filterable: boolean
  is_comparable: boolean
  display_group: string
  options: any[] | null
  validation: Record<string, number> | null
}

export interface Product {
  id: number
  name: string
  model: string
  sku: string
  category_id: number
  category_name: string
  manufacturer_id: number | null
  manufacturer_name: string
  supplier_id: number | null
  supplier_name: string
  unit: string
  base_price: number
  cost_price: number
  description: string
  image_url: string
  product_url: string
  status: string
  parent_id: number | null
  comm_methods: any[]
  comm_protocols: any[]
  power_supplies: any[]
  hardware_interfaces: any[]
  sensor_capabilities: any[]
  images: any[]
  specs: Record<string, any>
  urls: Record<string, string>
  custom_fields: Record<string, any>
  created_at: string
  updated_at: string
}

export interface Supplier {
  id: number
  name: string
  contact_person: string
  phone: string
  email: string
  website: string
  notes: string
}

export interface Solution {
  id: number
  name: string
  description: string
  client_name: string
  project_name: string
  status: string
  total_cost: number
  total_price: number
  notes: string
  created_by: number | null
  items: SolutionItem[]
  created_at: string
  updated_at: string
}

export interface SolutionItem {
  id: number
  solution_id: number
  product_id: number
  product_name: string
  quantity: number
  unit_price: number
  discount_rate: number
  remark: string
  sort_order: number
}

export interface Quotation {
  id: number
  solution_id: number | null
  quote_number: string
  title: string
  client_name: string
  client_contact: string
  valid_days: number
  tax_rate: number
  status: string
  total_amount: number
  notes: string
  created_by: number | null
  items: QuotationItem[]
  created_at: string
  updated_at: string
}

export interface QuotationItem {
  id: number
  quotation_id: number
  product_id: number
  product_snapshot: Record<string, any>
  quantity: number
  unit_price: number
  amount: number
  discount_rate: number
  remark: string
  sort_order: number
}

export interface BOMTemplate {
  id: number
  name: string
  description: string
  sheet_name: string
  snapshot: Record<string, any>
  is_default: boolean
  created_by: number | null
  created_at: string
  updated_at: string
}

export interface PaginatedResult<T> {
  items: T[]
  total: number
  page: number
  per_page: number
}
