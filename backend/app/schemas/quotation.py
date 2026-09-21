"""Quotation schemas."""
from typing import Optional
from pydantic import BaseModel


class QuotationCreate(BaseModel):
    solution_id: Optional[int] = None
    title: Optional[str] = None
    client_name: Optional[str] = None
    client_contact: Optional[str] = None
    valid_days: int = 15
    # 增值税一般税率（百分数，13 表示 13%）。前端没有设置入口（R21 移除了税率信息行），
    # 实际只在导出 xlsx 的备注行展示，所以统一按 13% 出。显式传入时仍以传入值为准。
    # 注意：报价口径是**含税**（单价即含税单价），该字段不参与金额计算。
    tax_rate: float = 13
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
