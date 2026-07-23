from app.database import Base, JSONBType
from sqlalchemy import (Column, Integer, String, DateTime,
                        ForeignKey, Text, Numeric)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone


class Solution(Base):
    __tablename__ = "solutions"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    client_name = Column(String(200), nullable=True)
    project_name = Column(String(200), nullable=True)
    status = Column(String(20), default="draft")
    total_cost = Column(Numeric(14, 2), default=0)
    total_price = Column(Numeric(14, 2), default=0)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    items = relationship("SolutionItem", back_populates="solution",
                         cascade="all, delete-orphan", order_by="SolutionItem.sort_order")
    bom_snapshot = relationship("SolutionBOMSnapshot", back_populates="solution",
                                uselist=False, cascade="all, delete-orphan")

    def to_dict(self, product_map=None):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "client_name": self.client_name or "",
            "project_name": self.project_name or "",
            "status": self.status,
            "total_cost": float(self.total_cost) if self.total_cost else 0,
            "total_price": float(self.total_price) if self.total_price else 0,
            "notes": self.notes or "",
            "created_by": self.created_by,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else "",
            "items": [item.to_dict(product_map) for item in self.items],
        }


class SolutionItem(Base):
    __tablename__ = "solution_items"

    id = Column(Integer, primary_key=True)
    solution_id = Column(Integer, ForeignKey("solutions.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Numeric(10, 2), default=1)
    unit_price = Column(Numeric(12, 2), nullable=True)
    discount_rate = Column(Numeric(5, 2), default=100)
    remark = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)

    solution = relationship("Solution", back_populates="items")
    product = relationship("Product")

    def to_dict(self, product_map=None):
        from app.utils.helpers import format_description_with_specs

        product_name = ""
        product_model = ""
        product_sku = ""
        product_description = ""
        product_specs = {}
        product_cost_price = 0.0
        if self.product_id and product_map:
            product_name = product_map.get(self.product_id, "")
        elif self.product:
            product_name = self.product.name
            product_model = self.product.model or ""
            product_sku = self.product.sku or ""
            product_specs = self.product.specs or {}
            product_description = format_description_with_specs(
                self.product.description or "",
                product_specs,
            )
            product_cost_price = float(self.product.cost_price or 0)
        return {
            "id": self.id,
            "solution_id": self.solution_id,
            "product_id": self.product_id,
            "product_name": product_name,
            "product_model": product_model,
            "product_sku": product_sku,
            "product_description": product_description,
            "product_cost_price": product_cost_price,
            "quantity": float(self.quantity) if self.quantity else 0,
            "unit_price": float(self.unit_price) if self.unit_price else 0,
            "discount_rate": float(self.discount_rate) if self.discount_rate else 100,
            "remark": self.remark or "",
            "sort_order": self.sort_order,
        }
