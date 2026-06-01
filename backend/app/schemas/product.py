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


class ProductUpdate(ProductCreate):
    pass  # same fields, all optional in practice via PUT


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
