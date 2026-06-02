"""Quotation schemas."""
from typing import Optional
from pydantic import BaseModel


class QuotationCreate(BaseModel):
    solution_id: Optional[int] = None
    title: Optional[str] = None
    client_name: Optional[str] = None
    client_contact: Optional[str] = None
    valid_days: int = 15
    tax_rate: float = 0
    status: str = "draft"
    notes: Optional[str] = None


class QuotationUpdate(BaseModel):
    title: Optional[str] = None
    client_name: Optional[str] = None
    client_contact: Optional[str] = None
    valid_days: Optional[int] = None
    tax_rate: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class QuotationItemCreate(BaseModel):
    product_id: int
    quantity: float = 1
    unit_price: Optional[float] = None
    amount: float = 0
    discount_rate: float = 100
    remark: Optional[str] = None
    sort_order: int = 0


class QuotationItemUpdate(BaseModel):
    product_id: Optional[int] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    discount_rate: Optional[float] = None
    remark: Optional[str] = None
    sort_order: Optional[int] = None
