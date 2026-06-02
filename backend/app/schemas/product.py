"""Product Pydantic schemas."""
from typing import Optional, Any
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    model: str = ""
    sku: str = ""
    category_id: int
    manufacturer_id: Optional[int] = None
    supplier_id: Optional[int] = None
    unit: str = "台"
    base_price: Optional[float] = None
    cost_price: Optional[float] = None
    description: str = ""
    image_url: str = ""
    product_url: str = ""
    status: str = "active"
    parent_id: Optional[int] = None
    specs: dict = {}
    urls: dict = {}
    custom_fields: dict = {}
    comm_methods: list[dict] = []
    comm_protocols: list[dict] = []
    power_supplies: list[dict] = []
    hardware_interfaces: list[dict] = []
    sensor_capabilities: list[dict] = []
    images: list[dict] = []


class ProductUpdate(BaseModel):
    """Partial update schema — all fields optional for PUT."""
    name: Optional[str] = None
    model: Optional[str] = None
    sku: Optional[str] = None
    category_id: Optional[int] = None
    manufacturer_id: Optional[int] = None
    supplier_id: Optional[int] = None
    unit: Optional[str] = None
    base_price: Optional[float] = None
    cost_price: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    product_url: Optional[str] = None
    status: Optional[str] = None
    parent_id: Optional[int] = None
    specs: Optional[dict] = None
    urls: Optional[dict] = None
    custom_fields: Optional[dict] = None
    comm_methods: Optional[list[dict]] = None
    comm_protocols: Optional[list[dict]] = None
    power_supplies: Optional[list[dict]] = None
    hardware_interfaces: Optional[list[dict]] = None
    sensor_capabilities: Optional[list[dict]] = None
    images: Optional[list[dict]] = None


class ProductResponse(BaseModel):
    product: dict


class ProductListResponse(BaseModel):
    products: list[dict]
    total: int
    page: int
    per_page: int


class ProductImportPreview(BaseModel):
    file: Optional[str] = None


class AIFetchRequest(BaseModel):
    url: str = ""
    text: str = ""


class AIFetchResponse(BaseModel):
    fetched: dict


class ProductCompareResponse(BaseModel):
    products: dict[int, dict]
    matrix: dict[str, dict[int, Any]]
    display_names: dict[str, str]


class ProductImportConfirm(BaseModel):
    mapping: dict = {}
    rows: list[list] = []


class DownloadImageRequest(BaseModel):
    url: str


class ProductDependencyCreate(BaseModel):
    depends_on_product_id: Optional[int] = None
    depends_on_category_id: Optional[int] = None
    dependency_type: str = "required"
    description: Optional[str] = None
    sort_order: int = 0


class ProductDependencyUpdate(BaseModel):
    depends_on_product_id: Optional[int] = None
    depends_on_category_id: Optional[int] = None
    dependency_type: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
