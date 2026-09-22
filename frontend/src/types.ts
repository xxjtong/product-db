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

export interface ProductCommMethod { method_id: number; method_name: string; method_type: string; details: string }
export interface ProductCommProtocol { protocol_id: number; protocol_name: string; direction: string }
export interface ProductPowerSupply { power_id: number; power_name: string; voltage_range: string; battery_life: string }
export interface ProductHardwareInterface { id: number; interface_name: string; quantity: number; description: string }
export interface ProductSensorCapability { metric_id: number; metric_name: string; unit: string; measure_range: string; accuracy: string; resolution: string }
export interface ProductImage { id: number; url: string; is_primary: boolean; sort_order: number; alt_text: string }
export interface ProductDependency { id: number; product_id: number; depends_on_product_id: number; depends_on_category_id: number | null; dependency_type: string; description: string; sort_order: number }

export interface Product {
  id: number
  name: string
  model: string
  sku: string
  category_id: number
  category_ids?: number[]
  category_name: string
  all_category_names?: string[]
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
  comm_methods: ProductCommMethod[]
  comm_protocols: ProductCommProtocol[]
  power_supplies: ProductPowerSupply[]
  hardware_interfaces: ProductHardwareInterface[]
  sensor_capabilities: ProductSensorCapability[]
  images: ProductImage[]
  specs: Record<string, unknown>
  urls: Record<string, string>
  // custom_fields 保持 any：ProductFormView（第一批、不在本次范围）用
  // `(p.custom_fields && p.custom_fields.remark) || ''` 直接当 string 用，改成 unknown 会编译失败
  custom_fields: Record<string, any>
  created_at: string
  updated_at: string
  view_count?: number
  variants?: { id: number; name: string; model: string }[]
  spec_definitions?: SpecDefinition[]
}

export interface Manufacturer {
  id: number
  name: string
  website?: string
  description?: string
  sort_order?: number
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
  product_model: string
  product_sku: string
  product_description?: string
  product_cost_price?: number
  quantity: number
  unit_price: number | null
  discount_rate: number
  amount?: number
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
  download_count?: number
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

/** 当前登录用户（/auth/session 返回的 user，App 层通过 currentUser 注入） */
export interface CurrentUser {
  id: number
  username: string
  role: string
  email?: string
}

/** 字典主数据：通讯方式 / 通讯协议 / 供电方式 / 传感器指标 */
export interface CommMethod {
  id: number
  name: string
  method_type?: string
  description?: string
}

export interface CommProtocol {
  id: number
  name: string
  description?: string
}

export interface PowerSupply {
  id: number
  name: string
  supply_category?: string
  description?: string
}

export interface SensorMetric {
  id: number
  name: string
  unit?: string
  accuracy?: string
  resolution?: string
  measure_range?: string
  description?: string
}

// 产品表单（编辑态）相关的行类型：与后端 Product 子结构对应，但允许「尚未选择」的空值
export interface ProductFormCommMethod { method_id: number | null; details: string }
export interface ProductFormCommProtocol { protocol_id: number | null; direction: string }
export interface ProductFormPowerSupply { power_id: number | null; voltage_range: string; battery_life: string }
export interface ProductFormHardwareInterface { interface_name: string; quantity: number; description: string }
export interface ProductFormSensorCapability { metric_id: number | null; measure_range: string; accuracy: string; resolution: string }
export interface ProductFormImage { url: string; is_primary: boolean; sort_order: number }

export interface ProductForm {
  name: string
  model: string
  sku: string
  category_id: number | null
  category_ids: number[]
  manufacturer_id: number | null
  supplier_id: number | null
  // v-model.number 清空输入时会得到 ''；加载前可能为 null/undefined，故保留联合类型
  base_price: number | string | null | undefined
  cost_price?: number | null
  description: string
  status: string
  parent_id: number | null
  comm_methods: ProductFormCommMethod[]
  comm_protocols: ProductFormCommProtocol[]
  power_supplies: ProductFormPowerSupply[]
  hardware_interfaces: ProductFormHardwareInterface[]
  sensor_capabilities: ProductFormSensorCapability[]
  images: ProductFormImage[]
  image_url: string
  product_url: string
  remark?: string
  specs: Record<string, unknown>
  custom_fields?: Record<string, unknown>
}

/** AI 智能录入（AiExtractCard）返回给表单的原始结构：外部模型输出，字段可能缺失 */
export interface AiFillPayload {
  name?: string
  model?: string
  description?: string
  base_price?: number
  category_slug?: string
  manufacturer_name?: string
  comm_methods?: { name?: string; details?: string }[]
  comm_protocols?: { name?: string; direction?: string }[]
  power_supplies?: { name?: string; voltage_range?: string; battery_life?: string }[]
  hardware_interfaces?: { interface_name?: string; quantity?: number; description?: string }[]
  sensor_capabilities?: { metric_name?: string; measure_range?: string; accuracy?: string; resolution?: string }[]
  specs?: Record<string, unknown> | string
}
