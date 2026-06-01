"""Solution / BOM schemas."""
from typing import Optional
from pydantic import BaseModel


class SolutionCreate(BaseModel):
    name: str
    description: str = ""
    client_name: str = ""
    project_name: str = ""
    status: str = "draft"
    notes: str = ""


class SolutionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    client_name: Optional[str] = None
    project_name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class SolutionItemCreate(BaseModel):
    product_id: int
    quantity: float = 1
    unit_price: Optional[float] = None
    discount_rate: float = 100
    remark: str = ""
    sort_order: int = 0


class SolutionItemUpdate(BaseModel):
    product_id: Optional[int] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    discount_rate: Optional[float] = None
    remark: Optional[str] = None
    sort_order: Optional[int] = None


class BOMSnapshotSave(BaseModel):
    snapshot: dict
