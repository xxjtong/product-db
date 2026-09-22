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
    # 可选：创建时一并并入方案的产品（形如 [{"product_id": 1, "quantity": 2}]）。
    # 用于「AI 出预览 → 用户点确认」这条路：预览里展示过的补充产品原样回传，
    # 方案里已存在的会被忽略（不重复添加、不改数量）。
    extra_items: list[dict] = []


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


class QuotationBOMRow(BaseModel):
    """BOM 编辑器提交的一行（与编辑器列一一对应）。

    原先这个端点收裸 `dict`，前端传什么后端都收 —— 脏类型要靠 number_or 逐个兜底，
    契约也不可见。改成显式 schema 后类型不符会明确 422（R74）。
    """
    name: str = ""
    sku: str = ""
    model: str = ""
    description: str = ""
    qty: Optional[float] = None      # 0 是合法值（本次不采购但保留该行）
    price: Optional[float] = None
    discount: Optional[float] = None
    remark: str = ""
    cost: Optional[float] = None     # 无成本权限的用户读到的是 None


class QuotationBOMSave(BaseModel):
    rows: list[QuotationBOMRow] = []
